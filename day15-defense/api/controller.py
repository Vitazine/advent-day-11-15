"""Persistent ownership/idempotency journal; single global admission slot."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib,json,sqlite3,tempfile,time,uuid
from pathlib import Path
from runner.loop import Runner
from runner.contracts import JobRequest
from runner.native_generator import NativeGenerator
from runner.unix_executor import UnixExecutor
from runner.accept import Acceptor
from runner.store import StoreError

class APIError(Exception):
 def __init__(self,code,status):self.code,self.status=code,status

class Controller:
 def __init__(self,root,gateway_token,start_worker=True):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.runner=Runner(self.root/'runner',UnixExecutor(),gateway_token,generator=NativeGenerator())
  self.pool=ThreadPoolExecutor(max_workers=1) if start_worker else None
  with self.tx() as db:db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,owner TEXT,idem TEXT,digest TEXT,state TEXT,job TEXT,created REAL, UNIQUE(owner,idem))')
  self.recover()
 @contextmanager
 def tx(self):
  db=sqlite3.connect(self.root/'api.db',timeout=5);db.row_factory=sqlite3.Row
  try:db.execute('BEGIN IMMEDIATE');yield db;db.commit()
  except BaseException:db.rollback();raise
  finally:db.close()
 def recover(self):
  with self.tx() as db:db.execute("UPDATE requests SET state='error' WHERE state IN ('queued','running')")
 def submit(self,principal,idem,files,task):
  digest=hashlib.sha256(json.dumps([files,task],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  with self.tx() as db:
   old=db.execute('SELECT * FROM requests WHERE owner=? AND idem=?',(principal['id'],idem)).fetchone()
   if old:
    if old['digest']!=digest:raise APIError('IDEMPOTENCY_CONFLICT',409)
    return self.public(dict(old))
   count=db.execute('SELECT COUNT(*) FROM requests WHERE owner=?',(principal['id'],)).fetchone()[0]
   if count>=principal['max_jobs']:raise APIError('TOKEN_JOB_LIMIT',429)
   if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]>=20:raise APIError('CAMPAIGN_LIMIT',429)
   if db.execute("SELECT 1 FROM requests WHERE state IN ('queued','running')").fetchone():raise APIError('BUSY',429)
   ident=uuid.uuid4().hex
   db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',(ident,principal['id'],idem,digest,'queued',None,time.time()))
  if self.pool:self.pool.submit(self.execute,ident,files,task)
  return {'id':ident,'state':'queued'}
 def execute(self,ident,files,task):
  try:
   with self.tx() as db:db.execute("UPDATE requests SET state='running' WHERE id=?",(ident,))
   with tempfile.TemporaryDirectory(prefix='source-',dir=self.root) as tmp:
    source=Path(tmp).resolve()
    for name,content in files:
     path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8',newline='')
    result=self.runner.run(JobRequest(source,task))
   with self.tx() as db:db.execute("UPDATE requests SET state='done',job=? WHERE id=?",(result['id'],ident))
  except Exception:
   with self.tx() as db:db.execute("UPDATE requests SET state='error' WHERE id=?",(ident,))
 def owned(self,principal,ident):
  with self.tx() as db:row=db.execute('SELECT * FROM requests WHERE id=? AND owner=?',(ident,principal['id'])).fetchone()
  if row is None:raise APIError('NOT_FOUND',404)
  return dict(row)
 def public(self,row):
  result={'id':row['id'],'state':row['state']}
  if row['job']:
   state=self.runner.jobs.status(row['job']);gate=state['gate'] or {}
   result.update(state=state['state'],artifact_hash=state['snapshot'],iteration=state['iteration'],reserved_nano=state['reserved'],reason_codes=gate.get('reason_codes',[]))
  return result
 def status(self,principal,ident):return self.public(self.owned(principal,ident))
 def accept(self,principal,ident):
  row=self.owned(principal,ident)
  if not row['job']:raise APIError('NOT_READY',409)
  try:Acceptor(self.runner.jobs,self.runner.snapshots,self.root/'accepted').accept(row['job'])
  except (StoreError,ValueError,OSError):raise APIError('ACCEPT_DENIED',409) from None
  return self.public(row)
 def artifact(self,principal,ident):
  row=self.owned(principal,ident)
  if not row['job'] or self.runner.jobs.status(row['job'])['state']!='accepted':raise APIError('NOT_ACCEPTED',409)
  data=(self.root/'accepted'/f"{row['job']}.json").read_bytes()
  state=self.runner.jobs.status(row['job'])
  if hashlib.sha256(data).hexdigest()!=state['snapshot']:raise APIError('ARTIFACT_CHANGED',409)
  return {'id':ident,'artifact_hash':state['snapshot'],'files':[{'path':p,'content':c} for p,c in json.loads(data)]}
 def limits(self,principal):
  with self.tx() as db:used=db.execute('SELECT COUNT(*) FROM requests WHERE owner=?',(principal['id'],)).fetchone()[0]
  return {'expires_at':principal['expires'],'max_jobs':principal['max_jobs'],'used_jobs':used,'remaining_jobs':max(0,principal['max_jobs']-used),'max_job_reserve_usd':.05,'max_iterations':3,'generation_mode':'gateway-native','max_files':20,'max_source_bytes':196608}
