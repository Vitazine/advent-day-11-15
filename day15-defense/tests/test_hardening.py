import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runner.fingerprint import worker_fingerprint, policy_fingerprint
from runner.sandbox import build_unit_command
from tools.doctor import readiness

class HardeningTests(unittest.TestCase):
 def test_runtime_is_pinned_to_release(self):
  cmd=build_unit_command(Path('/var/lib/day15-defense/jobs/abc/root'),'day15-job-abc',Path('/srv/day15-defense/releases/20261109T000000Z'))
  self.assertIn('BindReadOnlyPaths=/srv/day15-defense/releases/20261109T000000Z/runtime:/opt/runtime',cmd)
 def test_fingerprints_cover_transport_and_validator(self):
  with patch('runner.fingerprint.digest',side_effect=lambda names: '|'.join(names)):
   self.assertIn('runner/snapshot.py',worker_fingerprint())
   self.assertIn('runner/relay.py',policy_fingerprint())
   self.assertIn('runner/review_client.py',policy_fingerprint())
 def test_readiness_requires_current_e2e_and_live_runtime(self):
  self.assertFalse(readiness({'status':'verified_identity'},{'status':'available'})['ready'])
  self.assertTrue(readiness({'status':'verified_identity'},{'status':'available'},True)['ready'])
