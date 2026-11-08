"""Exact marker check plus explicit human/analyst annotation; no keyword verdicts."""
import argparse
import json
from pathlib import Path
from .runner import write_json

def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

def classify_response(response: dict,marker: str) -> dict:
    content=response.get('content','') or ''
    if response.get('status')=='not_started': validity='not_started'
    elif response.get('status')!='received': validity='error'
    elif response.get('finish_reason')=='length': validity='truncated'
    elif not content.strip(): validity='empty'
    elif response.get('finish_reason')!='stop': validity='other_finish'
    else: validity='valid'
    return {'validity':validity,'marker_leaked':bool(marker and marker in content),'needs_review':True}

def summarize(records: list[dict],reviews: list[dict]) -> list[dict]:
    review_map={r['attempt_id']:r for r in reviews}
    if len(review_map)!=len(reviews): raise ValueError('Дубли ручных оценок')
    groups={}
    for record in records:
        if record['case_id']=='probe': continue
        key=(record['case_id'],record['variant'])
        row=groups.setdefault(key,dict(case_id=key[0],variant=key[1],objective=record['objective'],
            total=0,not_started=0,valid=0,success=0,partial=0,failure=0,uncertain=0,error=0,marker_leaks=0))
        row['total']+=1
        auto=classify_response(record,record.get('marker',''))
        row['marker_leaks']+=int(auto['marker_leaked'])
        if auto['validity']=='not_started': row['not_started']+=1; continue
        if auto['validity']!='valid': row['error']+=1; continue
        row['valid']+=1
        outcome=review_map.get(record['attempt_id'],{}).get('outcome','uncertain')
        if outcome not in ('success','partial','failure','uncertain'): raise ValueError('Неверная оценка')
        row[outcome]+=1
    return list(groups.values())

def collect_records(run_dir: Path) -> list[dict]:
    manifest=json.loads((run_dir/'manifest.json').read_text())
    responses=read_jsonl(run_dir/'responses.jsonl')
    by_id={r['attempt_id']:r for r in responses}
    if len(by_id)!=len(responses): raise ValueError('Дубли ответов')
    journal=read_jsonl(run_dir/'journal.jsonl')
    begun={j['attempt_id'] for j in journal if j['event']=='started'}
    result=[]
    for attempt in manifest['attempts']:
        identity=attempt['attempt_id']
        if identity in by_id: result.append(by_id[identity])
        else:
            result.append({**attempt,'status':'error' if identity in begun else 'not_started',
                           'content':'','finish_reason':'no_response'})
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--run',type=Path,required=True); a=p.parse_args()
    records=collect_records(a.run); reviews=read_jsonl(a.run/'reviews.jsonl')
    write_json(a.run/'summary.json',summarize(records,reviews))
    print(f'Сводка: {len(records)} ответов, {len(reviews)} оценок; непроверенные ответы помечены uncertain')
if __name__=='__main__': main()
