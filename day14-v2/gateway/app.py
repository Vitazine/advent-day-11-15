"""Authenticated API; full guard completes before response headers or SSE."""
import asyncio
import uuid
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from .auth import authenticate, IngressLimiter
from .config import Settings
from .contracts import ChatRequest, ReviewRequest, EventMeta, parse_json
from .errors import GatewayError
from .sse import completion, encode_sse

async def read_body(request):
    if request.headers.get('content-type','').split(';')[0].strip()!='application/json':raise GatewayError('INVALID_REQUEST',415)
    if request.headers.get('content-encoding','identity')!='identity':raise GatewayError('UNSUPPORTED_ENCODING',415)
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>512*1024:raise GatewayError('BODY_TOO_LARGE',413)
    return parse_json(bytes(raw))

def create_app(settings=None, service=None):
    settings=settings or Settings.load()
    if service is None:
        from .ledger import Ledger
        from .provider import Provider
        from .service import GatewayService
        service=GatewayService(settings,Provider(settings),Ledger(settings.data_dir/'ledger.db',audit_cap=settings.audit_cap))
    async def cleanup():
        while True:
            await asyncio.sleep(300)
            try:service.ledger.cleanup()
            except Exception:service.halted=True
    @asynccontextmanager
    async def lifespan(app):
        service.ledger.recover();service.ledger.cleanup()
        task=asyncio.create_task(cleanup())
        try:yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.service=service
    limiter=IngressLimiter()
    @app.middleware('http')
    async def boundary(request: Request, call_next):
        rid=uuid.uuid4().hex
        try:
            try:request.state.principal=authenticate(request.headers.get('authorization'),settings)
            except GatewayError:
                limiter.attempt(request.client.host if request.client else 'unknown')
                raise
            if request.method=='POST' and request.url.path in ('/v1/chat/completions','/v1/security/reviews'):
                service.ledger.attempt(request.state.principal.key_id)
            response=await call_next(request)
        except GatewayError as e:
            rid=getattr(e,'request_id',rid)
            response=JSONResponse(e.body(),status_code=e.status)
        except (ValidationError,ValueError):response=JSONResponse(GatewayError('INVALID_REQUEST').body(),status_code=422)
        except Exception:response=JSONResponse(GatewayError('UNAVAILABLE',503).body(),status_code=503)
        if response.status_code>=400 and hasattr(request.state,'principal'):
            try:
                service.ledger.record(EventMeta(request_id=getattr(request.state,'request_id',rid),
                    key_id=request.state.principal.key_id,stage='http',state='failed'))
            except Exception:
                response=JSONResponse(GatewayError('UNAVAILABLE',503).body(),status_code=503)
        response.headers['X-Request-ID']=getattr(request.state,'request_id',rid)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    @app.get('/v1/models')
    async def models():return {'object':'list','data':[{'id':'day14-coder','object':'model','created':0,'owned_by':'gateway'}]}
    @app.get('/v1/limits')
    async def limits(request: Request):return service.ledger.limits(request.state.principal.key_id)
    @app.post('/v1/chat/completions')
    async def chat(request: Request):
        parsed=ChatRequest.model_validate(await read_body(request))
        payload=parsed.model_dump(exclude_none=True)
        payload.pop('stream_options',None);payload['stream']=False
        # DeepSeek accepts text strings for all four roles; flatten text-only parts.
        for m in payload['messages']:
            if m['role']=='assistant' and 'content' not in m: m['content']=None
            if isinstance(m.get('content'),list):m['content']='\n'.join(p['text'] for p in m['content'])
        result=await service.call(request.state.principal,payload,stage='chat',exact_secrets=(request.headers['authorization'][7:],),charge_attempt=False)
        request.state.request_id=result.request_id
        if parsed.stream:
            return StreamingResponse(encode_sse(result,model=parsed.model,include_usage=bool(parsed.stream_options and parsed.stream_options.include_usage)),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
        return completion(result,parsed.model)
    @app.post('/v1/security/reviews')
    async def security_review(request: Request):
        from .review import review
        parsed=ReviewRequest.model_validate(await read_body(request))
        result=await review(parsed,request.state.principal,service,exact_secrets=(request.headers['authorization'][7:],),charge_attempt=False)
        request.state.request_id=result.request_id
        return result.model_dump()
    return app
