import tempfile
import unittest
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from gateway.ledger import Ledger
from gateway.contracts import EventMeta
from gateway.errors import GatewayError

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1000000
        self.db=Ledger(Path(self.tmp.name)/'test.db',clock=lambda:self.now)
    def tearDown(self):self.tmp.cleanup()
    def reserve(self,k='a',amount=10):
        return self.db.reserve(k,amount,EventMeta(request_id=uuid.uuid4().hex,key_id=k,stage='chat',state='accepted'))
    def test_limits(self):
        for _ in range(10):self.db.attempt('a')
        with self.assertRaises(GatewayError):self.db.attempt('a')
        self.now+=60;self.db.attempt('a')
        self.assertEqual(self.db.limits('a')['key']['budget_nano'],100_000_000)
        with self.assertRaises(GatewayError):self.reserve(amount=100_000_001)
    def test_atomic_reservation(self):
        def run(_):
            try:self.reserve();return 1
            except GatewayError:return 0
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(sum(pool.map(run,range(4))),1)
        self.reserve('b')
        with self.assertRaises(GatewayError):self.reserve('c')
    def test_unknown_restart(self):
        self.reserve(amount=100)
        self.now+=90000
        self.assertEqual(self.db.limits('a')['key']['reserved_nano'],100)
        self.db.recover()
        self.assertEqual(self.db.limits('a')['key']['unknown_nano'],100)
        self.assertEqual(self.db.limits('a')['key']['active'],0)
    def test_finish_once(self):
        rid=self.reserve(amount=100)
        self.db.finish(rid,20,None,'completed',1)
        self.db.finish(rid,20,None,'completed',1)
        self.assertEqual(self.db.limits('a')['key']['spent_nano'],20)
    def test_halt(self):
        rid=self.reserve();self.db.finish(rid,100,None,'completed',1)
        with self.assertRaises(GatewayError):self.reserve()
    def test_cleanup(self):
        rid=self.reserve();self.db.finish(rid,1,None,'completed',1)
        self.now+=7*86400+1;self.db.cleanup()
        self.assertEqual(self.db.events(),[])
    def test_audit_cap(self):
        self.db.audit_cap=1
        with self.assertRaises(GatewayError):self.reserve()
        self.assertEqual(self.db.limits('a')['key']['active'],0)
    def test_metadata_only(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):EventMeta(request_id='r',key_id='a',stage='chat',state='accepted',prompt='secret')
