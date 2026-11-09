import asyncio
import json
import unittest
from tests import test_chat_api as base
from tests.support import HEADERS,chat_payload
from gateway.guards import inspect_payload

class Boundaries(base.ApiCase):
    def test_json_escaped_secret_in_arguments(self):
        escaped=''.join('\\u%04x'%ord(c) for c in 'sk-proj-synthetic123')
        p={'tool_calls':[{'function':{'arguments':'{"value":"'+escaped+'"}'}}]}
        self.assertFalse(inspect_payload(p,direction='output').allowed)
    def test_all_http_body_boundaries(self):
        raw=json.dumps(chat_payload()).encode()
        r=self.client.post('/v1/chat/completions',content=raw+b' '*(512*1024-len(raw)),headers=dict(HEADERS,**{'Content-Type':'application/json'}))
        self.assertEqual(r.status_code,200)
        r=self.client.post('/v1/chat/completions',content=raw+b' '*(512*1024+1-len(raw)),headers=dict(HEADERS,**{'Content-Type':'application/json'}))
        self.assertEqual(r.status_code,413)
    def test_null_content_tool_history(self):
        self.provider.result.message={'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'read','arguments':'{}'}}]}
        self.provider.result.finish_reason='tool_calls'
        p=chat_payload();p['tools']=[{'type':'function','function':{'name':'read','parameters':{'type':'object'}}}]
        r=self.send(p);p['messages'] += [r.json()['choices'][0]['message'],{'role':'tool','tool_call_id':'call_1','content':'ok'}]
        self.send(p)
        self.assertIn('content',self.provider.calls[-1]['messages'][1])
        self.assertIsNone(self.provider.calls[-1]['messages'][1]['content'])
