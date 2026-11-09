import unittest
from runner.contracts import Snapshot,ReviewFile,RunResult,CheckResult
from runner.checks import StaticChecks
from runner.gate import Gate,POLICY_HASH

class GateTests(unittest.TestCase):
    def setUp(self):
        self.snap=Snapshot('a'*64,'a'*64,(ReviewFile('app.py','def add(a,b): return a+b'),))
        self.checks=CheckResult('passed',self.snap.artifact_hash,POLICY_HASH,(), 'static')
        self.execution=RunResult('passed',0,'job',self.snap.artifact_hash)
        self.review={'artifact_hash':self.snap.artifact_hash,'decision':'pass','findings':[],'policy_version':'python-fastapi-v1'}
    def test_all_checks_required_for_pass(self):
        self.assertEqual(Gate.evaluate(self.snap,self.checks,self.execution,self.review).status,'pass')
        for review in (None,{},dict(self.review,artifact_hash='b'*64),dict(self.review,decision='warn'),dict(self.review,findings=[{'severity':'High'}])):
            self.assertNotEqual(Gate.evaluate(self.snap,self.checks,self.execution,review).status,'pass')
    def test_execution_failure_or_old_policy_denies(self):
        bad=RunResult('timeout',None,'job',self.snap.artifact_hash)
        self.assertNotEqual(Gate.evaluate(self.snap,self.checks,bad,self.review).status,'pass')
        old=CheckResult('passed',self.snap.artifact_hash,'old',(),'static')
        self.assertNotEqual(Gate.evaluate(self.snap,old,self.execution,self.review).status,'pass')
    def test_known_unsafe_constructs_detected_without_execution(self):
        for code in ('import os; os._exit(0)', 'import httpx\nx=httpx.get("https://example.com",verify=False)', 'eval(user_input)', 'import logging\nlogging.warning(request.headers)', 'import subprocess\nsubprocess.run(command,shell=True)'):
            snap=Snapshot('a'*64,'a'*64,(ReviewFile('app.py',code),))
            self.assertEqual(StaticChecks.run(snap).status,'failed')
    def test_clean_code_and_invalid_syntax(self):
        self.assertEqual(StaticChecks.run(self.snap).status,'passed')
        self.assertEqual(StaticChecks.run(Snapshot('a'*64,'a'*64,(ReviewFile('a.py','def ???'),))).status,'failed')
