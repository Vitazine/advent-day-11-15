import tempfile
import unittest
from pathlib import Path
from tools.evaluate import classify, run_cases
from tools.export_evidence import export_events
from tests import test_chat_api as base
from tests.support import HEADERS

class EvaluationTests(base.ApiCase):
    def test_classification(self):
        self.assertEqual(classify({'vulnerable':True},{'gateway':'allowed','review':'pass'}),'missed_by_both')
        self.assertEqual(classify({'vulnerable':True},{'gateway':'allowed','review':'error'}),'not_evaluated')
        self.assertEqual(classify({'vulnerable':False},{'gateway':'blocked','review':'not_run'}),'false_positive')
    def test_blocked_review_not_run(self):
        case={'id':'test','task':'sk-proj-synthetic123','vulnerable':True}
        self.client.headers.update(HEADERS)
        result=run_cases(self.client,[case],mode='synthetic')[0]
        self.assertEqual(result['review'],'not_run');self.assertEqual(result['classification'],'caught_gateway')
        self.assertEqual(self.provider.calls,[])
    def test_export_no_canary(self):
        self.client.headers.update(HEADERS)
        run_cases(self.client,[{'id':'test','task':'sk-proj-synthetic123','vulnerable':True}],mode='synthetic')
        p=Path(self.tmp.name)/'export.json';export_events(self.db,p)
        self.assertNotIn('sk-proj-synthetic123',p.read_text())
