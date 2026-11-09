"""Strict transport types and bounded JSON parsing."""
import json
from typing import Literal
from pathlib import PurePosixPath
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .errors import GatewayError

class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', hide_input_in_errors=True)

class TextPart(Strict):
    type: Literal['text']
    text: str

class FunctionCall(Strict):
    name: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    arguments: str

class ToolCall(Strict):
    id: str = Field(min_length=1, max_length=128)
    type: Literal['function']
    function: FunctionCall

class Message(Strict):
    role: Literal['system','user','assistant','tool']
    content: str | list[TextPart] | None = None
    tool_calls: list[ToolCall] | None = Field(default=None, max_length=64)
    tool_call_id: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def structure(self):
        if self.role != 'assistant' and self.content is None: raise ValueError('content required')
        if self.tool_calls is not None and self.role != 'assistant': raise ValueError('assistant only')
        if (self.role == 'tool') != (self.tool_call_id is not None): raise ValueError('tool id mismatch')
        if self.role == 'assistant' and self.content is None and not self.tool_calls: raise ValueError('empty assistant')
        return self

class FunctionDef(Strict):
    name: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    description: str | None = None
    parameters: dict
    strict: bool | None = None

class Tool(Strict):
    type: Literal['function']
    function: FunctionDef

class FunctionChoice(Strict):
    name: str
class ToolChoice(Strict):
    type: Literal['function']
    function: FunctionChoice
class StreamOptions(Strict):
    include_usage: bool = False

class ChatRequest(Strict):
    model: Literal['day14-coder']
    messages: list[Message] = Field(min_length=1, max_length=200)
    tools: list[Tool] | None = Field(default=None, max_length=64)
    tool_choice: Literal['auto','none','required'] | ToolChoice | None = None
    stream: bool = False
    stream_options: StreamOptions | None = None
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    max_tokens: int = Field(default=4096, ge=1, le=8192)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=8192)
    n: Literal[1] = 1

    @model_validator(mode='after')
    def tools_consistent(self):
        if self.max_completion_tokens is not None:
            if 'max_tokens' in self.model_fields_set and self.max_tokens != self.max_completion_tokens:
                raise ValueError('conflicting output token limits')
            self.max_tokens = self.max_completion_tokens
        names=[t.function.name for t in self.tools or []]
        if len(set(names)) != len(names): raise ValueError('duplicate tool')
        if isinstance(self.tool_choice, ToolChoice) and self.tool_choice.function.name not in names: raise ValueError('unknown tool')
        if self.tool_choice == 'required' and not names: raise ValueError('missing tools')
        pending=set()
        for m in self.messages:
            if m.role == 'tool':
                if m.tool_call_id not in pending: raise ValueError('unexpected tool result')
                pending.remove(m.tool_call_id)
            else:
                if pending: raise ValueError('missing tool result')
                ids=[t.id for t in m.tool_calls or []]
                if len(set(ids))!=len(ids): raise ValueError('duplicate call id')
                pending.update(ids)
        if pending: raise ValueError('missing tool result')
        return self

class ReviewFile(Strict):
    path: str = Field(min_length=1, max_length=240)
    content: str
    @field_validator('path')
    @classmethod
    def safe_path(cls, path):
        if path.startswith('/') or '\\' in path or ':' in path or any(ord(c)<32 for c in path): raise ValueError('path')
        if any(x in ('','..','.') for x in path.split('/')): raise ValueError('path')
        if str(PurePosixPath(path)) != path: raise ValueError('path')
        return path

class ReviewRequest(Strict):
    stack_profile: Literal['python-fastapi']
    files: list[ReviewFile] = Field(min_length=1,max_length=20)
    task: str = Field(default='',max_length=8192)
    @model_validator(mode='after')
    def unique(self):
        if len({f.path for f in self.files})!=len(self.files): raise ValueError('duplicate path')
        return self

class Usage(Strict):
    prompt_tokens: int = Field(ge=0,le=2_000_000)
    completion_tokens: int = Field(ge=0,le=2_000_000)
    total_tokens: int = Field(ge=0,le=4_000_000)
    prompt_cache_hit_tokens: int = Field(ge=0,le=2_000_000)
    prompt_cache_miss_tokens: int = Field(ge=0,le=2_000_000)
    @model_validator(mode='after')
    def totals(self):
        if self.total_tokens != self.prompt_tokens+self.completion_tokens: raise ValueError('usage')
        if self.prompt_tokens != self.prompt_cache_hit_tokens+self.prompt_cache_miss_tokens: raise ValueError('cache usage')
        return self

def parse_json(raw: bytes, limit=512*1024):
    if len(raw)>limit: raise GatewayError('BODY_TOO_LARGE',413)
    try:
        text=raw.decode('utf-8'); depth=0; string=False; escaped=False
        for ch in text:
            if string:
                if escaped: escaped=False
                elif ch=='\\': escaped=True
                elif ch=='"': string=False
            elif ch=='"': string=True
            elif ch in '[{':
                depth+=1
                if depth>32: raise ValueError('depth')
            elif ch in ']}': depth-=1
        def pairs(items):
            obj={}
            for k,v in items:
                if k in obj: raise ValueError('duplicate')
                obj[k]=v
            return obj
        def invalid(_): raise ValueError('number')
        value=json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
        # Reject surrogate strings that cannot be sent as UTF-8.
        json.dumps(value,ensure_ascii=False).encode('utf-8')
        return value
    except (ValueError,UnicodeError,RecursionError): raise GatewayError('INVALID_REQUEST') from None

Severity = Literal['Critical','High','Medium','Low']
Category = Literal['API_KEY','EMAIL','CARD','PHONE','CONFIG_SECRET','SYSTEM_PROMPT','COMMAND','URL','INSPECTION_LIMIT','TOOL_POLICY']
class EventMeta(Strict):
    request_id: str = Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    key_id: str = Field(min_length=1,max_length=40,pattern=r'^[a-zA-Z0-9_-]+$')
    stage: Literal['chat','review','http']
    state: Literal['accepted','input_blocked','output_blocked','completed','unknown','failed','review_result']
    categories: tuple[Category,...] = ()
    policy_version: Literal['gateway-v1','python-fastapi-v1'] = 'gateway-v1'
    review_id: str | None = Field(default=None,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    decision: Literal['pass','warn','block'] | None = None
    severity_counts: dict[Severity,int] | None = None

class Finding(Strict):
    severity: Severity
    category: Literal['SECRET_EXPOSURE','UNSAFE_STORAGE','PII_LOGGING','INSECURE_TRANSPORT','INPUT_VALIDATION','INJECTION','DESERIALIZATION','PATH_TRAVERSAL','SSRF','AUTHORIZATION','OTHER']
    path: str = Field(min_length=1,max_length=240)
    line: int | None = Field(ge=1)
    message: str = Field(min_length=1,max_length=600)
    remediation: str = Field(min_length=1,max_length=600)

class Findings(Strict):
    findings: list[Finding] = Field(max_length=50)

class ReviewResponse(Strict):
    review_id: str
    request_id: str
    artifact_hash: str
    policy_version: Literal['python-fastapi-v1'] = 'python-fastapi-v1'
    stack_profile: Literal['python-fastapi'] = 'python-fastapi'
    decision: Literal['pass','warn','block']
    findings: list[Finding]
    usage: Usage
