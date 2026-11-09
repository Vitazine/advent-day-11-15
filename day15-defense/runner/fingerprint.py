"""Policy identity changes with security-sensitive implementation or pins."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(paths):
    h=hashlib.sha256()
    for name in paths:
        data=(ROOT/name).read_bytes();h.update(name.encode()+b'\0'+str(len(data)).encode()+b'\0'+data)
    return h.hexdigest()

def worker_fingerprint():
    return digest(('runner/fingerprint.py','runner/snapshot.py','runner/contracts.py','server/broker.py','server/worker.py','sandbox/check.py','sandbox/ast_checks.py','sandbox/bandit_entry.py','sandbox/bandit.ini','runner/sandbox.py','requirements-worker.txt'))

def policy_fingerprint():
    return digest(('api/app.py','api/controller.py','runner/native_generator.py','runner/unix_executor.py','requirements-api.txt','runner/process.py','runner/relay.py','runner/review_client.py','runner/gate.py','runner/checks.py','runner/snapshot.py','runner/policy.py','runner/accept.py','runner/store.py','runner/loop.py','runner/opencode.py','runner/gateway_client.py','integration/opencode/manifest.json'))+worker_fingerprint()
