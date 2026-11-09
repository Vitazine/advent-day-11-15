"""Create private local credentials; never print either key."""
import argparse
import getpass
import hashlib
import json
import os
import secrets
from pathlib import Path

def configure(target,api_key):
    target=Path(target)
    # A fresh directory is ownership evidence; never overwrite or follow existing paths.
    target.mkdir(mode=0o700,parents=False,exist_ok=False)
    token='client.'+secrets.token_urlsafe(32)
    values={'proxy-token':token,'tokens.json':json.dumps({'client':hashlib.sha256(token.encode()).hexdigest()}),'upstream-key':api_key}
    for name,value in values.items():
        fd=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(value+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=Path('.local/credentials'))
    args=parser.parse_args();args.directory.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    api_key=getpass.getpass('DeepSeek API key (скрытый ввод): ').strip()
    if not api_key:parser.error('Пустой ключ')
    configure(args.directory,api_key)
    print('Созданы файлы credentials; значения ключей не выводятся.')
