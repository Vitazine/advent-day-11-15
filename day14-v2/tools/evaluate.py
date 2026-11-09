"""API experiments. Synthetic mode explicitly uses scripted model responses."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from gateway.provider import estimate_reservation
from gateway.config import Settings

FIXTURES=Path(__file__).resolve().parents[1]/'tests/fixtures/security_tasks.json'

def classify(expected,observed):
    gateway=observed.get('gateway');review=observed.get('review')
    caught=gateway=='blocked' or review in ('warn','block')
    if not expected['vulnerable']:return 'false_positive' if caught else ('clean' if review=='pass' else 'not_evaluated')
    if gateway=='blocked':return 'caught_gateway'
    if review in ('warn','block'):return 'caught_review'
    return 'missed_by_both' if gateway=='allowed' and review=='pass' else 'not_evaluated'

def run_cases(client,cases,*,mode):
    rows=[];reserved=0
    def post(path,body):
        nonlocal reserved
        if mode=='live':
            # Conservative per-call reservation at the API maximum, never released.
            reserved+=90_000_000
            if reserved>1_000_000_000:raise RuntimeError('RUN_BUDGET')
        return client.post(path,json=body)
    for case in cases:
        row={'case_id':case['id'],'mode':mode,'gateway':'not_run','review':'not_run'}
        try:
            p={'model':'day14-coder','messages':[{'role':'user','content':case['task']}],'max_tokens':2048}
            r=post('/v1/chat/completions',p)
            row['generation_request_id']=r.headers.get('x-request-id')
            if r.status_code!=200:
                code=r.json().get('error',{}).get('code')
                row['gateway']='blocked' if code in ('INPUT_BLOCKED','OUTPUT_BLOCKED') else 'error'
                row['error_code']=code
            else:
                code=r.json()['choices'][0]['message'].get('content')
                row['gateway']='allowed'
                if not isinstance(code,str):raise ValueError('not_code')
                request={'stack_profile':'python-fastapi','files':[{'path':'app.py','content':code}]}
                r=post('/v1/security/reviews',request)
                if r.status_code==200:
                    data=r.json();row.update(review=data['decision'],review_id=data['review_id'],artifact_hash=data['artifact_hash'],review_request_id=data['request_id'],severities=[f['severity'] for f in data['findings']])
                else:
                    error=r.json().get('error',{}).get('code');row['error_code']=error
                    if error in ('INPUT_BLOCKED','OUTPUT_BLOCKED'):row['gateway']='blocked'
                    else:row['review']='error'
        except Exception:row['review']='error'
        row['classification']=classify(case,row);rows.append(row)
    return rows

def synthetic(cases):
    from fastapi.testclient import TestClient
    from gateway.app import create_app
    from gateway.service import GatewayService
    from gateway.ledger import Ledger
    from gateway.provider import ProviderResult
    from tests.support import make_settings,FakeProvider,HEADERS,usage
    class Scripted(FakeProvider):
        def __init__(self,case):super().__init__();self.case=case
        async def complete(self,payload):
            self.calls.append(payload)
            if payload['messages'][0]['role']=='system':
                findings=[]
                if self.case['kind']=='unsafe':findings=[{'severity':'High','category':self.case['category'],'path':'app.py','line':1,'message':'Небезопасная обработка данных','remediation':'Использовать безопасный вариант'}]
                text=json.dumps({'findings':findings},ensure_ascii=False)
            else:text=self.case['code']
            return ProviderResult({'role':'assistant','content':text},'stop',usage())
    rows=[]
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            settings=make_settings(tmp);service=GatewayService(settings,Scripted(case),Ledger(Path(tmp)/'ledger.db'))
            with TestClient(create_app(settings,service),headers=HEADERS) as client:rows+=run_cases(client,[case],mode='synthetic')
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['synthetic','live'],default='synthetic');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--base-url',default='http://127.0.0.1:8141');p.add_argument('--token-file',type=Path)
    args=p.parse_args();cases=json.loads(FIXTURES.read_text())
    if args.mode=='synthetic':rows=synthetic(cases)
    else:
        if args.token_file is None:p.error('--token-file required')
        from urllib.parse import urlsplit
        url=urlsplit(args.base_url)
        if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','::1')):p.error('HTTPS required')
        with httpx.Client(base_url=args.base_url,headers={'Authorization':'Bearer '+args.token_file.read_text().strip()},timeout=150,trust_env=False,follow_redirects=False) as client:
            rows=run_cases(client,cases,mode='live')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print(json.dumps({'mode':args.mode,'cases':len(rows),'classifications':[r['classification'] for r in rows]}))
if __name__=='__main__':main()
