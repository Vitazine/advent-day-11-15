import hashlib
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from gateway.config import Settings
from gateway.app import create_app

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.token='test.'+'a'*43
        self.settings=Settings(data_dir=Path(self.tmp.name), token_hashes={'test':hashlib.sha256(self.token.encode()).hexdigest()})
        self.client=TestClient(create_app(self.settings))
    def tearDown(self): self.client.close();self.tmp.cleanup()
    def test_auth(self):
        self.assertEqual(self.client.get('/v1/models').status_code,401)
        r=self.client.get('/v1/models',headers={'Authorization':'Bearer '+self.token})
        self.assertEqual(r.json()['data'][0]['id'],'day14-coder')
    def test_invalid_and_unknown(self):
        r=self.client.get('/v1/models',headers={'Authorization':'Bearer secret'})
        self.assertNotIn('secret',r.text)
        self.assertEqual(r.status_code,401)
    def test_spoofed_limiter(self):
        codes=[self.client.get('/v1/models',headers={'X-Forwarded-For':str(i)}).status_code for i in range(31)]
        self.assertEqual(codes[-1],429)
