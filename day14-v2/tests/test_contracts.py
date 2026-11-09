import json
import unittest
from pydantic import ValidationError
from gateway.contracts import ChatRequest, ReviewRequest, parse_json
from gateway.errors import GatewayError


def chat(**kw):
    return dict(model='day14-coder', messages=[{'role':'user','content':'hello'}], **kw)

class ContractsTests(unittest.TestCase):
    def test_chat(self):
        self.assertEqual(ChatRequest.model_validate(chat()).model, 'day14-coder')
        for kw in ({'n':2}, {'base_url':'https://example.invalid'}, {'max_tokens':8193}, {'stream':'yes'}):
            with self.subTest(kw=kw), self.assertRaises(ValidationError): ChatRequest.model_validate(chat(**kw))
    def test_counts(self):
        for n in (200,201):
            p=chat();p['messages']*=n
            if n==200: ChatRequest.model_validate(p)
            else:
                with self.assertRaises(ValidationError): ChatRequest.model_validate(p)
    def test_parser(self):
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'\xff', b'['*33+b'0'+b']'*33):
            with self.subTest(raw=raw[:30]), self.assertRaises(GatewayError): parse_json(raw)
        self.assertEqual(parse_json(b'['*32+b'0'+b']'*32), json.loads('['*32+'0'+']'*32))
    def test_review_paths(self):
        for path in ('../a','/a','a/../b','a\\b','a/./b'):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                ReviewRequest.model_validate({'stack_profile':'python-fastapi','files':[{'path':path,'content':'x'}]})

    def test_tool_count_and_nontext(self):
        for n in (64,65):
            p=chat();p['tools']=[{'type':'function','function':{'name':'f'+str(i),'parameters':{'type':'object'}}} for i in range(n)]
            if n==64:ChatRequest.model_validate(p)
            else:
                with self.assertRaises(ValidationError):ChatRequest.model_validate(p)
        p=chat();p['messages'][0]['content']=[{'type':'image_url','image_url':{'url':'x'}}]
        with self.assertRaises(ValidationError):ChatRequest.model_validate(p)
    def test_review_count_duplicates(self):
        for n in (0,21):
            with self.assertRaises(ValidationError):ReviewRequest.model_validate({'stack_profile':'python-fastapi','files':[{'path':f'{i}.py','content':'x'} for i in range(n)]})
        with self.assertRaises(ValidationError):ReviewRequest.model_validate({'stack_profile':'python-fastapi','files':[{'path':'a.py','content':'x'}]*2})
