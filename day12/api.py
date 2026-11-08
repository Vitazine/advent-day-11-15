import json
import ssl
import time
from urllib.request import build_opener, Request, ProxyHandler, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError
from .budget import Stop

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None

class Client:
    def __init__(self,key):
        if not key or any(c.isspace() for c in key): raise Stop('Invalid credential')
        self.__key=key; self.last=0
        self.opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
    def check_safe(self,obj):
        if self.__key in json.dumps(obj,ensure_ascii=False): raise Stop('Secret reflection; content discarded')
    def request(self,path,payload=None):
        if path not in ('/models','/chat/completions'): raise Stop('Endpoint forbidden')
        self.check_safe(payload)
        data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
        if data and len(data)>16384: raise Stop('Request exceeds 16 KiB safety cap')
        try:
            req=Request('https://api.deepseek.com'+path,data=data,headers={'Authorization':'Bearer '+self.__key,'Content-Type':'application/json'})
            with self.opener.open(req,timeout=60) as r: raw=r.read(1048577)
            if len(raw)>1048576: raise Stop('Oversize response')
            result=json.loads(raw); self.check_safe(result)
            if not isinstance(result,dict) or any(result.get(k) for k in ('error','warning','warnings')): raise Stop('Provider error/warning')
            return result
        except HTTPError as e: raise Stop('HTTP '+str(e.code)+'; stopped, no retry') from None
        except Stop: raise
        except Exception: raise Stop('Transport or response error; stopped, no retry') from None
    def list_models(self):
        data=self.request('/models').get('data')
        if not isinstance(data,list): raise Stop('Invalid models')
        return [{'id':m.get('id')} for m in data if isinstance(m,dict)]
    def complete(self,messages,tools,ledger,choice=None):
        payload={'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':0.2,'max_tokens':768,'stream':False,'messages':messages,'tools':tools}
        if choice: payload['tool_choice']=choice
        self.check_safe(payload)
        n=len(json.dumps(payload,ensure_ascii=False).encode())
        if n>16384: raise Stop('Request exceeds safety cap')
        rid=ledger.reserve(n,768)
        time.sleep(max(0,5-(time.monotonic()-self.last))); self.last=time.monotonic()
        r=self.request('/chat/completions',payload)
        try:
            ch=r['choices'][0]; msg=ch['message']; reason=ch['finish_reason']
            content=msg.get('content'); calls=msg.get('tool_calls',[])
            if content is not None and not isinstance(content,str): raise ValueError()
            if not isinstance(calls,list) or len(calls)>16: raise ValueError()
            for c in calls:
                if not isinstance(c.get('id'),str) or c.get('type')!='function' or not isinstance(c['function']['name'],str) or not isinstance(c['function']['arguments'],str): raise ValueError()
            usage={k:v for k,v in r['usage'].items() if type(v) is int and v>=0}
            ledger.settle(rid,usage)
            result={'message':{'role':'assistant','content':content},'finish_reason':reason,'model':r['model'],'usage':usage,'reservation_id':rid}
            if calls: result['message']['tool_calls']=calls
            if r['model']!='deepseek-flash': raise Stop('Unexpected model identity')
            return result
        except Stop: raise
        except Exception: raise Stop('Invalid completion structure') from None
