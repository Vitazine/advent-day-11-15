import json
from pathlib import Path
import unittest
from redteam.run import run_case

class RedTeamTests(unittest.TestCase):
 def test_frozen_attack_and_control_corpus(self):
  cases=json.loads((Path(__file__).resolve().parents[1]/'redteam/cases.json').read_text())
  self.assertEqual(len(cases),32)
  for case in cases:
   with self.subTest(case=case['id']):
    result=run_case(case)
    self.assertEqual(result['observed'],case['expected'],result)
