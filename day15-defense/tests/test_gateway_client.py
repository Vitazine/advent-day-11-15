import json
from pathlib import Path
import tempfile
import unittest
from runner.store import JobStore,StoreError
from runner.gateway_client import GatewayClient,GatewayFailure

class GatewayClientTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=JobStore(Path(self.tmp.name)/'db');self.job=self.store.create('a'*64)
 def tearDown(self):self.tmp.cleanup()
 def test_reserves_before_network_and_keeps_unknown_cost(self):
  def failed(*args):raise OSError('private')
  client=GatewayClient('synthetic',self.store,self.job,transport=failed)
  with self.assertRaises(GatewayFailure):client.request('chat/completions',{'messages':[],'max_tokens':128})
  self.assertGreater(self.store.status(self.job)['reserved'],0)
 def test_exhaustion_prevents_network(self):
  self.store.reserve(self.job,49_999_999)
  def forbidden(*args):self.fail('network must not run')
  client=GatewayClient('synthetic',self.store,self.job,transport=forbidden)
  with self.assertRaises(StoreError):client.request('chat/completions',{'messages':[]})
 def test_arbitrary_route_rejected(self):
  client=GatewayClient('synthetic',self.store,self.job)
  with self.assertRaises(GatewayFailure):client.request('https://example.com',{})
