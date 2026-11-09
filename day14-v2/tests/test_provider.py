import json
import unittest
import httpx
from gateway.config import Settings
from gateway.provider import Provider, ProviderFailure, estimate_reservation, usage_cost

USAGE={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10}
def response(message=None,finish='stop',usage=None):
    return {'choices':[{'message':message or {'role':'assistant','content':'Hello'},'finish_reason':finish}], 'usage':USAGE if usage is None else usage}
class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):self.settings=Settings(api_key='synthetic-provider-key');self.calls=[]
    def provider(self,data,status=200):
        def handler(r):self.calls.append(r);return httpx.Response(status,json=data)
        return Provider(self.settings,transport=httpx.MockTransport(handler))
    async def test_fixed_upstream(self):
        r=await self.provider(response()).complete({'messages':[],'max_tokens':10})
        self.assertEqual(r.message['content'],'Hello')
        self.assertEqual(str(self.calls[0].url),'https://api.deepseek.com/chat/completions')
        body=json.loads(self.calls[0].content)
        self.assertFalse(body['stream']);self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertEqual(usage_cost(r.usage,self.settings),9000)
    async def test_no_retry(self):
        with self.assertRaises(ProviderFailure):await self.provider({},302).complete({})
        self.assertEqual(len(self.calls),1)
    async def test_invalid(self):
        cases=[response(usage={}),{'choices':[]}, response(finish='weird'),response({'role':'assistant','content':'x'*(1024*1024)})]
        for data in cases:
            with self.subTest(),self.assertRaises(ProviderFailure):await self.provider(data).complete({})
    async def test_truncated_tool_args(self):
        msg={'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'read','arguments':'{"path":'}}]}
        for finish in ('tool_calls','length'):
            with self.assertRaises(ProviderFailure):await self.provider(response(msg,finish)).complete({})
    async def test_reasoning_removed(self):
        msg={'role':'assistant','content':'hello','reasoning_content':'private'}
        r=await self.provider(response(msg)).complete({})
        self.assertNotIn('reasoning_content',r.message)
    def test_reservation(self):
        self.assertGreater(estimate_reservation({'messages':[],'max_tokens':8192},self.settings),8192*1200)
        self.settings.context_limit=10
        with self.assertRaises(Exception):estimate_reservation({'messages':[]},self.settings)

    async def test_assistant_content_array_rejected(self):
        with self.assertRaises(ProviderFailure):
            await self.provider(response({'role':'assistant','content':[{'type':'text','text':'hello'}]})).complete({})

    async def test_safe_structural_error_code(self):
        msg={'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'read','arguments':'PRIVATE_INVALID_JSON'}}]}
        with self.assertRaises(ProviderFailure) as failure:
            await self.provider(response(msg,'tool_calls')).complete({})
        self.assertEqual(failure.exception.code,'UPSTREAM_INVALID_ARGUMENTS')
        self.assertNotIn('PRIVATE',str(failure.exception))

    async def test_deepseek_tool_index_is_normalized(self):
        msg={'role':'assistant','content':'','tool_calls':[{'index':0,'id':'call_1','type':'function','function':{'name':'get_status','arguments':'{}'}}]}
        result=await self.provider(response(msg,'tool_calls')).complete({})
        self.assertEqual(result.finish_reason,'tool_calls')
        self.assertNotIn('index',result.message['tool_calls'][0])
        self.assertEqual(result.message['tool_calls'][0]['function']['arguments'],'{}')
