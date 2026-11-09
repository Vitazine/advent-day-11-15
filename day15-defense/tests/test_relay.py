import json
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from runner.relay import GatewayRelay
class Client:
 def __init__(self):self.calls=[]
 def request(self,route,body):self.calls.append((route,body));return 200,{},b'{}'
class RelayTests(unittest.TestCase):
 def test_auth_routes_limits_and_each_call_forwarded(self):
  client=Client()
  with GatewayRelay(client) as relay:
   def send(path,token,data):
    req=Request(relay.base_url+path,data=data,headers={'Authorization':'Bearer '+token})
    try:
     with urlopen(req,timeout=2) as response:return response.status
    except HTTPError as e:return e.code
   self.assertEqual(send('/chat/completions','wrong',b'{}'),401)
   self.assertEqual(send('/security/reviews',relay.token,b'{}'),404)
   self.assertEqual(send('/chat/completions',relay.token,b'x'*262145),502)
   self.assertEqual(client.calls,[])
   for _ in range(2):self.assertEqual(send('/chat/completions',relay.token,b'{}'),200)
   self.assertEqual(len(client.calls),2)
