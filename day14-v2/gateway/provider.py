"""Only outbound HTTP boundary. Full responses are buffered before use."""
import asyncio
import json
from dataclasses import dataclass
import httpx
from .contracts import Message, Usage, parse_json
from .errors import GatewayError

@dataclass
class ProviderResult:
    message: dict
    finish_reason: str
    usage: Usage

class ProviderFailure(GatewayError):
    def __init__(self,code='UPSTREAM_ERROR',status=502,usage=None):
        super().__init__(code,status);self.usage=usage

def usage_cost(usage,settings):
    return usage.prompt_cache_hit_tokens*settings.cache_rate+usage.prompt_cache_miss_tokens*settings.input_rate+usage.completion_tokens*settings.output_rate

def estimate_reservation(payload,settings):
    size=len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())
    if size>256*1024:raise GatewayError('BODY_TOO_LARGE',413)
    output=payload.get('max_tokens',4096)
    if type(output)!=int or not 1<=output<=8192:raise GatewayError('INVALID_REQUEST')
    tokens=size+2048
    if tokens+output>settings.context_limit:raise GatewayError('CONTEXT_TOO_LARGE',413)
    return tokens*settings.input_rate+output*settings.output_rate

class Provider:
    def __init__(self,settings,transport=None):self.settings=settings;self.transport=transport
    async def complete(self,payload):
        body=dict(payload,model=self.settings.model,stream=False,thinking={'type':'disabled'})
        body.pop('stream_options',None);body.pop('n',None)
        usage=None
        failure_code='UPSTREAM_ERROR'
        try:
            async with asyncio.timeout(self.settings.timeout):
                async with httpx.AsyncClient(transport=self.transport,trust_env=False,follow_redirects=False,timeout=self.settings.timeout) as client:
                    async with client.stream('POST','https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+self.settings.api_key},json=body) as r:
                        if r.status_code!=200:raise ProviderFailure()
                        raw=bytearray()
                        async for chunk in r.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw)>1024*1024:raise ProviderFailure('UPSTREAM_TOO_LARGE')
            failure_code='UPSTREAM_INVALID_JSON'
            data=parse_json(bytes(raw),limit=1024*1024)
            # Provider may add metadata; only explicitly supported usage fields survive.
            failure_code='UPSTREAM_INVALID_USAGE'
            usage=Usage.model_validate({k:data['usage'][k] for k in Usage.model_fields})
            failure_code='UPSTREAM_INVALID_CHOICES'
            if len(data['choices'])!=1:raise ValueError('choices')
            choice=data['choices'][0];source=choice['message'];finish=choice['finish_reason']
            # Non-requested reasoning is neither returned nor logged.
            failure_code='UPSTREAM_INVALID_MESSAGE'
            normalized={k:source[k] for k in ('role','content','tool_calls') if k in source}
            if isinstance(normalized.get('tool_calls'),list):
                normalized['tool_calls']=[{
                    'id':call['id'], 'type':call['type'],
                    'function':{k:call['function'][k] for k in ('name','arguments')}
                } for call in normalized['tool_calls']]
            message=Message.model_validate(normalized)
            if isinstance(message.content,list):raise ValueError('content type')
            failure_code='UPSTREAM_INVALID_FINISH'
            if message.role!='assistant' or finish not in ('stop','length','tool_calls'):raise ValueError('finish')
            if message.tool_calls:
                if finish!='tool_calls':raise ValueError('truncated tools')
                if len({t.id for t in message.tool_calls})!=len(message.tool_calls):raise ValueError('duplicate tool')
                failure_code='UPSTREAM_INVALID_ARGUMENTS'
                for call in message.tool_calls:
                    args=parse_json(call.function.arguments.encode(),limit=1024*1024)
                    if not isinstance(args,dict):raise ValueError('arguments')
            elif finish=='tool_calls':raise ValueError('missing tools')
            clean=message.model_dump(exclude_none=True)
            if message.content is None:clean['content']=None
            return ProviderResult(clean,finish,usage)
        except (TimeoutError,httpx.TimeoutException):raise ProviderFailure('UPSTREAM_TIMEOUT',504,usage) from None
        except ProviderFailure:raise
        except Exception:raise ProviderFailure(failure_code,usage=usage) from None
