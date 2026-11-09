"""Local TCP smoke with a scripted provider; no paid requests."""
import json
import socket
import tempfile
import threading
import time
from pathlib import Path
import httpx
import uvicorn
from gateway.app import create_app
from gateway.service import GatewayService
from gateway.ledger import Ledger
from tests.support import make_settings,FakeProvider,HEADERS,chat_payload

def main():
    with tempfile.TemporaryDirectory() as tmp:
        settings=make_settings(tmp);provider=FakeProvider()
        app=create_app(settings,GatewayService(settings,provider,Ledger(Path(tmp)/'ledger.db')))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));sock.listen(16)
            port=sock.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,proxy_headers=False))
            thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
            try:
                for _ in range(100):
                    if server.started:break
                    time.sleep(.02)
                if not server.started:raise RuntimeError('server_start')
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers=HEADERS,trust_env=False,timeout=10) as client:
                    results={}
                    r=client.post('/v1/chat/completions',json=chat_payload());assert r.status_code==200;results['json']='pass'
                    r=client.post('/v1/chat/completions',json=dict(chat_payload(),stream=True));assert r.status_code==200 and '[DONE]' in r.text;results['sse']='pass'
                    p=chat_payload();p['messages'][0]['content']='sk-proj-synthetic123'
                    r=client.post('/v1/chat/completions',json=p);assert r.status_code==422 and 'sk-proj-synthetic123' not in r.text;results['input_block']='pass'
                    provider.result.message['content']='{"findings":[]}'
                    r=client.post('/v1/security/reviews',json={'stack_profile':'python-fastapi','files':[{'path':'a.py','content':'x=1'}]})
                    assert r.status_code==200 and r.json()['decision']=='pass';results['review']='pass'
                    provider.result.message['content']='sk-proj-synthetic123'
                    r=client.post('/v1/chat/completions',json=dict(chat_payload(),stream=True));assert r.status_code==422 and 'data:' not in r.text;results['output_block']='pass'
                    print(json.dumps({'mode':'synthetic','transport':'real-loopback-tcp','checks':results}))
            finally:
                server.should_exit=True;thread.join(5)
                if thread.is_alive():raise RuntimeError('server_shutdown')
if __name__=='__main__':main()
