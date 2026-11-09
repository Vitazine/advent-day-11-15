import subprocess
import sys
import unittest
from runner.process import bounded_output
from runner.policy import PolicyError
class ProcessTests(unittest.TestCase):
 def test_output_limit_kills_producer(self):
  p=subprocess.Popen([sys.executable,'-c','import os; os.write(1,b"x"*100000); import time; time.sleep(30)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  with self.assertRaises(PolicyError): bounded_output(p,2,1024)
  self.assertIsNotNone(p.poll())
 def test_timeout(self):
  p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  with self.assertRaises(PolicyError): bounded_output(p,.1,1024)
  self.assertIsNotNone(p.poll())
