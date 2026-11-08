import json
import os
from decimal import Decimal
from pathlib import Path

class Stop(Exception): pass

def save(path,obj):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

class Ledger:
    def __init__(self,root):
        self.path=Path(root)/'budget.json'
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {'count':0,'reserved_usd':'0','usage_peak_usd':'0','requests':[]}
    def reserve(self,request_bytes,max_output):
        amount=(Decimal(request_bytes+2048)*Decimal('0.30')+Decimal(max_output)*Decimal('1.20'))/1000000
        total=Decimal(self.state['reserved_usd'])+amount
        if self.state['count']>=130 or total>1: raise Stop('Budget or generation limit')
        self.state['count']+=1; self.state['reserved_usd']=str(total)
        row={'id':str(self.state['count']),'bound_usd':str(amount),'input_bound':request_bytes+2048,'status':'reserved'}
        self.state['requests'].append(row); save(self.path,self.state); return row['id']
    def settle(self,reservation_id,usage):
        row=next(r for r in self.state['requests'] if r['id']==reservation_id)
        if row['status']!='reserved': raise Stop('Reservation already settled')
        if not all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')): raise Stop('Missing usage')
        cost=(Decimal(usage['prompt_tokens'])*Decimal('0.30')+Decimal(usage['completion_tokens'])*Decimal('1.20'))/1000000
        row.update(status='completed',usage=usage,peak_usd=str(cost))
        self.state['usage_peak_usd']=str(Decimal(self.state['usage_peak_usd'])+cost)
        save(self.path,self.state)
        if usage['prompt_tokens']>row['input_bound'] or cost>Decimal(row['bound_usd']): raise Stop('Usage exceeds conservative reserve')
