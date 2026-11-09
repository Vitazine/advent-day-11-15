"""Shared guarded path for chat and independent review."""
import asyncio
import time
import uuid
from dataclasses import dataclass
from .contracts import EventMeta, Usage
from .errors import GatewayError
from .guards import inspect_payload, GuardDecision
from .provider import ProviderFailure, estimate_reservation, usage_cost

@dataclass
class GatewayResult:
    request_id: str
    message: dict
    finish_reason: str
    usage: Usage
    cost_nano: int

def tools_allowed(payload,message):
    """Enforce request capabilities; tool text cannot grant new capabilities.

    Declaring a tool is not human consent to its side effects. The client
    executor must independently authorize each action before executing it.
    """
    names={tool['function']['name'] for tool in payload.get('tools') or []}
    calls=message.get('tool_calls') or []
    choice=payload.get('tool_choice') or 'auto'
    if choice=='none':return not calls
    if isinstance(choice,dict):
        return bool(calls) and all(call['function']['name']==choice['function']['name'] and call['function']['name'] in names for call in calls)
    if choice=='required' and not calls:return False
    return all(call['function']['name'] in names for call in calls)

class GatewayService:
    def __init__(self,settings,provider,ledger):
        self.settings,self.provider,self.ledger=settings,provider,ledger
        self.halted=False
    async def call(self,principal,payload,*,stage,review_id=None,exact_secrets=(),charge_attempt=True):
        payload=dict(payload,model=self.settings.model,stream=False,thinking={'type':'disabled'})
        payload.pop('stream_options',None);payload.pop('n',None)
        payload.pop('max_completion_tokens',None)
        rid=uuid.uuid4().hex
        meta=EventMeta(request_id=rid,key_id=principal.key_id,stage=stage,state='accepted',review_id=review_id,
                       policy_version='python-fastapi-v1' if stage=='review' else 'gateway-v1')
        secrets=tuple(s for s in (self.settings.api_key,*exact_secrets) if s)
        try:
            if self.halted or not self.settings.ready:raise GatewayError('UNAVAILABLE',503)
            self.ledger.cleanup()
            if charge_attempt:self.ledger.attempt(principal.key_id)
            amount=estimate_reservation(payload,self.settings)
            checked=inspect_payload(payload,direction='input',exact_secrets=secrets,profile='review' if stage=='review' else 'coding')
            if not checked.allowed:
                self.ledger.record(meta.model_copy(update={'state':'input_blocked','categories':checked.categories}))
                raise GatewayError('INPUT_BLOCKED',422,checked.categories)
            self.ledger.reserve(principal.key_id,amount,meta)
        except GatewayError as e:
            e.request_id=rid;raise
        except Exception:raise GatewayError('UNAVAILABLE',503) from None
        started=time.monotonic()
        def finish(cost,usage,state):
            try:self.ledger.finish(rid,cost,usage,state,int((time.monotonic()-started)*1000))
            except Exception:
                self.halted=True
                raise GatewayError('UNAVAILABLE',503) from None
        try:
            result=await self.provider.complete(payload)
        except asyncio.CancelledError:
            # Synchronous bounded SQLite operation has no await cancellation point.
            try:finish(amount,None,'unknown')
            except GatewayError:pass
            raise
        except ProviderFailure as e:
            finish(usage_cost(e.usage,self.settings) if e.usage else amount,e.usage,'failed' if e.usage else 'unknown')
            e.request_id=rid;raise
        except Exception:
            finish(amount,None,'unknown')
            error=GatewayError('UPSTREAM_ERROR',502);error.request_id=rid;raise error from None
        try:
            cost=usage_cost(result.usage,self.settings)
            checked=inspect_payload(result.message,direction='output',exact_secrets=secrets,profile='review' if stage=='review' else 'coding')
            if not tools_allowed(payload,result.message):
                checked=GuardDecision(False,tuple(sorted(set(checked.categories)|{'TOOL_POLICY'})))
            if not checked.allowed:
                self.ledger.record(meta.model_copy(update={'state':'output_blocked','categories':checked.categories}))
            finish(cost,result.usage,'completed' if checked.allowed else 'output_blocked')
            if cost>amount:raise GatewayError('SAFETY_HALT',503)
            if not checked.allowed:raise GatewayError('OUTPUT_BLOCKED',422,checked.categories)
        except GatewayError as e:
            e.request_id=rid;raise
        except Exception:
            finish(amount,None,'unknown')
            error=GatewayError('UNAVAILABLE',503);error.request_id=rid;raise error from None
        return GatewayResult(rid,result.message,result.finish_reason,result.usage,cost)
