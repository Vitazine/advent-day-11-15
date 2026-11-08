"""Small adaptive follow-up; historical comparison remains immutable."""
import argparse
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import secrets
import time
from .api import DeepSeekClient, ApiStop, MAX_REQUEST
from .keychain import read_api_key, KeychainError
from .contracts import SETTINGS
from .runner import ROOT, PRICING, append_json, now, digest, usage_upper, validate, load_manifest
from .evaluate import read_jsonl

RUN=ROOT/'runs/2026-11-07-adaptive'
class ExperimentStop(Exception): pass

def reserve_cost(spent: Decimal,messages: list[dict]) -> Decimal:
 body=json.dumps({**SETTINGS,'messages':messages},ensure_ascii=False).encode()
 if len(body)>MAX_REQUEST: raise ExperimentStop('Превышено тело запроса')
 reserve=(Decimal(len(body)+1024)*Decimal(PRICING['input_per_million'])+Decimal(512)*Decimal(PRICING['output_per_million']))/Decimal(1000000)
 if spent+reserve>Decimal('1'): raise ExperimentStop('Общий бюджет $1 исчерпан')
 return reserve

def validate_answer(answer: dict) -> None:
 if answer.get('model') not in ('deepseek-flash','DeepSeek-V4.1-Flash-1017','deepseek-v4.1-flash-1017') or answer.get('reasoning_present'):
  raise ExperimentStop('Ответ не соответствует модели или режиму')
 usage=answer.get('usage',{})
 if any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens')) or usage['completion_tokens']>512:
  raise ExperimentStop('Неизвестный usage или превышен output cap')

def previous_cost(status: dict,journal: list[dict]) -> Decimal:
 started={e['attempt_id'] for e in journal if e['event']=='started'}
 completed={e['attempt_id'] for e in journal if e['event']=='completed'}
 if status.get('state')!='complete' or status.get('inflight_charge_unknown') or status.get('completed_generations')!=79 or len(started)!=79 or started!=completed:
  raise ExperimentStop('Основной прогон не подтверждён; оплата может быть неизвестна')
 cost=Decimal(status['cost_upper_usd'])
 if not cost.is_finite() or cost<0: raise ExperimentStop('Некорректные предыдущие расходы')
 return cost

def confirmation_trials(case: dict) -> list[tuple]:
 return [(case,variant,repeat) for repeat in (1,2,3) for variant in ('baseline','hardened')]

def main():
 p=argparse.ArgumentParser();p.add_argument('--variant',choices=('baseline','hardened'),default='baseline');p.add_argument('--case',action='append');p.add_argument('--repeat',type=int,default=1);p.add_argument('--confirm',help='ID сценария для трёх повторов на обоих промптах; уже завершённые не повторяются');a=p.parse_args()
 try:
  validate(load_manifest(ROOT/'runs/2026-11-07-main/manifest.json'))
  cases=json.loads((ROOT/'adaptive_cases.json').read_text())
  if a.case:
   if set(a.case)-{c['id'] for c in cases}: raise ExperimentStop('Неизвестный сценарий')
   cases=[c for c in cases if c['id'] in a.case]
  if not 1<=a.repeat<=3: raise ExperimentStop('Неверный повтор')
  RUN.mkdir(exist_ok=True)
  with (ROOT/'runs/.execution.lock').open('a') as lock:
   try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError: raise ExperimentStop('Другой прогон уже запущен') from None
   journal=read_jsonl(RUN/'journal.jsonl');responses=read_jsonl(RUN/'responses.jsonl')
   started={e['attempt_id'] for e in journal if e['event']=='started'}
   done={e['attempt_id'] for e in journal if e['event']=='completed'}
   if started!=done: raise ExperimentStop('Незавершённая попытка: повтор запрещён')
   trials=[(c,a.variant,a.repeat) for c in cases]
   if a.confirm:
    selected=[c for c in cases if c['id']==a.confirm]
    if len(selected)!=1: raise ExperimentStop('Неизвестный confirm-сценарий')
    trials=[(c,v,r) for c,v,r in confirmation_trials(selected[0]) if f"{c['id']}-{r}-{v}" not in done]
   identities=[f"{c['id']}-{r}-{v}" for c,v,r in trials]
   if any(i in started for i in identities): raise ExperimentStop('Эти попытки уже выполнены')
   if len(started)+len(trials)>30: raise ExperimentStop('Лимит дополнительных генераций 30')
   spent=previous_cost(json.loads((ROOT/'runs/2026-11-07-main/status.json').read_text()),read_jsonl(ROOT/'runs/2026-11-07-main/journal.jsonl'))
   spent+=sum((usage_upper(r['usage'],PRICING) for r in responses),Decimal(0))
   client=DeepSeekClient(read_api_key())
   models=client.list_models()
   match=[m for m in models if m['id']=='deepseek-flash']
   if len(match)!=1 or match[0].get('name','') not in ('','DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017'): raise ExperimentStop('Модель не совпала')
   append_json(RUN/'preflight.jsonl',{'at':now(),'model':match[0],'pricing':PRICING,'cases':identities})
   for (case,variant,repeat),identity in zip(trials,identities):
    prompt=(ROOT/f'prompts/{variant}.txt').read_text()
    time.sleep(5)
    marker='D11_'+secrets.token_hex(12)
    messages=[{'role':'system','content':prompt.replace('{marker}',marker)},{'role':'user','content':case['user_text']}]
    reserve_cost(spent,messages)
    append_json(RUN/'journal.jsonl',{'attempt_id':identity,'event':'started','at':now()})
    answer=client.complete(messages,SETTINGS)
    record={**answer,'attempt_id':identity,'case_id':case['id'],'technique':case['technique'],
            'variant':variant,'repeat':repeat,'marker':marker,'messages':messages,'prompt_hash':digest(messages[0]['content']),
            'timestamp':now(),'settings':SETTINGS,'status':'received','objective':'adaptive'}
    try: validate_answer(answer)
    except ExperimentStop:
     record['status']='invalid';append_json(RUN/'responses.jsonl',record);raise
    append_json(RUN/'responses.jsonl',record)
    cost=usage_upper(answer['usage'],PRICING);spent+=cost
    append_json(RUN/'journal.jsonl',{'attempt_id':identity,'event':'completed','at':now(),'cost_upper_usd':str(cost)})
    print(f'{identity}: сохранено; общий верхний расход ${spent:.6f}',flush=True)
  return 0
 except (ExperimentStop,ApiStop,KeychainError) as error:
  print('Остановка: '+str(error),flush=True);return 2
 except BaseException:
  print('Остановка: ошибка или прерывание; автоматического повтора нет',flush=True);return 2
if __name__=='__main__': raise SystemExit(main())
