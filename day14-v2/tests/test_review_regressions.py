import json
import tempfile
import unittest
from pathlib import Path
from gateway.guards import inspect_payload
from gateway.ledger import Ledger
from gateway.contracts import EventMeta
from tests import test_chat_api as base
from tests.support import chat_payload

class ScannerRegressions(unittest.TestCase):
    def test_nested_json_fragment(self):
        p={'tool_calls':[{'function':{'arguments':'{"a":"sk-","b":"proj-synthetic123"}'}}]}
        self.assertFalse(inspect_payload(p,direction='output').allowed)
    def test_schema_key_fragment(self):
        p={'parameters':{'properties':{'synthetic-':{},'config-secret':{}}}}
        self.assertFalse(inspect_payload(p,direction='input',exact_secrets=('synthetic-config-secret',)).allowed)
    def test_numeric_pii(self):
        self.assertFalse(inspect_payload({'const':4111111111111111},direction='input').allowed)
    def test_audit_reserved_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Ledger(Path(tmp)/'db',audit_cap=6000)
            db.reserve('test',100,EventMeta(request_id='a',key_id='test',stage='chat',state='accepted'))
            db.finish('a',1,None,'completed',1)
            self.assertEqual(db.limits('test')['key']['active'],0)
            self.assertEqual(db.limits('test')['key']['spent_nano'],1)

class HttpRegressions(base.ApiCase):
    def test_bad_attempts_rate_limited(self):
        p=chat_payload();p['unsupported']=True
        codes=[self.send(p).status_code for _ in range(11)]
        self.assertEqual(codes[-1],429)
    def test_nested_secret_never_returned(self):
        self.provider.result.message={'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'read','arguments':'{"a":"sk-","b":"proj-synthetic123"}'}}]}
        self.provider.result.finish_reason='tool_calls'
        self.assertEqual(self.send().status_code,422)

    def test_invalid_request_audited_without_payload(self):
        p=chat_payload();p['unsupported']='PRIVATE_INPUT'
        self.assertEqual(self.send(p).status_code,422)
        events=self.db.events()
        self.assertTrue(any(e['stage']=='http' and e['state']=='failed' for e in events))
        self.assertNotIn('PRIVATE_INPUT',str(events))
