"""Bounded repair loop. Only trusted code moves jobs toward acceptance."""
import fcntl
from pathlib import Path
from .snapshot import SnapshotStore
from .store import JobStore,StoreError
from .checks import StaticChecks
from .gateway_client import GatewayClient
from .review_client import ReviewClient
from .gate import Gate
from .opencode import OpenCodeGenerator

class Runner:
 def __init__(self,root,sandbox,token,*,generator=None,reviewer=None):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.snapshots=SnapshotStore(self.root/'snapshots');self.jobs=JobStore(self.root/'jobs.db')
  self.sandbox,self.token=sandbox,token
  self.generator=generator or OpenCodeGenerator();self.reviewer=reviewer
 def run(self,request):
  if request.profile!='python-fastapi' or not isinstance(request.task,str) or len(request.task)>8192:raise StoreError('INVALID_REQUEST')
  with (self.root/'runner.lock').open('a') as lock:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:raise StoreError('BUSY') from None
   self.jobs.recover()
   snap=self.snapshots.create(request.source);job=self.jobs.create(snap.id)
   client=GatewayClient(self.token,self.jobs,job)
   review=self.reviewer or ReviewClient(client).review
   feedback=()
   try:
    for iteration in range(3):
     if request.task:
      proposed=self.generator.generate(snap,request.task,feedback,client)
      snap=self.snapshots.from_files(proposed)
     self.jobs.begin_iteration(job,snap.id)
     checks=StaticChecks.run(snap)
     execution=self.sandbox.run(snap)
     result=review(snap)
     decision=Gate.evaluate(snap,checks,execution,result)
     self.jobs.record_gate(job,decision)
     if decision.status=='pass':break
     feedback=tuple(sorted(set(decision.reason_codes+checks.reason_codes+execution.reason_codes)))
     if not request.task or iteration==2:
      self.jobs.fail(job,'denied');break
   except KeyboardInterrupt:
    self.jobs.fail(job,'cancelled');raise
   except Exception:
    self.jobs.fail(job,'error')
   return self.jobs.status(job)
