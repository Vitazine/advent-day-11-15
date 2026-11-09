"""Deterministic preflight; the same AST checks also run inside the sandbox."""
import re
import uuid
from sandbox.ast_checks import scan
from .contracts import CheckResult
from .gate import POLICY_HASH

class StaticChecks:
    @staticmethod
    def run(snapshot):
        reasons=set()
        for file in snapshot.files:
            if re.search(r'(?i)\b(?:sk-[a-z0-9_-]{8,}|ghp_[a-z0-9]{16,})',file.content):reasons.add('SECRET_PATTERN')
            if file.path.endswith('.py'):reasons.update(scan(file.content))
        return CheckResult('failed' if reasons else 'passed',snapshot.artifact_hash,POLICY_HASH,tuple(sorted(reasons)),uuid.uuid4().hex)
