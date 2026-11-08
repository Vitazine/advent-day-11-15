"""One-shot, journaled experiment. Commands never print credentials or responses."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
from .contracts import Suite, SETTINGS, load_suite, build_messages
from .api import DeepSeekClient, ApiStop, MAX_REQUEST
from .keychain import read_api_key, KeychainError

ROOT=Path(__file__).resolve().parent
INPUTS=('cases.json','config.json','prompts/baseline.txt','prompts/hardened.txt')
PRICING={'input_per_million':'0.30','output_per_million':'1.20','cache_hit_per_million':'0.006',
         'checked_on':'2026-11-07','source':'https://api-docs.deepseek.com/quick_start/pricing/',
         'basis':'peak, uncached input: conservative upper estimate'}

class RunStop(Exception): pass

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def write_json(path: Path,value) -> None:
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp,path)

def append_json(path: Path,value) -> None:
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())

def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())

def fingerprint(root: Path) -> dict:
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in INPUTS}

def seal(m: dict) -> str:
    return digest({k:v for k,v in m.items() if k not in ('seal','preflight')})

def input_bound(a: dict) -> int:
    # UTF-8 byte count is deliberately far above typical Russian token counts.
    return len(json.dumps({**SETTINGS,'messages':a['messages']},ensure_ascii=False).encode())+1024

def estimate_upper_usd(manifest: dict,pricing: dict) -> Decimal:
    rows=[manifest['probe']]+manifest['attempts']
    return (Decimal(sum(input_bound(a) for a in rows))*Decimal(pricing['input_per_million'])+
            Decimal(len(rows)*512)*Decimal(pricing['output_per_million']))/Decimal(1000000)

def prepare(suite: Suite,run_dir: Path) -> dict:
    attempts=[]
    for index,case in enumerate(suite.cases):
        for repeat in (1,2,3):
            marker='D11_'+secrets.token_hex(12)
            order=('baseline','hardened') if (index+repeat)%2 else ('hardened','baseline')
            for variant in order:
                messages=build_messages(case,suite.prompts[variant],marker)
                attempts.append({'attempt_id':f'{case.id}-{repeat}-{variant}', 'case_id':case.id,
                    'technique':case.technique,'objective':case.objective,'variant':variant,'repeat':repeat,
                    'marker':marker,'messages':messages,'prompt_hash':digest(messages[0]['content'])})
    probe={'attempt_id':'probe','case_id':'probe','technique':'Техническая проба','objective':'probe',
           'variant':'probe','repeat':0,'marker':'','messages':[{'role':'user','content':'Ответь одним словом: готово.'}],'prompt_hash':''}
    m={'schema':1,'created_at':now(),'suite_root':str(suite.root),'fingerprint':fingerprint(suite.root),
       'config':suite.config,'pricing':PRICING.copy(),'probe':probe,'attempts':attempts,
       'model_mapping_source':'https://api-docs.deepseek.com/','expected_version':'DeepSeek-V4.1-Flash-1017'}
    m['seal']=seal(m)
    run_dir.mkdir(parents=True,exist_ok=False)
    write_json(run_dir/'manifest.json',m)
    return m

def validate(m: dict) -> None:
    if m['seal']!=seal(m) or fingerprint(Path(m['suite_root']))!=m['fingerprint']:
        raise RunStop('Изменены входные файлы или manifest; запуск запрещён')
    suite=load_suite(Path(m['suite_root']))
    if suite.config!=m['config'] or len(m['attempts'])!=78 or len({a['attempt_id'] for a in m['attempts']})!=78:
        raise RunStop('Нарушена матрица или конфигурация')
    for a in [m['probe']]+m['attempts']:
        if input_bound(a)-1024>MAX_REQUEST:
            raise RunStop('Запрос превышает 16 KiB')
    price=m['pricing']
    if not all(Decimal(price[k]).is_finite() and Decimal(price[k])>=0 for k in ('input_per_million','output_per_million')):
        raise RunStop('Некорректные тарифы')
    if estimate_upper_usd(m,price)>Decimal('1.00'):
        raise RunStop('Верхняя оценка превышает $1')
    checked=datetime.fromisoformat(price['checked_on']).replace(tzinfo=timezone.utc)
    if abs((datetime.now(timezone.utc)-checked).total_seconds())>48*3600:
        raise RunStop('Тарифы устарели: требуется повторная проверка перед новым запуском')

def preflight(manifest_path: Path,client: DeepSeekClient) -> dict:
    m=load_manifest(manifest_path); validate(m)
    models=client.list_models()
    matches=[model for model in models if model.get('id')=='deepseek-flash']
    if len(matches)!=1:
        raise RunStop('Нужная модель отсутствует в /models')
    model=matches[0]
    name=model.get('name','')
    if name and name not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017'):
        raise RunStop('Название модели не соответствует ожидаемой версии')
    m['preflight']={'at':now(),'model':model,'manifest_seal':m['seal'],
                    'estimate_upper_usd':str(estimate_upper_usd(m,m['pricing'])),
                    'identity_note':'Версия 1017 по документации; алиас не фиксирует снимок'}
    write_json(manifest_path,m)
    return m['preflight']

def usage_upper(usage: dict,pricing: dict) -> Decimal:
    if any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens')):
        raise RunStop('Usage неизвестен: расходы не подтверждены')
    return (Decimal(usage['prompt_tokens'])*Decimal(pricing['input_per_million'])+
            Decimal(usage['completion_tokens'])*Decimal(pricing['output_per_million']))/Decimal(1000000)

def execute(manifest_path: Path,client: DeepSeekClient) -> None:
    m=load_manifest(manifest_path); validate(m)
    flight=m.get('preflight',{})
    if flight.get('manifest_seal')!=m['seal'] or not flight.get('at'):
        raise RunStop('Сначала выполните preflight')
    if (datetime.now(timezone.utc)-datetime.fromisoformat(flight['at'])).total_seconds()>3600:
        raise RunStop('Preflight старше часа')
    run_dir=manifest_path.parent
    # One shared advisory lock prevents simultaneous runs on this machine.
    lock_path=ROOT/'runs'/'.execution.lock'
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RunStop('Другой прогон уже выполняется') from None
        journal=run_dir/'journal.jsonl'
        try:
            with journal.open('x'): pass
        except FileExistsError:
            raise RunStop('Этот запуск уже начат; автоматическое возобновление запрещено') from None
        spent=Decimal(0)
        rows=[m['probe']]+m['attempts']
        for index,a in enumerate(rows):
            if index: time.sleep(5)
            reserve=(Decimal(input_bound(a))*Decimal(m['pricing']['input_per_million'])+
                     Decimal(512)*Decimal(m['pricing']['output_per_million']))/Decimal(1000000)
            if index>=79 or spent+reserve>Decimal('1.00'):
                raise RunStop('Достигнут лимит запросов или расходов')
            append_json(journal,{'attempt_id':a['attempt_id'],'event':'started','at':now()})
            try:
                answer=client.complete(a['messages'],m['config']['settings'])
                record={**a,**answer,'timestamp':now(),'settings':m['config']['settings'],'status':'invalid'}
                try:
                    cost=usage_upper(answer['usage'],m['pricing'])
                except RunStop:
                    append_json(run_dir/'responses.jsonl',record)
                    raise
                spent+=cost
                if answer['model'] not in ('deepseek-flash','DeepSeek-V4.1-Flash-1017','deepseek-v4.1-flash-1017'):
                    append_json(run_dir/'responses.jsonl',record)
                    raise RunStop('Модель ответа изменилась')
                if answer.get('reasoning_present'):
                    append_json(run_dir/'responses.jsonl',record)
                    raise RunStop('Thinking не выключен; требуется проверка настроек')
                if answer['usage']['completion_tokens']>512:
                    append_json(run_dir/'responses.jsonl',record)
                    raise RunStop('Превышен лимит выходных токенов')
                record['status']='received'
                append_json(run_dir/'responses.jsonl',record)
                if index==0 and (answer['finish_reason']!='stop' or not answer['content'].strip()):
                    raise RunStop('Техническая проба не завершилась корректно')
                append_json(journal,{'attempt_id':a['attempt_id'],'event':'completed','at':now(),'cost_upper_usd':str(cost)})
                write_json(run_dir/'status.json',{'completed_generations':index+1,'cost_upper_usd':str(spent),'state':'complete' if index==78 else 'running'})
                print(f'Генерация {index+1}/79 сохранена; расходы по верхнему тарифу ${spent:.6f}',flush=True)
            except (ApiStop,RunStop) as error:
                append_json(journal,{'attempt_id':a['attempt_id'],'event':'stopped','at':now(),
                    'reason':str(error),'http_status':getattr(error,'status',None)})
                write_json(run_dir/'status.json',{'state':'stopped','completed_generations':index,
                    'cost_upper_usd':str(spent),'reason':str(error),'inflight_charge_unknown':True})
                raise RunStop(str(error)) from None
            except BaseException:
                append_json(journal,{'attempt_id':a['attempt_id'],'event':'stopped','at':now(),'reason':'Прервано; состояние оплаты последнего запроса неизвестно'})
                raise RunStop('Прервано; повтор запрещён до проверки журнала') from None

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','preflight','run'))
    parser.add_argument('--out',type=Path)
    parser.add_argument('--run',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='prepare':
            if args.out is None: raise RunStop('Укажите --out')
            m=prepare(load_suite(ROOT),args.out)
            print(f'Подготовлено {len(m["attempts"])} попыток + проба; верхняя оценка ${estimate_upper_usd(m,m["pricing"]):.6f}')
        else:
            if args.run is None: raise RunStop('Укажите --run')
            path=args.run/'manifest.json'
            validate(load_manifest(path))  # Before reading any credential.
            client=DeepSeekClient(read_api_key())
            if args.command=='preflight':
                result=preflight(path,client)
                print(f'Preflight OK: deepseek-flash, верхняя оценка ${result["estimate_upper_usd"]}')
            else: execute(path,client)
        return 0
    except (RunStop,KeychainError,ApiStop) as error:
        print('Остановка: '+str(error),file=sys.stderr); return 2
    except BaseException:
        print('Остановка: ошибка локального выполнения; секреты и traceback не выводятся',file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
