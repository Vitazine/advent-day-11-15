import hashlib
import hmac
import re
import time
from collections import deque
from dataclasses import dataclass
from .errors import GatewayError

@dataclass(frozen=True)
class Principal:
    key_id: str

def authenticate(header, settings):
    token=header[7:] if header and header.startswith('Bearer ') else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}\.[A-Za-z0-9_-]{43,128}',token):
        raise GatewayError('UNAUTHORIZED',401)
    key_id=token.split('.')[0]
    actual=hashlib.sha256(token.encode()).hexdigest()
    expected=settings.token_hashes.get(key_id,'0'*64)
    if not hmac.compare_digest(actual,expected): raise GatewayError('UNAUTHORIZED',401)
    return Principal(key_id)

class IngressLimiter:
    def __init__(self): self.entries={};self.salt=__import__('secrets').token_bytes(32)
    def attempt(self, address):
        now=time.monotonic()
        key=hmac.new(self.salt,address.encode(),hashlib.sha256).digest()
        for old in list(self.entries):
            if not self.entries[old] or self.entries[old][-1]<=now-60: del self.entries[old]
        if key not in self.entries and len(self.entries)>=4096: raise GatewayError('RATE_LIMIT',429)
        q=self.entries.setdefault(key,deque())
        while q and q[0]<=now-60:q.popleft()
        if len(q)>=30: raise GatewayError('RATE_LIMIT',429)
        q.append(now)
