"""Trusted persistent job journal and conservative spend reservations."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid
from .gate import POLICY_HASH

class StoreError(RuntimeError):pass

class JobStore:
 def __init__(self,path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  with self.tx() as db:
   db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,state TEXT,snapshot TEXT,iteration INTEGER,created REAL,reserved INTEGER,gate TEXT)')
  self.path.chmod(0o600)
 @contextmanager
 def tx(self):
  db=sqlite3.connect(self.path,timeout=5);db.row_factory=sqlite3.Row
  try:
   db.execute('BEGIN IMMEDIATE');yield db;db.commit()
  except BaseException:db.rollback();raise
  finally:db.close()
 def _row(self,db,job):
  if not isinstance(job,str) or not re.fullmatch('[0-9a-f]{32}',job):raise StoreError('UNKNOWN_JOB')
  row=db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
  if row is None:raise StoreError('UNKNOWN_JOB')
  return dict(row)
 def create(self,snapshot):
  if not re.fullmatch('[0-9a-f]{64}',snapshot):raise StoreError('INVALID_SNAPSHOT')
  job=uuid.uuid4().hex
  with self.tx() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(job,'created',snapshot,0,time.time(),0,None))
  return job
 def status(self,job):
  with self.tx() as db:row=self._row(db,job)
  if row['gate']:row['gate']=json.loads(row['gate'])
  return row
 def begin_iteration(self,job,snapshot):
  if not re.fullmatch('[0-9a-f]{64}',snapshot):raise StoreError('INVALID_SNAPSHOT')
  with self.tx() as db:
   row=self._row(db,job)
   if row['state'] in ('accepted','cancelled','error','denied') or row['iteration']>=3 or time.time()-row['created']>600:raise StoreError('JOB_LIMIT')
   db.execute("UPDATE jobs SET state='checking',snapshot=?,iteration=iteration+1,gate=NULL WHERE id=?",(snapshot,job))
 def reserve(self,job,amount):
  if type(amount)!=int or amount<=0:raise StoreError('INVALID_RESERVE')
  with self.tx() as db:
   row=self._row(db,job)
   total=db.execute('SELECT COALESCE(SUM(reserved),0) FROM jobs').fetchone()[0]
   if row['state'] in ('accepted','cancelled','error','denied') or time.time()-row['created']>600:raise StoreError('JOB_LIMIT')
   if row['reserved']+amount>50_000_000 or total+amount>1_000_000_000:raise StoreError('BUDGET_LIMIT')
   db.execute('UPDATE jobs SET reserved=reserved+? WHERE id=?',(amount,job))
 def record_gate(self,job,decision):
  with self.tx() as db:
   row=self._row(db,job)
   if time.time()-row['created']>600 or row['state']!='checking' or decision.snapshot_id!=row['snapshot'] or decision.artifact_hash!=row['snapshot'] or decision.policy_hash!=POLICY_HASH:raise StoreError('GATE_MISMATCH')
   state='accepted_candidate' if decision.status=='pass' else 'repairing'
   db.execute('UPDATE jobs SET state=?,gate=? WHERE id=?',(state,json.dumps(asdict(decision)),job))
 def fail(self,job,state='error'):
  if state not in ('error','cancelled','denied'):raise StoreError('INVALID_STATE')
  with self.tx() as db:
   row=self._row(db,job)
   if row['state']=='accepted':raise StoreError('ALREADY_ACCEPTED')
   db.execute('UPDATE jobs SET state=?,gate=NULL WHERE id=?',(state,job))
 def recover(self):
  # Call only while holding the runner process lock, never from a status request.
  with self.tx() as db:db.execute("UPDATE jobs SET state='error',gate=NULL WHERE state IN ('checking','repairing')")
