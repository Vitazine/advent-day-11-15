"""Root-owned SSH entrypoint. JSON stdin only; no caller-selected commands/paths."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time
import uuid

RELEASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RELEASE))
from runner.snapshot import validate,canonical
from runner.sandbox import build_unit_command
from runner.fingerprint import worker_fingerprint

BASE=Path('/var/lib/day15-defense')

def main():
    if os.getuid()!=0:raise SystemExit(2)
    os.umask(0o077)
    raw=sys.stdin.buffer.read(240*1024+1)
    if len(raw)>240*1024:raise SystemExit(2)
    try:files=validate(json.loads(raw))
    except (ValueError,TypeError):raise SystemExit(2)
    digest=hashlib.sha256(canonical(files)).hexdigest()
    job=uuid.uuid4().hex
    report=dict(status='error',exit_code=None,evidence_id=job,artifact_hash=digest,reason_codes=[],profile_hash=worker_fingerprint())
    def output():print(json.dumps(report,separators=(',',':')))
    BASE.mkdir(mode=0o700,exist_ok=True)
    lock=(BASE/'worker.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        report['reason_codes']=['BUSY'];output();return
    available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    if available<256*1024*1024:
        report['reason_codes']=['HOST_MEMORY_LOW'];output();return
    root=BASE/'jobs'/job/'root'
    unit='day15-job-'+job
    try:
        for name in ('usr/bin','usr/lib','lib64','tmp','run','work','etc','proc','dev','opt','opt/runtime'):
            (root/name).mkdir(parents=True,exist_ok=True,mode=0o755)
        # RootDirectory is entered by PID1 before dropping privileges.
        for parent in (root,root/'usr'):parent.chmod(0o755)
        (root/'lib').symlink_to('usr/lib');(root/'bin').symlink_to('usr/bin')
        (root/'lib64/ld-linux-x86-64.so.2').symlink_to('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')
        for file in files:
            path=root/'work'/file.path
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
            path.write_text(file.content,encoding='utf-8',newline='');path.chmod(0o444)
        for name in ('check.py','bandit_entry.py','bandit.ini','ast_checks.py'):
            shutil.copyfile(RELEASE/'sandbox'/name,root/'opt'/name);(root/'opt'/name).chmod(0o444)
        for directory in root.rglob('*'):
            if directory.is_dir() and not directory.is_symlink():directory.chmod(0o755)
        command=build_unit_command(root,unit,RELEASE)
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ)
        start=time.monotonic();total=0;reason=None
        try:
            while selector.get_map():
                if time.monotonic()-start>125:reason='TIMEOUT';break
                for key,_ in selector.select(0.5):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if not chunk:selector.unregister(key.fileobj);continue
                    total+=len(chunk)
                    if total>1024*1024:reason='OUTPUT_LIMIT';break
                if reason:break
            if reason:
                subprocess.run(['systemctl','stop',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
            code=proc.wait(timeout=10)
            report['exit_code']=code
            report['status']='timeout' if reason=='TIMEOUT' else ('failed' if reason or code else 'passed')
            report['reason_codes']=[reason] if reason else ([] if code==0 else ['CHECKS_FAILED'])
        finally:
            selector.close();proc.stdout.close()
            if proc.poll() is None:proc.kill();proc.wait()
    except Exception:
        report['status']='error';report['reason_codes']=['EXECUTOR_ERROR']
    finally:
        subprocess.run(['systemctl','stop',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
        shutil.rmtree(BASE/'jobs'/job,ignore_errors=True)
    # No code, test output, env values or secrets are retained in audit.
    audit=BASE/'audit';audit.mkdir(mode=0o700,exist_ok=True)
    (audit/f'{job}.json').write_text(json.dumps(report))
    for old in sorted(audit.glob('*.json'),key=lambda p:p.stat().st_mtime)[:-1000]:old.unlink()
    output()

if __name__=='__main__':main()
