"""Independent review; only the server computes the decision."""
import hashlib
import json
import uuid
from pathlib import Path
from .contracts import Findings, ReviewResponse, EventMeta, parse_json
from .errors import GatewayError

POLICY='python-fastapi-v1'
PROMPT=Path(__file__).with_name('prompts').joinpath('python_fastapi.txt').read_text()

def artifact_hash(files):
    canonical=json.dumps([[f.path,f.content] for f in sorted(files,key=lambda f:f.path)],ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(canonical.encode()).hexdigest()

def build_review_payload(request,settings):
    return {'model':settings.model,'messages':[{'role':'system','content':PROMPT},
            {'role':'user','content':json.dumps(request.model_dump(),ensure_ascii=False,separators=(',',':'))}],
            'max_tokens':8192,'stream':False,'temperature':0}

def validate_findings(message,files):
    try:
        parsed=Findings.model_validate(parse_json(message.encode(),limit=1024*1024)).findings
        lines={f.path:len(f.content.splitlines()) for f in files}
        for finding in parsed:
            if finding.path not in lines or (finding.line is not None and finding.line>lines[finding.path]):raise ValueError('location')
        return parsed
    except Exception:raise GatewayError('INVALID_REVIEW',502) from None

def decide(findings):
    if any(f.severity in ('Critical','High') for f in findings):return 'block'
    return 'warn' if findings else 'pass'

async def review(request,principal,service,exact_secrets=(),charge_attempt=True):
    review_id=uuid.uuid4().hex
    result=await service.call(principal,build_review_payload(request,service.settings),stage='review',review_id=review_id,exact_secrets=exact_secrets,charge_attempt=charge_attempt)
    try:
        if result.finish_reason!='stop' or result.message.get('tool_calls'):raise GatewayError('INVALID_REVIEW',502)
        findings=validate_findings(result.message['content'],request.files)
        decision=decide(findings)
        service.ledger.record(EventMeta(request_id=result.request_id,key_id=principal.key_id,stage='review',state='review_result',
                              policy_version=POLICY,review_id=review_id,decision=decision,
                              severity_counts={s:sum(f.severity==s for f in findings) for s in ('Critical','High','Medium','Low')}))
    except GatewayError as e:e.request_id=result.request_id;raise
    except Exception:
        error=GatewayError('UNAVAILABLE',503);error.request_id=result.request_id;raise error from None
    return ReviewResponse(review_id=review_id,request_id=result.request_id,artifact_hash=artifact_hash(request.files),decision=decision,findings=findings,usage=result.usage)
