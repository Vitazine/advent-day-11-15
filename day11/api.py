"""Bounded direct HTTPS, no proxy, redirect, retry, or HTTP debug output."""
import json
import ssl
from urllib.request import build_opener, Request, ProxyHandler, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError
from .contracts import SETTINGS

BASE = 'https://api.deepseek.com'
MAX_RESPONSE = 1024 * 1024
MAX_REQUEST = 16 * 1024

class ApiStop(Exception):
    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.reason, self.status = reason, status

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class DeepSeekClient:
    def __init__(self, api_key: str):
        if not api_key or any(c.isspace() for c in api_key):
            raise ApiStop('Некорректный ключ')
        self.__key = api_key
        self._opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())

    def _request(self, path: str, payload: dict | None = None) -> dict:
        if path not in ('/models', '/chat/completions'):
            raise ApiStop('Endpoint запрещён')
        try:
            data = None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
            if data is not None and (len(data)>MAX_REQUEST or self.__key.encode() in data):
                raise ApiStop('Небезопасное или слишком большое тело запроса')
            request = Request(BASE+path, data=data, headers={'Authorization':'Bearer '+self.__key, 'Content-Type':'application/json'})
            with self._opener.open(request, timeout=60) as response:
                raw = response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:
                raise ApiStop('Ответ превышает лимит')
            result=json.loads(raw)
            # Check decoded representation too, in case the service escapes characters.
            if self.__key in json.dumps(result,ensure_ascii=False):
                raise ApiStop('Ответ содержит секрет; сохранение запрещено')
            if not isinstance(result,dict) or result.get('error') or result.get('warning') or result.get('warnings'):
                raise ApiStop('Ошибка или предупреждение провайдера')
            return result
        except ApiStop:
            raise
        except HTTPError as error:
            status=error.code
            raise ApiStop('HTTP: запуск остановлен',status) from None
        except Exception:
            raise ApiStop('Сетевая ошибка или некорректный ответ') from None

    def list_models(self) -> list[dict]:
        result=self._request('/models')
        data=result.get('data')
        if not isinstance(data,list) or any(not isinstance(m,dict) or not isinstance(m.get('id'),str) for m in data):
            raise ApiStop('Некорректный список моделей')
        # Only benign identity and capability fields enter the manifest.
        return [{k:m[k] for k in ('id','name','context_window','max_output_tokens','effort') if k in m} for m in data]

    def complete(self,messages: list[dict[str,str]],settings: dict) -> dict:
        if settings != SETTINGS:
            raise ApiStop('Настройки не совпадают с согласованными')
        result=self._request('/chat/completions',{**settings,'messages':messages})
        try:
            choice=result['choices'][0]
            content=choice['message'].get('content')
            if content is not None and not isinstance(content,str):
                raise ValueError()
            usage=result.get('usage') or {}
            safe_usage={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens') if type(usage.get(k)) is int and usage[k]>=0}
            reason=choice['finish_reason']
            if not isinstance(reason,str) or not isinstance(result.get('model'),str):
                raise ValueError()
            return {'id':str(result.get('id','')), 'model':result['model'], 'content':content or '',
                    'finish_reason':reason,'usage':safe_usage,
                    'reasoning_present':bool(choice['message'].get('reasoning_content'))}
        except (KeyError, IndexError, TypeError, ValueError):
            raise ApiStop('Некорректная структура генерации') from None
