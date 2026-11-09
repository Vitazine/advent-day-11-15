import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from gateway.service import GatewayService
from gateway.ledger import Ledger
from gateway.auth import Principal
from gateway.errors import GatewayError
from tests.support import make_settings, FakeProvider, chat_payload

class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.settings=make_settings(self.tmp.name)
        self.db=Ledger(Path(self.tmp.name)/'test.db');self.provider=FakeProvider()
        self.service=GatewayService(self.settings,self.provider,self.db);self.principal=Principal('test')
    def tearDown(self):self.tmp.cleanup()
    async def call(self,p=None,stage='chat'):return await self.service.call(self.principal,p or chat_payload(),stage=stage)
    async def test_input_block_zero_calls(self):
        p=chat_payload();p['messages'][0]['content']='sk-proj-synthetic123'
        with self.assertRaises(GatewayError) as e:await self.call(p)
        self.assertEqual(e.exception.code,'INPUT_BLOCKED');self.assertEqual(self.provider.calls,[])
        self.assertNotIn('sk-proj-synthetic123',str(self.db.events()))
    async def test_output_block_no_payload(self):
        self.provider.result.message['content']='sk-proj-synthetic123'
        with self.assertRaises(GatewayError):await self.call()
        self.assertGreater(self.db.limits('test')['key']['spent_nano'],0)
        self.assertNotIn('sk-proj-synthetic123',str(self.db.events()))
    async def test_audit_failure(self):
        with patch.object(self.db,'reserve',side_effect=OSError('PRIVATE')):
            with self.assertRaises(GatewayError):await self.call()
        self.assertEqual(self.provider.calls,[])
    async def test_cancel_releases_slot(self):
        self.provider.wait=asyncio.Event();task=asyncio.create_task(self.call())
        await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.db.limits('test')['key']['active'],0)
        self.assertGreater(self.db.limits('test')['key']['unknown_nano'],0)
    async def test_single_accounting(self):
        await self.call(stage='review')
        self.assertEqual(len(self.provider.calls),1)
        self.assertEqual(self.db.limits('test')['key']['spent_nano'],9000)
    async def test_stale_price(self):
        self.settings.price_date='2020-01-01'
        with self.assertRaises(GatewayError):await self.call()
        self.assertEqual(self.provider.calls,[])

    async def test_actual_model_is_inspected(self):
        self.settings.model='sk-proj-synthetic-model'
        with self.assertRaises(GatewayError) as e:await self.call()
        self.assertEqual(e.exception.code,'INPUT_BLOCKED')
        self.assertEqual(self.provider.calls,[])
