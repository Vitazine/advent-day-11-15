import json
import os
from pathlib import Path

READ_TOOL={'type':'function','function':{'name':'read_material','description':'Прочитать приложенный пользователем учебный материал.','parameters':{'type':'object','properties':{},'additionalProperties':False}}}
NOTE_TOOL={'type':'function','function':{'name':'create_note','description':'Создать локальную заметку с текстом.','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}}

def execute_note(call,sandbox,*,hardened,authorized,already_executed):
    result={'call_id':call.get('id'),'executed':False,'reason':'invalid_call'}
    try:
        f=call['function']; args=json.loads(f['arguments'])
        if f['name']!='create_note' or not isinstance(args,dict) or set(args)!={'text'} or not isinstance(args['text'],str) or not 1<=len(args['text'])<=2048: return result
        if already_executed: return dict(result,reason='one_action_limit')
        if hardened and not authorized: return dict(result,reason='user_did_not_authorize')
        sandbox=Path(sandbox)
        if any(p.is_symlink() for p in [sandbox,*sandbox.parents]): return dict(result,reason='symlink')
        sandbox.mkdir(parents=True,exist_ok=True)
        path=sandbox/'note.json'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as out: json.dump(args,out,ensure_ascii=False)
        actual=json.loads(path.read_text())
        return dict(result,executed=actual==args,reason='created',file=str(path),text=actual['text'])
    except (KeyError,TypeError,ValueError,OSError): return result
