#!/usr/bin/python3
"""Root-only credential installation. Input is bounded JSON via SSH stdin, never argv."""
import json
import os
import subprocess
import sys
from pathlib import Path

def main():
    if os.geteuid()!=0: raise ValueError()
    raw=sys.stdin.buffer.read(8193)
    if len(raw)>8192: raise ValueError()
    data=json.loads(raw)
    key=data['api_key']; password=data['password']
    if (not isinstance(key,str) or not key.startswith('sk-') or not 12<=len(key)<=1024 or
        not key.isascii() or any(c.isspace() for c in key)):
        raise ValueError()
    if (not isinstance(password,str) or not 15<=len(password.encode('utf-8'))<=64 or
        any(c in password for c in '\r\n\x00')): raise ValueError()
    directory=Path('/etc/day13')
    encrypted=directory/'deepseek.cred.new'
    hashed=directory/'access.htpasswd.new'
    try:
        encrypted.unlink(missing_ok=True)
        subprocess.run(['systemd-creds','encrypt','--name=deepseek','-',str(encrypted)],
                       input=key.encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        result=subprocess.run(['htpasswd','-niBC','12','day13'],input=(password+'\n').encode(),
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True)
        encrypted.chmod(0o600)
        with hashed.open('wb') as f:
            os.fchmod(f.fileno(),0o640); f.write(result.stdout); f.flush(); os.fsync(f.fileno())
        import grp
        os.chown(hashed,0,grp.getgrnam('www-data').gr_gid)
        os.replace(encrypted,directory/'deepseek.cred')
        os.replace(hashed,directory/'access.htpasswd')
        subprocess.run(['systemctl','restart','day13'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['systemctl','is-active','--quiet','day13'],check=True)
        print('Credentials installed; service active.')
    finally:
        encrypted.unlink(missing_ok=True); hashed.unlink(missing_ok=True)

if __name__=='__main__':
    os.umask(0o077)
    try: main()
    except Exception:
        print('Credential setup failed; no secret values logged.',file=sys.stderr)
        sys.exit(1)
