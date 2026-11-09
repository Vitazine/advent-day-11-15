import hashlib
from datetime import date
from pathlib import Path
from gateway.config import Settings
from gateway.contracts import Usage
from gateway.provider import ProviderResult

TOKEN='test.'+'a'*43
HEADERS={'Authorization':'Bearer '+TOKEN}
def make_settings(path):
    return Settings(data_dir=Path(path),token_hashes={'test':hashlib.sha256(TOKEN.encode()).hexdigest()},api_key='synthetic-config-secret',price_date=date.today().isoformat())
def chat_payload():return {'model':'day14-coder','messages':[{'role':'user','content':'Say hello'}]}
def usage():return Usage(prompt_tokens=10,completion_tokens=5,total_tokens=15,prompt_cache_hit_tokens=0,prompt_cache_miss_tokens=10)
class FakeProvider:
    def __init__(self):self.calls=[];self.result=ProviderResult({'role':'assistant','content':'Hello'},'stop',usage());self.failure=None;self.wait=None
    async def complete(self,payload):
        self.calls.append(payload)
        if self.wait:await self.wait.wait()
        if self.failure:raise self.failure
        return self.result
