import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from gateway.app import create_app
from gateway.service import GatewayService
from gateway.ledger import Ledger
from tests.support import make_settings,FakeProvider,HEADERS,chat_payload

class ApiCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.settings=make_settings(self.tmp.name)
        self.provider=FakeProvider();self.db=Ledger(Path(self.tmp.name)/'test.db')
        self.service=GatewayService(self.settings,self.provider,self.db)
        self.client=TestClient(create_app(self.settings,self.service));self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()
    def send(self,p=None):return self.client.post('/v1/chat/completions',json=p or chat_payload(),headers=HEADERS)

class ChatTests(ApiCase):
    def test_json(self):
        r=self.send();self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['choices'][0]['message']['content'],'Hello')
        self.assertEqual(r.headers['x-request-id'],r.json()['id'].removeprefix('chatcmpl-'))
    def test_tool_roundtrip(self):
        calls=[{'id':'call_1','type':'function','function':{'name':'read','arguments':'{"path":"a.py"}'}}]
        self.provider.result.message={'role':'assistant','content':None,'tool_calls':calls};self.provider.result.finish_reason='tool_calls'
        p=chat_payload();p['tools']=[{'type':'function','function':{'name':'read','parameters':{'type':'object'}}}]
        r=self.send(p);self.assertEqual(r.json()['choices'][0]['message']['tool_calls'],calls)
        p['messages'] += [r.json()['choices'][0]['message'],{'role':'tool','tool_call_id':'call_1','content':'safe code'}]
        self.assertEqual(self.send(p).status_code,200)
        self.assertEqual(self.provider.calls[-1]['messages'][-1]['tool_call_id'],'call_1')
    def test_body_limits(self):
        for raw,status in ((b'x'*(512*1024+1),413),(b'{"x":1,"x":2}',422),(b'\xff',422)):
            r=self.client.post('/v1/chat/completions',content=raw,headers=dict(HEADERS,**{'Content-Type':'application/json'}))
            self.assertEqual(r.status_code,status)
        self.assertEqual(self.provider.calls,[])
    def test_secret_and_unknown(self):
        p=chat_payload();p['messages'][0]['content']='sk-proj-synthetic123'
        r=self.send(p);self.assertEqual(r.status_code,422);self.assertNotIn('sk-proj-synthetic123',r.text)
        p=chat_payload();p['unsupported']=True;self.assertEqual(self.send(p).status_code,422)
    def test_limits_owned(self):
        r=self.client.get('/v1/limits',headers=HEADERS)
        self.assertEqual(r.status_code,200);self.assertNotIn('token_hashes',r.text)
