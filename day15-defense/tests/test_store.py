import tempfile
from pathlib import Path
import unittest
from runner.store import JobStore, StoreError
from runner.gate import POLICY_HASH
from runner.contracts import GateDecision

class StoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=JobStore(Path(self.tmp.name)/'jobs.db');self.job=self.store.create('a'*64)
 def tearDown(self):self.tmp.cleanup()
 def test_budget_is_persistent_and_atomic(self):
  self.store.reserve(self.job,40_000_000)
  with self.assertRaises(StoreError):self.store.reserve(self.job,11_000_000)
  reopened=JobStore(self.store.path)
  with self.assertRaises(StoreError):reopened.reserve(self.job,11_000_000)
 def test_gate_binds_snapshot(self):
  with self.assertRaises(StoreError):self.store.record_gate(self.job,GateDecision('pass','b'*64,'b'*64,POLICY_HASH,()))
  self.assertNotEqual(self.store.status(self.job)['state'],'accepted_candidate')
 def test_new_snapshot_invalidates_gate_and_iterations_bounded(self):
  self.store.begin_iteration(self.job,'a'*64)
  self.store.record_gate(self.job,GateDecision('pass','a'*64,'a'*64,POLICY_HASH,()))
  self.store.begin_iteration(self.job,'b'*64)
  self.assertIsNone(self.store.status(self.job)['gate'])
  self.store.begin_iteration(self.job,'c'*64)
  with self.assertRaises(StoreError):self.store.begin_iteration(self.job,'d'*64)
 def test_unknown_and_terminal_job_rejected(self):
  with self.assertRaises(StoreError):self.store.status('bad')
  self.store.fail(self.job,'cancelled')
  with self.assertRaises(StoreError):self.store.begin_iteration(self.job,'a'*64)
 def test_late_gate_cannot_create_candidate(self):
  self.store.begin_iteration(self.job,'a'*64)
  with self.store.tx() as db:db.execute('UPDATE jobs SET created=0 WHERE id=?',(self.job,))
  with self.assertRaises(StoreError):self.store.record_gate(self.job,GateDecision('pass','a'*64,'a'*64,POLICY_HASH,()))
 def test_recovery_clears_inflight_authority(self):
  self.store.begin_iteration(self.job,'a'*64)
  JobStore(self.store.path).recover()
  self.assertEqual(self.store.status(self.job)['state'],'error')
  self.assertIsNone(self.store.status(self.job)['gate'])
