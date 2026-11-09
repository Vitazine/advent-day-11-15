#!/usr/bin/env python3
"""Standalone stdlib client. Never executes or extracts returned source."""
import argparse,hashlib,json,re,sys,time,uuid
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
BASE='https://just-black-coffe.shop/day15/v1'
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def call(token,method,path,payload=None,key=None):
 headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
 if key:headers['Idempotency-Key']=key
 data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
 req=Request(BASE+path,data=data,headers=headers,method=method)
 opener=build_opener(ProxyHandler({}),NoRedirect())
 try:
  with opener.open(req,timeout=30) as response:
   raw=response.read(512*1024+1)
   if len(raw)>512*1024:raise ValueError('Response too large')
   return json.loads(raw)
 except HTTPError as error:
  try:code=json.loads(error.read(4096)).get('error',{}).get('code','HTTP_ERROR')
  except ValueError:code='HTTP_ERROR'
  raise ValueError(f'HTTP {error.code}: {code}') from None

def main():
 parser=argparse.ArgumentParser(description='Day15 partner API client')
 parser.add_argument('--token-file',type=Path,required=True)
 sub=parser.add_subparsers(dest='command',required=True)
 sub.add_parser('limits')
 submit=sub.add_parser('submit');submit.add_argument('--input',type=Path,required=True);submit.add_argument('--key',required=True)
 for name in ('status','wait','accept','download'):
  command=sub.add_parser(name);command.add_argument('job_id')
  if name=='download':command.add_argument('--output',type=Path,required=True)
 args=parser.parse_args();token=args.token_file.read_text().strip()
 if args.command=='limits':result=call(token,'GET','/limits')
 elif args.command=='submit':
  if args.input.stat().st_size>256*1024:raise ValueError('Input too large')
  if not re.fullmatch('[A-Za-z0-9_-]{1,64}',args.key):raise ValueError('Invalid idempotency key')
  result=call(token,'POST','/jobs',json.loads(args.input.read_text()),args.key)
 else:
  if not re.fullmatch('[0-9a-f]{32}',args.job_id):raise ValueError('Invalid job ID')
  route='/jobs/'+args.job_id
  if args.command=='accept':result=call(token,'POST',route+'/accept',{})
  elif args.command=='download':
   result=call(token,'GET',route+'/artifact')
   files=result['files'];canonical=json.dumps(sorted([[f['path'],f['content']] for f in files]),ensure_ascii=False,separators=(',',':')).encode()
   if hashlib.sha256(canonical).hexdigest()!=result['artifact_hash']:raise ValueError('Artifact hash mismatch')
   with args.output.open('x',encoding='utf-8') as file:json.dump(result,file,ensure_ascii=False,indent=2)
   result={'saved':str(args.output),'artifact_hash':result['artifact_hash']}
  else:
   deadline=time.monotonic()+660
   while True:
    result=call(token,'GET',route)
    if args.command=='status' or result['state'] not in ('queued','running'):break
    if time.monotonic()>deadline:raise ValueError('Wait timed out; use status with the same job ID')
    time.sleep(3)
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (OSError,ValueError,KeyError,URLError) as error:
  print(str(error),file=sys.stderr);raise SystemExit(1)
