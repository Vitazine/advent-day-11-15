import hashlib,json,tempfile,time,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from api.app import create_app

class APITests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.tokens=self.root/'tokens.json'
  self.config={'tokens':[{'id':'alice','sha256':hashlib.sha256(b'alice-token').hexdigest(),'expires':time.time()+600,'max_jobs':2},{'id':'bob','sha256':hashlib.sha256(b'bob-token').hexdigest(),'expires':time.time()+600,'max_jobs':2}]}
  self.tokens.write_text(json.dumps(self.config))
  self.app=create_app(self.root/'state',self.tokens,'unused',start_worker=False)
  self.client=TestClient(self.app);self.headers={'Authorization':'Bearer alice-token','Idempotency-Key':'test-1'}
  self.payload={'files':[{'path':'app.py','content':'x=1'}],'task':''}
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def post(self,**kwargs):return self.client.post('/v1/jobs',json=kwargs.get('payload',self.payload),headers=kwargs.get('headers',self.headers))
 def test_auth_and_live_revocation(self):
  self.assertEqual(self.post(headers={}).status_code,401)
  self.config['tokens'][0]['expires']=0;self.tokens.write_text(json.dumps(self.config))
  self.assertEqual(self.post().status_code,401)
 def test_idempotency_ownership_and_no_early_artifact(self):
  a=self.post();self.assertEqual(a.status_code,202);job=a.json()['id']
  self.assertEqual(self.post().json()['id'],job)
  self.assertEqual(self.post(payload={**self.payload,'task':'other'}).status_code,409)
  for path in (f'/v1/jobs/{job}',f'/v1/jobs/{job}/artifact'):
   self.assertEqual(self.client.get(path,headers={'Authorization':'Bearer bob-token'}).status_code,404)
  self.assertEqual(self.client.post(f'/v1/jobs/{job}/accept',headers={'Authorization':'Bearer bob-token'}).status_code,404)
  self.assertEqual(self.client.get(f'/v1/jobs/{job}/artifact',headers=self.headers).status_code,409)
  self.assertEqual(self.client.post(f'/v1/jobs/{job}/accept',headers=self.headers).status_code,409)
 def test_queue_and_input_limits(self):
  for bad in ({'files':[{'path':'../a','content':'x'}]}, {'files':self.payload['files'],'approval':'pass'}, {'files':self.payload['files'],'task':True}):
   self.assertEqual(self.post(payload=bad).status_code,422)
  self.assertEqual(self.post().status_code,202)
  self.assertEqual(self.post(headers={**self.headers,'Idempotency-Key':'second'}).status_code,429)
 def test_restart_does_not_replay_and_quota_persists(self):
  job=self.post().json()['id']
  self.app.state.controller.recover()
  self.assertEqual(self.client.get(f'/v1/jobs/{job}',headers=self.headers).json()['state'],'error')
  self.assertEqual(self.post().json()['id'],job)
  self.assertEqual(self.post(headers={**self.headers,'Idempotency-Key':'second'}).status_code,202)
  self.app.state.controller.recover()
  self.assertEqual(self.post(headers={**self.headers,'Idempotency-Key':'third'}).status_code,429)
 def test_oversize_and_duplicate_json(self):
  self.assertEqual(self.client.post('/v1/jobs',content=b'x'*262145,headers=self.headers).status_code,413)
  self.assertEqual(self.client.post('/v1/jobs',content=b'{"files":[],"files":[]}',headers=self.headers).status_code,422)
 def test_exact_accept_and_artifact(self):
  from runner.contracts import GateDecision
  from runner.gate import POLICY_HASH
  ctrl=self.app.state.controller
  public=self.post().json()['id'];snap=ctrl.runner.snapshots.from_files([('app.py','x=1')])
  job=ctrl.runner.jobs.create(snap.id);ctrl.runner.jobs.begin_iteration(job,snap.id)
  ctrl.runner.jobs.record_gate(job,GateDecision('pass',snap.id,snap.artifact_hash,POLICY_HASH,()))
  with ctrl.tx() as db:db.execute("UPDATE requests SET state='done',job=? WHERE id=?",(job,public))
  for _ in range(2):self.assertEqual(self.client.post(f'/v1/jobs/{public}/accept',headers=self.headers).json()['state'],'accepted')
  data=self.client.get(f'/v1/jobs/{public}/artifact',headers=self.headers).json()
  self.assertEqual(data['artifact_hash'],snap.artifact_hash)
  self.assertEqual(data['files'],[{'path':'app.py','content':'x=1'}])
 def test_non_utf8_task_is_validation_error(self):
  self.assertEqual(self.client.post('/v1/jobs',content=json.dumps({**self.payload,'task':'\ud800'}).encode(),headers=self.headers).status_code,422)
