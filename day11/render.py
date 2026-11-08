"""Render untrusted final answers as text only; no scripts or remote resources."""
import argparse
from html import escape
import json
from pathlib import Path
from .evaluate import read_jsonl, classify_response

STYLE='''body{font:16px/1.55 -apple-system,BlinkMacSystemFont,sans-serif;background:#f4f6fa;color:#172338;margin:0;padding:32px}main{max-width:1080px;margin:auto}h1{font-size:28px}h2{font-size:21px;margin-top:0}article{background:white;border:1px solid #ccd5e3;border-radius:12px;padding:24px;margin:24px 0;break-inside:avoid}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.55 ui-monospace,monospace;background:#f5f7fa;padding:16px;border-radius:6px}small{color:#52627a}.meta{padding:10px 0;color:#334a65}.label{font-weight:650;margin-top:16px}.note{padding:16px;background:#e7edf8;border-radius:8px}'''

def render_transcripts(records: list[dict],output: Path) -> None:
    parts=['<!doctype html><html lang="ru"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>День 11 — API-транскрипты</title><style>'+STYLE+'</style><main><h1>День 11 · Проверка банковского помощника</h1><p class="note">Отображение сохранённого API-транскрипта. Ответы созданы моделью; это не интерфейс DeepSeek. Служебные маркеры — синтетические. Данные с моделью synthetic — только тестовые.</p>']
    for r in records:
        auto=classify_response(r,r.get('marker',''))
        parts.append('<article id="'+escape(r['attempt_id'],quote=True)+'"><h2>'+escape(r['technique'])+' · '+escape(r['variant'])+'</h2>')
        parts.append('<div class="meta">'+escape(f"{r['attempt_id']} | {r['model']} | {r['timestamp']}")+'</div>')
        parts.append('<small>'+escape(f"finish_reason={r['finish_reason']} · validity={auto['validity']} · marker_leaked={auto['marker_leaked']}")+'</small>')
        for message in r['messages']:
            parts.append('<div class="label">'+escape(message['role'])+'</div><pre>'+escape(message['content'])+'</pre>')
        parts.append('<div class="label">Ответ модели</div><pre>'+escape(r.get('content',''))+'</pre>')
        if r.get('review'):
            parts.append('<div class="label">Оценка</div><p>'+escape(json.dumps(r['review'],ensure_ascii=False))+'</p>')
        parts.append('</article>')
    output.write_text(''.join(parts)+'</main></html>',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(); p.add_argument('--run',type=Path,required=True); a=p.parse_args()
    records=read_jsonl(a.run/'responses.jsonl'); reviews={r['attempt_id']:r for r in read_jsonl(a.run/'reviews.jsonl')}
    for r in records: r['review']=reviews.get(r['attempt_id'])
    render_transcripts(records,a.run/'transcripts.html')
    print('HTML-транскрипты сохранены локально')
if __name__=='__main__': main()
