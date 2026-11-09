import unittest
from runner.policy import parse_proposal,PolicyError

class PolicyTests(unittest.TestCase):
 def test_proposal_cannot_grant_authority(self):
  for text in ('{"files":[],"decision":"pass"}', '{"operation":"shell","command":"echo synthetic"}', '{"files":[],"files":[]}'):
   with self.subTest(text=text),self.assertRaises(PolicyError):parse_proposal(text)
 def test_valid_source_is_preserved(self):
  self.assertEqual(parse_proposal('{"files":[{"path":"app.py","content":"print(1)"}]}'),(('app.py','print(1)'),))
 def test_paths_and_oversize_rejected(self):
  for text in ('{"files":[{"path":"../app.py","content":"x"}]}', ' '*300000, '{"files":[{"path":"app.py","content":"x","approved":true}]}'):
   with self.assertRaises(PolicyError):parse_proposal(text)
