"""Unprivileged connection to fixed peer-restricted host executor."""
import json,re,socket
from .contracts import RunResult
from .snapshot import canonical
from .fingerprint import worker_fingerprint
from .sandbox import SandboxError

class UnixExecutor:
 def run(self,snapshot,profile='python-fastapi'):
  if profile!='python-fastapi':raise SandboxError('PROFILE_INVALID')
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
   conn.settimeout(150);conn.connect('/run/day15-executor/worker.sock')
   conn.sendall(canonical(snapshot.files));conn.shutdown(socket.SHUT_WR)
   chunks=bytearray()
   while True:
    part=conn.recv(4096)
    if not part:break
    chunks.extend(part)
    if len(chunks)>16384:raise SandboxError('OUTPUT_LIMIT')
  try:
   data=json.loads(chunks)
   if data['artifact_hash']!=snapshot.artifact_hash or data['profile_hash']!=worker_fingerprint():raise ValueError()
   if data['status'] not in ('passed','failed','timeout','error'):raise ValueError()
   if data['status']=='passed' and (type(data['exit_code'])!=int or data['exit_code']!=0):raise ValueError()
   if not re.fullmatch('[0-9a-f]{32}',data['evidence_id']):raise ValueError()
   return RunResult(data['status'],data['exit_code'],data['evidence_id'],data['artifact_hash'],tuple(data['reason_codes']))
  except (ValueError,TypeError,KeyError):raise SandboxError('EXECUTOR_INVALID') from None
