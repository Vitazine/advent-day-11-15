"""Partner-only HTTPS API; authentication and ownership on every endpoint."""
import hashlib,hmac,json,os,re,time
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from runner.policy import parse_proposal,PolicyError
from .controller import Controller,APIError

def strict_json(raw):
 def pairs(items):
  result={}
  for k,v in items:
   if k in result:raise ValueError()
   result[k]=v
  return result
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))

def create_app(root,token_file,gateway_token,start_worker=True):
 app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
 controller=Controller(root,gateway_token,start_worker);app.state.controller=controller
 @app.middleware('http')
 async def boundary(request,call_next):
  try:
   supplied=request.headers.get('authorization','')
   if not supplied.startswith('Bearer ') or len(supplied)>256:raise APIError('UNAUTHORIZED',401)
   digest=hashlib.sha256(supplied[7:].encode()).hexdigest();principal=None
   for item in json.loads(Path(token_file).read_text())['tokens']:
    if hmac.compare_digest(digest,item['sha256']) and time.time()<item['expires']:principal=item
   if principal is None:raise APIError('UNAUTHORIZED',401)
   request.state.principal=principal
   if request.method=='POST':
    raw=bytearray()
    async for chunk in request.stream():
     raw.extend(chunk)
     if len(raw)>256*1024:raise APIError('BODY_LIMIT',413)
    request.state.raw=bytes(raw)
   response=await call_next(request)
  except APIError as e:response=JSONResponse({'error':{'code':e.code}},status_code=e.status)
  except Exception:response=JSONResponse({'error':{'code':'INTERNAL_ERROR'}},status_code=500)
  response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
  return response
 @app.exception_handler(APIError)
 async def failure(request,error):return JSONResponse({'error':{'code':error.code}},status_code=error.status)
 @app.get('/v1/limits')
 def limits(request:Request):return controller.limits(request.state.principal)
 @app.post('/v1/jobs',status_code=202)
 def submit(request:Request):
  idem=request.headers.get('idempotency-key','')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',idem):raise APIError('IDEMPOTENCY_KEY_REQUIRED',422)
  try:
   body=strict_json(request.state.raw)
   if not isinstance(body,dict) or not set(body)<= {'files','task'}:raise ValueError()
   task=body.get('task','')
   if not isinstance(task,str) or len(task)>8192:raise ValueError()
   task.encode('utf-8')
   files=parse_proposal(json.dumps({'files':body['files']},ensure_ascii=False))
  except (ValueError,KeyError,TypeError,RecursionError):raise APIError('INVALID_REQUEST',422) from None
  return controller.submit(request.state.principal,idem,files,task)
 @app.get('/v1/jobs/{ident}')
 def status(ident:str,request:Request):return controller.status(request.state.principal,ident)
 @app.post('/v1/jobs/{ident}/accept')
 def accept(ident:str,request:Request):
  if request.state.raw not in (b'',b'{}'):raise APIError('INVALID_REQUEST',422)
  return controller.accept(request.state.principal,ident)
 @app.get('/v1/jobs/{ident}/artifact')
 def artifact(ident:str,request:Request):return controller.artifact(request.state.principal,ident)
 return app

def production():
 return create_app(Path('/var/lib/day15-api'),Path('/etc/day15-api/tokens.json'),Path('/etc/day15-api/gateway-token').read_text().strip())
