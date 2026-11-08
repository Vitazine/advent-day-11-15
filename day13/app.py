"""Gateway API. nginx owns Basic Auth and overwrites X-Day13-IP."""
import asyncio
import json
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from .config import Settings
from .guards import protect, audit_text, Inspection
from .ledger import Ledger, LimitError
from .provider import Provider, reservation, usage_cost

STATIC=Path(__file__).parent/'static'
HEADERS={
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer',
    'X-Frame-Options':'DENY','Cache-Control':'no-store',
    'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
}
MESSAGES={
    'INPUT_BLOCKED':'В запросе обнаружены чувствительные данные. Вызов модели не выполнен.',
    'OUTPUT_BLOCKED':'Ответ модели заблокирован проверкой безопасности.',
    'INVALID_REQUEST':'Проверьте текст запроса и режим обработки.',
    'BODY_TOO_LARGE':'Запрос превышает допустимый размер.',
    'FORBIDDEN':'Запрос не разрешён.', 'UNAVAILABLE':'Генерация временно недоступна.',
    'UPSTREAM_ERROR':'Не удалось получить ответ. Возможные расходы зарезервированы; автоматического повтора нет.',
    'RATE_LIMIT':'Достигнут лимит запросов в минуту.', 'BUDGET_LIMIT':'Достигнут лимит расходов.',
    'BUSY':'Запрос уже выполняется. Дождитесь завершения.', 'SAFETY_HALT':'Генерация остановлена защитой бюджета.',
    'AUDIT_FULL':'Журнал заполнен; генерация временно остановлена.',
}

def error(code, status, categories=(), request_id=None):
    return JSONResponse({'error':{'code':code,'message':MESSAGES[code]},'categories':list(categories),
                         'request_id':request_id},status_code=status,headers=HEADERS)


def create_app(settings=None, provider=None, ledger=None):
    settings=settings or Settings.load()
    ledger=ledger or Ledger(settings.data_dir/'ledger.db')
    provider=provider or Provider(settings.api_key)
    async def maintenance():
        while True:
            await asyncio.sleep(300)
            try: ledger.cleanup()
            except Exception: pass  # Generation performs cleanup again and fails closed.
    @asynccontextmanager
    async def lifespan(app):
        ledger.recover(); ledger.cleanup()
        task=asyncio.create_task(maintenance())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError): await task
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)

    @app.middleware('http')
    async def boundary(request, call_next):
        try:
            response=await call_next(request)
        except Exception:
            response=error('UNAVAILABLE',503)
        if (request.method=='POST' and request.url.path=='/day13/api/generate'
            and not getattr(request.state,'audited',False)):
            try:
                try: client_id=identity(request)
                except ValueError: client_id='untrusted'
                ledger.record(client_id,'http_'+str(response.status_code),'[BODY_NOT_RETAINED]',())
            except Exception:
                response=error('UNAVAILABLE',503)
        for name,value in HEADERS.items(): response.headers[name]=value
        return response

    def identity(request):
        if not request.client or request.client.host not in ('127.0.0.1','::1'):
            raise ValueError('Untrusted peer')
        raw=request.headers.get('x-day13-ip','')
        if not raw or len(raw)>64: raise ValueError('Missing trusted IP')
        return settings.ip_id(raw)

    @app.get('/day13/')
    async def index(): return FileResponse(STATIC/'index.html')

    @app.get('/day13/{asset}')
    async def asset(asset):
        if asset not in ('app.css','app.js'): return error('FORBIDDEN',404)
        return FileResponse(STATIC/asset)

    @app.get('/day13/api/limits')
    async def limits(request: Request):
        try: ip=identity(request)
        except ValueError: return error('FORBIDDEN',403)
        result=ledger.limits(ip)
        result.update(ready=settings.ready and not result['halted'],price_date=settings.price_date,
                      max_prompt_bytes=8192,max_output_tokens=512)
        return result

    @app.post('/day13/api/generate')
    async def generate(request: Request):
        try: ip=identity(request)
        except ValueError: return error('FORBIDDEN',403)
        if (request.headers.get('x-day13-request')!='1' or
            request.headers.get('origin',settings.origin)!=settings.origin or
            request.headers.get('sec-fetch-site')=='cross-site'):
            return error('FORBIDDEN',403)
        if request.headers.get('content-type','').split(';')[0].strip()!='application/json':
            return error('INVALID_REQUEST',415)
        try:
            ledger.cleanup()
            ledger.attempt(ip)
        except LimitError as exc: return error(exc.code,429)
        except Exception: return error('UNAVAILABLE',503)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>16384: return error('BODY_TOO_LARGE',413)
        try:
            payload=json.loads(raw)
            if (not isinstance(payload,dict) or set(payload)!={'prompt','mode'} or
                not isinstance(payload['prompt'],str) or not payload['prompt'].strip() or
                payload['mode'] not in ('block','mask')):
                return error('INVALID_REQUEST',422)
            prompt=payload['prompt']
            if len(prompt.encode('utf-8'))>8192: return error('BODY_TOO_LARGE',413)
        except (ValueError,TypeError,UnicodeError): return error('INVALID_REQUEST',422)
        secrets=(settings.api_key,settings.ip_key.decode('ascii',errors='ignore'))
        result=protect(prompt,payload['mode'],secrets)
        if not result.allowed:
            ledger.record(ip,'input_blocked','[REDACTED_CONTENT]',result.categories)
            request.state.audited=True
            return error('INPUT_BLOCKED',422,result.categories)
        if not settings.ready: return error('UNAVAILABLE',503)
        # Defense in depth: don't forward a transformed fragment that still triggers DLP.
        if not protect(result.text,'block',secrets).allowed:
            return error('INPUT_BLOCKED',422,('AMBIGUOUS_MASK',))
        amount=reservation(result.text)
        try:
            rid=ledger.reserve(ip,amount,audit_text(result.text,secrets),result.categories)
            request.state.audited=True
        except LimitError as exc: return error(exc.code,429)
        except Exception: return error('UNAVAILABLE',503)
        started=time.monotonic()
        try:
            text,usage=await provider.complete(result.text)
            cost=usage_cost(usage)
        except (Exception,asyncio.CancelledError):
            ledger.finish(rid,amount,'',(),{},'unknown')
            return error('UPSTREAM_ERROR',502,request_id=rid)
        try:
            checked=protect(text,'block',secrets,output=True)
        except Exception:
            checked=Inspection('[BLOCKED_OUTPUT]',('INSPECTION_ERROR',),False)
        state='completed' if checked.allowed else 'output_blocked'
        ledger.finish(rid,cost,audit_text(text,secrets) if checked.allowed else '[BLOCKED_OUTPUT]',
                      tuple(sorted(set(result.categories+checked.categories))),usage,state,
                      int((time.monotonic()-started)*1000))
        if cost>amount: return error('SAFETY_HALT',503,request_id=rid)
        if not checked.allowed: return error('OUTPUT_BLOCKED',422,checked.categories,rid)
        return {'request_id':rid,'answer':checked.text,'categories':list(result.categories),
                'masked':bool(result.categories),'usage':usage,'cost_nano':cost,'limits':ledger.limits(ip)}
    return app
