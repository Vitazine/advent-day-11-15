"""One bounded direct HTTPS call. No SDK debug logs, retries, redirects or proxy env."""
import asyncio
import json
import httpx
from .guards import SYSTEM_PROMPT

class ProviderError(Exception): pass


def usage_cost(usage):
    required=('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')
    if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or not 0<=usage[k]<=2_000_000 for k in required):
        raise ProviderError('Invalid usage')
    if usage['prompt_tokens']!=usage['prompt_cache_hit_tokens']+usage['prompt_cache_miss_tokens']:
        raise ProviderError('Invalid usage')
    if usage['total_tokens']!=usage['prompt_tokens']+usage['completion_tokens']:
        raise ProviderError('Invalid usage')
    # Integer nanodollars at peak rates: 0.006 / 0.30 / 1.20 USD per million.
    return usage['prompt_cache_hit_tokens']*6+usage['prompt_cache_miss_tokens']*300+usage['completion_tokens']*1200


def reservation(prompt):
    # Conservative byte estimate plus framing allowance, not a tokenizer guarantee.
    return (len(prompt.encode('utf-8'))+len(SYSTEM_PROMPT.encode())+2048)*300+512*1200


class Provider:
    def __init__(self, key): self._key=key

    async def complete(self, prompt):
        body={'model':'deepseek-flash','messages':[{'role':'system','content':SYSTEM_PROMPT},
              {'role':'user','content':prompt}], 'stream':False,'max_tokens':512,'thinking':{'type':'disabled'}}
        try:
            async with asyncio.timeout(60):
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=55) as client:
                    async with client.stream('POST','https://api.deepseek.com/chat/completions',
                                             headers={'Authorization':'Bearer '+self._key},json=body) as response:
                        if response.status_code!=200: raise ProviderError('Upstream rejected')
                        raw=bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw)>1024*1024: raise ProviderError('Response too large')
                data=json.loads(raw)
            choice=data['choices'][0]
            text=choice['message']['content']
            if not isinstance(text,str) or len(text.encode('utf-8'))>32768: raise ProviderError('Invalid content')
            if choice.get('finish_reason') not in ('stop','length'): raise ProviderError('Unexpected result')
            usage=data['usage']; usage_cost(usage)
            usage={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')}
            return text,usage
        except Exception:
            raise ProviderError('Provider unavailable') from None
