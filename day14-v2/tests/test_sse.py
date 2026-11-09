import json
from tests import test_chat_api as base
class SSETests(base.ApiCase):
    def test_sse(self):
        p=dict(__import__('tests.support',fromlist=['chat_payload']).chat_payload(),stream=True,stream_options={'include_usage':True})
        r=self.send(p);self.assertEqual(r.status_code,200)
        events=[s[6:] for s in r.text.split('\n\n') if s.startswith('data: ')]
        self.assertEqual(events[-1],'[DONE]')
        chunks=[json.loads(s) for s in events[:-1]]
        self.assertEqual(chunks[-1]['choices'],[])
        self.assertEqual(''.join(c['choices'][0]['delta'].get('content','') for c in chunks[:-1]),'Hello')
    def test_stream_blocked_before_start(self):
        self.provider.result.message['content']='Hello sk-proj-synthetic123'
        p=__import__('tests.support',fromlist=['chat_payload']).chat_payload();p['stream']=True
        r=self.send(p);self.assertEqual(r.status_code,422)
        self.assertNotIn('text/event-stream',r.headers['content-type']);self.assertNotIn('Hello',r.text)
    def test_multiple_tool_sse(self):
        calls=[{'id':'call_'+str(i),'type':'function','function':{'name':'read','arguments':json.dumps({'path':f'{i}.py'})}} for i in range(2)]
        self.provider.result.message={'role':'assistant','content':None,'tool_calls':calls};self.provider.result.finish_reason='tool_calls'
        p=__import__('tests.support',fromlist=['chat_payload']).chat_payload();p['stream']=True
        p['tools']=[{'type':'function','function':{'name':'read','parameters':{'type':'object'}}}]
        r=self.send(p);self.assertEqual(r.status_code,200);deltas=[json.loads(s[6:]) for s in r.text.split('\n\n') if s.startswith('data: {')]
        actual=[t for c in deltas for t in c['choices'][0]['delta'].get('tool_calls',[])]
        self.assertEqual([t['index'] for t in actual],[0,1])
        self.assertEqual(actual[1]['function']['arguments'],calls[1]['function']['arguments'])
