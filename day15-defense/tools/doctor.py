"""Read-only bootstrap checks. Identity is never an end-to-end readiness claim."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def inspect_client(binary: Path, version: str, expected_digest: str) -> dict:
    try:
        with binary.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        return {'status': 'missing'}
    if digest != expected_digest:
        return {'status': 'digest_mismatch'}
    return {'status': 'verified_identity', 'version': version, 'sha256': digest}

def inspect_runtime(binary: Path | None) -> dict:
    if binary is None:
        return {'status': 'missing'}
    try:
        result = subprocess.run([str(binary), 'info', '--format', '{{.OSType}}'],
                                capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'unavailable'}
    if result.returncode:
        return {'status': 'unavailable'}
    return {'status': 'available' if result.stdout.strip() == b'linux' else 'not_linux'}

def readiness(client: dict, runtime: dict, e2e_verified: bool = False) -> dict:
    # This bootstrap cannot attest to policy enforcement or an unimplemented loop.
    blockers = [] if e2e_verified else ['current_policy_e2e_unverified']
    if client.get('status') != 'verified_identity':
        blockers.append('client_unverified')
    if runtime.get('status') != 'available':
        blockers.append('runtime_unavailable')
    return {'ready': not blockers, 'blockers': blockers}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT/'integration/opencode/manifest.json')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    client = inspect_client(Path(manifest['binary']), manifest['version'], manifest['sha256'])
    from runner.gate import POLICY_HASH
    from runner.snapshot import SnapshotStore
    from runner.sandbox import Sandbox
    import tempfile, time
    runtime={'status':'unavailable'}
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','IdentitiesOnly=yes','-i',str(Path.home()/'.ssh/day15_executor'),'deploy@executor.example.com']
    try:
        with tempfile.TemporaryDirectory() as tmp:
            snap=SnapshotStore(Path(tmp).resolve()/'snapshots').from_files([('test_health.py','import unittest\nclass Health(unittest.TestCase):\n def test_health(self): self.assertEqual(2+2,4)\n')])
            result=Sandbox(ssh).run(snap)
            if result.status=='passed':runtime={'status':'available','profile':'python-fastapi','evidence_id':result.evidence_id}
    except Exception:pass
    try:
        evidence=json.loads((ROOT/'evidence/final-e2e.json').read_text())
        verified=evidence['policy_hash']==POLICY_HASH and evidence['passed'] is True and 0<=time.time()-evidence['timestamp']<86400
    except (OSError,ValueError,KeyError):verified=False
    state=readiness(client,runtime,verified)
    print(json.dumps({'client':client,'vps_executor':runtime,**state},indent=2))
    return 0 if state['ready'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
