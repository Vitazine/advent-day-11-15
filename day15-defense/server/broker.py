"""Root broker. Restricted Unix peer; fixed subprocess and bounded JSON only."""
import os,pwd,socket,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 if os.getuid()!=0:raise SystemExit(2)
 path=Path('/run/day15-executor/worker.sock')
 if path.exists():path.unlink()
 allowed=pwd.getpwnam('day15api').pw_uid
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
  listener.bind(str(path));path.chmod(0o660);listener.listen(2)
  while True:
   conn,_=listener.accept()
   with conn:
    try:
     _,uid,_=struct.unpack('3i',conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
     if uid!=allowed:continue
     conn.settimeout(5);raw=bytearray()
     while True:
      chunk=conn.recv(65536)
      if not chunk:break
      raw.extend(chunk)
      if len(raw)>240*1024:raise ValueError()
     result=subprocess.run(['/usr/bin/python3','-I',str(ROOT/'server/worker.py')],input=bytes(raw),capture_output=True,timeout=145)
     if result.returncode or len(result.stdout)>16384:raise ValueError()
     conn.sendall(result.stdout)
    except Exception:
     try:conn.sendall(b'{"error":"EXECUTOR_FAILED"}')
     except OSError:pass
if __name__=='__main__':main()
