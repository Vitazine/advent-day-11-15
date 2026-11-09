from pathlib import Path
import tempfile
import unittest
from runner.snapshot import SnapshotStore
from runner.store import JobStore,StoreError
from runner.gate import POLICY_HASH
from runner.contracts import GateDecision
from runner.accept import Acceptor

class AcceptTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.snapshots=SnapshotStore(self.root/'snapshots');self.snap=self.snapshots.from_files([('app.py','x=1')])
  self.jobs=JobStore(self.root/'jobs.db');self.job=self.jobs.create(self.snap.id)
  self.acceptor=Acceptor(self.jobs,self.snapshots,self.root/'accepted')
 def tearDown(self):self.tmp.cleanup()
 def approve(self):
  self.jobs.begin_iteration(self.job,self.snap.id)
  self.jobs.record_gate(self.job,GateDecision('pass',self.snap.id,self.snap.artifact_hash,POLICY_HASH,()))
 def test_review_cannot_be_skipped(self):
  with self.assertRaises(StoreError):self.acceptor.accept(self.job)
 def test_accept_is_idempotent_and_exact_bytes(self):
  self.approve();a=self.acceptor.accept(self.job);b=self.acceptor.accept(self.job)
  self.assertEqual(a,b);self.assertEqual(a.artifact_hash,self.snap.artifact_hash)
  self.assertEqual(self.jobs.status(self.job)['state'],'accepted')
 def test_tampered_snapshot_not_accepted(self):
  self.approve();p=self.root/'snapshots'/f'{self.snap.id}.json';p.chmod(0o600);p.write_text('[]')
  with self.assertRaises(ValueError):self.acceptor.accept(self.job)
  self.assertNotEqual(self.jobs.status(self.job)['state'],'accepted')
