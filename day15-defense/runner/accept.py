"""Atomic, idempotent acceptance of the exact reviewed source artifact."""
import hashlib
import json
import os
from pathlib import Path
import time
from .contracts import AcceptedArtifact
from .gate import POLICY_HASH
from .snapshot import canonical
from .store import StoreError

class Acceptor:
 def __init__(self,jobs,snapshots,destination):
  self.jobs,self.snapshots=jobs,snapshots
  self.destination=Path(destination);self.destination.mkdir(mode=0o700,parents=True,exist_ok=True)
 def accept(self,job_id):
  with self.jobs.tx() as db:
   row=self.jobs._row(db,job_id)
   if row['state'] not in ('accepted_candidate','accepted') or not row['gate']:raise StoreError('NOT_APPROVED')
   gate=json.loads(row['gate'])
   if gate.get('status')!='pass' or gate.get('policy_hash')!=POLICY_HASH or gate.get('artifact_hash')!=row['snapshot']:raise StoreError('STALE_APPROVAL')
   if row['state']!='accepted' and time.time()-row['created']>600:raise StoreError('APPROVAL_EXPIRED')
   snap=self.snapshots.open(row['snapshot']);data=canonical(snap.files)
   path=self.destination/f'{job_id}.json'
   try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   except FileExistsError:
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:existing=stream.read(240*1024+1)
    if hashlib.sha256(existing).hexdigest()!=snap.artifact_hash:raise StoreError('ACCEPTED_ARTIFACT_CHANGED')
   else:
    with os.fdopen(fd,'wb') as stream:
     stream.write(data);stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o400)
   db.execute("UPDATE jobs SET state='accepted' WHERE id=?",(job_id,))
   return AcceptedArtifact(snap.artifact_hash)
