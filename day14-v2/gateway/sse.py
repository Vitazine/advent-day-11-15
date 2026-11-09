"""Serialize only previously verified results."""
import json
import time

def completion(result,model):
    return {'id':'chatcmpl-'+result.request_id,'object':'chat.completion','created':int(time.time()),'model':model,
            'choices':[{'index':0,'message':result.message,'finish_reason':result.finish_reason}], 'usage':result.usage.model_dump()}

def encode_sse(result,*,model,include_usage):
    base={k:v for k,v in completion(result,model).items() if k not in ('choices','usage')}
    base['object']='chat.completion.chunk'
    def chunk(delta,finish=None):
        return ('data: '+json.dumps(dict(base,choices=[{'index':0,'delta':delta,'finish_reason':finish}]),ensure_ascii=False)+'\n\n').encode()
    yield chunk({'role':'assistant'})
    content=result.message.get('content')
    if content:
        yield chunk({'content':content})
    for index,tool in enumerate(result.message.get('tool_calls',[])):
        yield chunk({'tool_calls':[dict(tool,index=index)]})
    yield chunk({},result.finish_reason)
    if include_usage:
        yield ('data: '+json.dumps(dict(base,choices=[],usage=result.usage.model_dump()))+'\n\n').encode()
    yield b'data: [DONE]\n\n'
