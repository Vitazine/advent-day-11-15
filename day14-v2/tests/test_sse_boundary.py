import asyncio
import tempfile
import unittest
import json
from pathlib import Path
from gateway.app import create_app
from gateway.service import GatewayService
from gateway.ledger import Ledger
from tests.support import make_settings,FakeProvider,TOKEN,chat_payload

class WireBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_asgi_response_before_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=make_settings(tmp);provider=FakeProvider();provider.wait=asyncio.Event()
            provider.result.message['content']='sk-proj-synthetic123'
            app=create_app(settings,GatewayService(settings,provider,Ledger(Path(tmp)/'test.db')))
            request_event=asyncio.Queue();await request_event.put({'type':'http.request','body':json.dumps(dict(chat_payload(),stream=True)).encode(),'more_body':False})
            sent=[]
            async def send(event):sent.append(event)
            scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','scheme':'http','path':'/v1/chat/completions','raw_path':b'/v1/chat/completions','query_string':b'','root_path':'','headers':[(b'authorization',('Bearer '+TOKEN).encode()),(b'content-type',b'application/json')],'server':('test',80),'client':('127.0.0.1',1)}
            task=asyncio.create_task(app(scope,request_event.get,send))
            for _ in range(100):
                if provider.calls:break
                await asyncio.sleep(.001)
            self.assertEqual(len(provider.calls),1);self.assertEqual(sent,[])
            provider.wait.set();await asyncio.wait_for(task,2)
            self.assertEqual(sent[0]['status'],422)
            self.assertNotIn(b'sk-proj-synthetic123',b''.join(m.get('body',b'') for m in sent))

    async def test_disconnect_finishes_bounded_call(self):
        # Policy: a departed HTTP client does not discard a provider result/known usage.
        with tempfile.TemporaryDirectory() as tmp:
            settings=make_settings(tmp);provider=FakeProvider();provider.wait=asyncio.Event()
            db=Ledger(Path(tmp)/'test.db');app=create_app(settings,GatewayService(settings,provider,db))
            queue=asyncio.Queue();await queue.put({'type':'http.request','body':json.dumps(chat_payload()).encode(),'more_body':False})
            async def send(event):pass
            scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','scheme':'http','path':'/v1/chat/completions','raw_path':b'/v1/chat/completions','query_string':b'','root_path':'','headers':[(b'authorization',('Bearer '+TOKEN).encode()),(b'content-type',b'application/json')],'server':('test',80),'client':('127.0.0.1',1)}
            task=asyncio.create_task(app(scope,queue.get,send))
            for _ in range(100):
                if provider.calls:break
                await asyncio.sleep(.001)
            await queue.put({'type':'http.disconnect'})
            provider.wait.set();await asyncio.wait_for(task,2)
            self.assertEqual(db.limits('test')['key']['active'],0)
            self.assertEqual(db.limits('test')['key']['spent_nano'],9000)
