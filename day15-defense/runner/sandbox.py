"""Remote-only sandbox transport. No local execution fallback."""
import json
from pathlib import Path
import re
import subprocess
from .contracts import RunResult, Snapshot
from .snapshot import canonical
from .fingerprint import worker_fingerprint

class SandboxError(RuntimeError):pass

def build_unit_command(root: Path,unit: str, release: Path | None = None) -> list[str]:
    if not re.fullmatch(r'/var/lib/day15-defense/jobs/[a-z0-9]+/root',str(root)) or not re.fullmatch(r'day15-job-[a-z0-9]+',unit):
        raise SandboxError('INVALID_SANDBOX_PATH')
    release = release or Path('/srv/day15-defense/current').resolve()
    if not re.fullmatch(r'/srv/day15-defense/(?:releases/[0-9TZ]+|current)',str(release)):
        raise SandboxError('INVALID_RELEASE')
    properties=[f'RootDirectory={root}','Type=exec','DynamicUser=yes','WorkingDirectory=/work',
        'BindReadOnlyPaths=/usr/bin','BindReadOnlyPaths=/usr/lib',
        f'BindReadOnlyPaths={release}/runtime:/opt/runtime',
        'TemporaryFileSystem=/tmp:rw,size=32M','TemporaryFileSystem=/run:rw,size=4M',
        'ProtectSystem=strict','ProtectHome=yes','PrivateNetwork=yes','PrivateDevices=yes',
        'ProtectProc=invisible','ProcSubset=pid','MountAPIVFS=yes','NoNewPrivileges=yes',
        'CapabilityBoundingSet=','RestrictSUIDSGID=yes','ProtectKernelTunables=yes',
        'ProtectKernelModules=yes','ProtectControlGroups=yes','RestrictAddressFamilies=AF_UNIX',
        'SystemCallFilter=@system-service','MemoryMax=192M','MemorySwapMax=0','CPUQuota=50%',
        'TasksMax=64','RuntimeMaxSec=120','TimeoutStopSec=3','KillMode=control-group']
    cmd=['systemd-run','--quiet','--wait','--pipe','--collect',f'--unit={unit}']
    for prop in properties:cmd+=['-p',prop]
    return cmd+['/usr/bin/python3','-I','-B','/opt/check.py']

class Sandbox:
    def __init__(self,ssh_command: list[str] | None):self.ssh_command=ssh_command
    def run(self,snapshot: Snapshot,profile='python-fastapi') -> RunResult:
        if not self.ssh_command or profile!='python-fastapi':raise SandboxError('SANDBOX_UNAVAILABLE')
        payload=canonical(snapshot.files)
        try:
            proc=subprocess.run([*self.ssh_command,'sudo /usr/bin/python3 -I /srv/day15-defense/current/server/worker.py'],input=payload,capture_output=True,timeout=150,check=False)
            if len(proc.stdout)>16384 or proc.returncode:raise SandboxError('REMOTE_ERROR')
            data=json.loads(proc.stdout)
            if data.get('artifact_hash')!=snapshot.artifact_hash:raise SandboxError('HASH_MISMATCH')
            if set(data)!={'status','exit_code','evidence_id','artifact_hash','reason_codes','profile_hash'}:raise SandboxError('REMOTE_SHAPE')
            if data['profile_hash']!=worker_fingerprint():raise SandboxError('WORKER_VERSION_MISMATCH')
            if data['status'] not in ('passed','failed','timeout','error'):raise SandboxError('REMOTE_STATUS')
            if data['status']=='passed' and data['exit_code']!=0:raise SandboxError('REMOTE_STATUS')
            if not re.fullmatch('[0-9a-f]{32}',data['evidence_id']):raise SandboxError('REMOTE_ID')
            return RunResult(data['status'],data['exit_code'],data['evidence_id'],data['artifact_hash'],tuple(data['reason_codes']))
        except (OSError,ValueError,subprocess.TimeoutExpired):raise SandboxError('SANDBOX_UNAVAILABLE') from None
