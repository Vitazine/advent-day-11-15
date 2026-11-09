"""Fixed-destination gateway transport with persistent worst-case reservations."""
from datetime import date
import json
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import HTTPError

BASE_URL='https://just-black-coffe.shop/day14-v2/v1/'
class GatewayFailure(RuntimeError):pass
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

class GatewayClient:
 def __init__(self,token,store,job_id,transport=None):
  self.token,self.store,self.job_id=token,store,job_id
  self.transport=transport or self._http
 def _http(self,route,body):
  request=Request(BASE_URL+route,data=body,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'},method='POST')
  opener=build_opener(ProxyHandler({}),NoRedirect())
  try:response=opener.open(request,timeout=120)
  except HTTPError as error:response=error
  with response:
   raw=response.read(4*1024*1024+1)
   if len(raw)>4*1024*1024:raise GatewayFailure('RESPONSE_LIMIT')
   return response.status,{'Content-Type':response.headers.get('Content-Type','application/json')},raw
 def request(self,route,payload):
  if route not in ('chat/completions','security/reviews'):raise GatewayFailure('ROUTE_DENIED')
  if not 0<=(date.today()-date(2026,11,8)).days<=7:raise GatewayFailure('STALE_PRICING')
  raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
  if len(raw)>256*1024:raise GatewayFailure('BODY_LIMIT')
  # Includes server-owned review prompt, JSON double-escaping and protocol overhead.
  # Reserve is intentionally not refunded: retries/unknown usage cannot reset it.
  maximum=8192 if route=='security/reviews' else payload.get('max_tokens',payload.get('max_completion_tokens',8192))
  if type(maximum)!=int or not 1<=maximum<=8192:raise GatewayFailure('OUTPUT_LIMIT')
  amount=(2*len(raw)+16384)*300+maximum*1200
  self.store.reserve(self.job_id,amount)
  try:return self.transport(route,raw)
  except Exception as exc:raise GatewayFailure('GATEWAY_UNAVAILABLE') from None
