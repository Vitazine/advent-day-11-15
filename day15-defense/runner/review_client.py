import json
from .gateway_client import GatewayFailure

class ReviewClient:
 def __init__(self,client):self.client=client
 def review(self,snapshot):
  body={'stack_profile':'python-fastapi','files':[{'path':f.path,'content':f.content} for f in snapshot.files]}
  status,headers,raw=self.client.request('security/reviews',body)
  if status!=200:raise GatewayFailure(f'REVIEW_HTTP_{status}')
  try:
   data=json.loads(raw)
   if not isinstance(data,dict) or data.get('artifact_hash')!=snapshot.artifact_hash:raise ValueError()
   return data
  except (ValueError,TypeError):raise GatewayFailure('REVIEW_INVALID') from None
