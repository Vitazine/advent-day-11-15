"""Explicit schema for manually bounded HTTP body handling."""
from .contracts import ChatRequest,ReviewRequest,ReviewResponse

def schema():
    components={}
    for cls in (ChatRequest,ReviewRequest,ReviewResponse):
        item=cls.model_json_schema(ref_template='#/components/schemas/{model}')
        components.update(item.pop('$defs',{}));components[cls.__name__]=item
    paths={}
    for path,model,response in (('/v1/chat/completions','ChatRequest',None),('/v1/security/reviews','ReviewRequest','ReviewResponse')):
        ok={'description':'Проверенный результат; Chat поддерживает JSON или буферизованный SSE.'}
        if response:ok['content']={'application/json':{'schema':{'$ref':'#/components/schemas/'+response}}}
        paths[path]={'post':{'requestBody':{'required':True,'content':{'application/json':{'schema':{'$ref':'#/components/schemas/'+model}}}},'responses':{'200':ok,'default':{'description':'Безопасная ошибка error.code; X-Request-ID.'}}}}
    for path in ('/v1/models','/v1/limits'):paths[path]={'get':{'responses':{'200':{'description':'Модели либо собственные лимиты клиента.'}}}}
    return {'openapi':'3.1.0','info':{'title':'Day14 Gateway','version':'1.0.0'},'paths':paths,'security':[{'bearerAuth':[]}],
            'components':{'schemas':components,'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer'}}}}
