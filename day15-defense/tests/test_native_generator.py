import json,unittest
from runner.native_generator import NativeGenerator
from runner.contracts import Snapshot,ReviewFile
from runner.policy import PolicyError
class Client:
 def __init__(self,message,finish='stop'):self.message,self.finish=message,finish
 def request(self,route,payload):
  assert route=='chat/completions' and 'tools' not in payload
  return 200,{},json.dumps({'choices':[{'finish_reason':self.finish,'message':self.message}]}).encode()
class NativeTests(unittest.TestCase):
 def test_full_snapshot_only(self):
  snap=Snapshot('a'*64,'a'*64,(ReviewFile('a.py','pass'),))
  message={'content':json.dumps({'files':[{'path':'app.py','content':'x=1'}]})}
  self.assertEqual(NativeGenerator().generate(snap,'task',(),Client(message)),(('app.py','x=1'),))
  for client in (Client(message,'length'),Client({**message,'tool_calls':[{}]}),Client({'content':'{"approval":"pass"}'})):
   with self.assertRaises(PolicyError):NativeGenerator().generate(snap,'task',(),client)
