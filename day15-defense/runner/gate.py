"""Deterministic acceptance gate. No source-controlled approvals."""
import hashlib
from .contracts import GateDecision

from .fingerprint import policy_fingerprint
POLICY_HASH=hashlib.sha256(policy_fingerprint().encode()).hexdigest()

class Gate:
    @staticmethod
    def evaluate(snapshot,checks,execution,review):
        reasons=[]
        if checks.status!='passed' or checks.artifact_hash!=snapshot.artifact_hash or checks.policy_hash!=POLICY_HASH:
            reasons.append('STATIC_NOT_PASSED')
        if execution.status!='passed' or execution.exit_code!=0 or execution.artifact_hash!=snapshot.artifact_hash:
            reasons.append('EXECUTION_NOT_PASSED')
        if not isinstance(review,dict) or review.get('artifact_hash')!=snapshot.artifact_hash or review.get('policy_version')!='python-fastapi-v1':
            reasons.append('REVIEW_INVALID')
        elif review.get('decision')!='pass' or review.get('findings')!=[]:
            reasons.append('REVIEW_NOT_PASSED')
        return GateDecision('deny' if reasons else 'pass',snapshot.id,snapshot.artifact_hash,POLICY_HASH,tuple(reasons))
