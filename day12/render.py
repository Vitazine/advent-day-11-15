import html
import json
from pathlib import Path

def render_report(run_dir,target):
    rows=[]
    for p in sorted(Path(run_dir).glob('episodes/*/result.json')):
        r=json.loads(p.read_text())
        def esc(obj): return html.escape(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2))
        rows.append('<article><h2>'+esc(r['id'])+'</h2><p>Защита: '+esc(r['defense'])+'</p><h3>Запрос пользователя</h3><pre>'+esc(r['case']['user_request'])+'</pre><h3>Реальный ответ API</h3><pre>'+esc(r['final'])+'</pre><h3>Результат локального исполнителя</h3><pre>'+esc(r['actions'])+'</pre><h3>Автоматические признаки (не ручная оценка смысла)</h3><pre>'+esc(r['evaluation'])+'</pre></article>')
    Path(target).write_text('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>День 12 — транскрипты</title><style>body{font:16px system-ui;background:#faf6ef;color:#282522;max-width:1050px;margin:40px auto;padding:24px}article{background:white;border:1px solid #ddd;padding:24px;margin:24px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px ui-monospace}h1{font-size:36px}</style></head><body><h1>День 12 · реальные транскрипты API</h1><p>Синтетические учебные данные. Ниже отображены сохранённые ответы и проверенные локальные действия. Это не интерфейс DeepSeek. Внедрённые команды отображаются как текст.</p>'+''.join(rows)+'</body></html>')

if __name__=='__main__':
    from .runner import RUN
    render_report(RUN,Path(__file__).parent/'evidence'/'transcripts.html')
