"""The agent may propose source files, never permissions or runner decisions."""
import json
from .snapshot import validate,SnapshotError

class PolicyError(ValueError):pass

def parse_proposal(text):
 if not isinstance(text,str) or len(text.encode('utf-8'))>240*1024:raise PolicyError('PROPOSAL_LIMIT')
 def unique(pairs):
  obj={}
  for k,v in pairs:
   if k in obj:raise PolicyError('DUPLICATE_KEY')
   obj[k]=v
  return obj
 try:
  obj=json.loads(text,object_pairs_hook=unique)
  if not isinstance(obj,dict) or set(obj)!={'files'} or not isinstance(obj['files'],list):raise PolicyError('INVALID_PROPOSAL')
  pairs=[]
  for item in obj['files']:
   if not isinstance(item,dict) or set(item)!={'path','content'}:raise PolicyError('INVALID_FILE')
   pairs.append((item['path'],item['content']))
  return tuple((f.path,f.content) for f in validate(pairs))
 except (ValueError,TypeError,KeyError,RecursionError,SnapshotError):raise PolicyError('INVALID_PROPOSAL') from None
