"""Bounded heuristic DLP. Does not execute, fetch, redact or log input."""
import base64
import codecs
import html
import ipaddress
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

PATTERNS=(
 ('API_KEY',re.compile(r'(?i)(?:sk-[a-z0-9_-]{3,}|gh[pousr]_[a-z0-9_]{8,}|AKIA[A-Z0-9]{16})')),
 ('EMAIL',re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')),
 ('CARD',re.compile(r'(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)')),
 ('PHONE',re.compile(r'(?<!\w)(?:\+\d[\d ()-]{8,}\d|\b[78][ (]+\d{3}[ )-]+\d{3}[ -]+\d{2}[ -]+\d{2})(?!\w)')),
)
B64=re.compile(r'(?<![\w+/=-])[A-Za-z0-9+/_-]{12,}={0,2}(?![\w+/=-])')
COMMAND=re.compile(r'(?i)(?:\b(?:curl|wget)\b[^\n]{0,300}\|\s*(?:ba)?sh\b|\brm\s+-[a-z]*(?:r[a-z]*f|f[a-z]*r)\b|\bpowershell\b[^\n]{0,300}-(?:enc|encodedcommand)|/dev/tcp/|\bchmod\s+777\b)')
URL=re.compile(r'(?i)\b(?:https?://|javascript:|data:|file:)[^\s<>"\x27]+')

@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    categories: tuple[str,...]

def luhn(value):
    digits=[int(c) for c in value if c.isascii() and c.isdigit()]
    return 13<=len(digits)<=19 and len(set(digits))>1 and sum((2*n-9 if n>4 else 2*n) if i%2 else n for i,n in enumerate(reversed(digits)))%10==0

def _scan(text,secrets,output):
    found=set()
    for category,pattern in PATTERNS:
        for m in pattern.finditer(text):
            if category!='CARD' or luhn(m.group()):found.add(category)
    if any(s and s in text for s in secrets):found.add('CONFIG_SECRET')
    if output:
        if 'REVIEW_POLICY_DAY14_V1' in text:found.add('SYSTEM_PROMPT')
        if COMMAND.search(text):found.add('COMMAND')
        for m in URL.finditer(text):
            try:
                u=urlsplit(m.group().rstrip('.,;)'));host=u.hostname or ''
                suspicious=u.scheme!='https' or bool(u.username)
                try:suspicious |= not ipaddress.ip_address(host).is_global
                except ValueError:suspicious |= host in ('localhost','bit.ly','tinyurl.com','t.co') or host.endswith(('.internal','.local','.onion'))
                if suspicious:found.add('URL')
            except ValueError:found.add('URL')
    return found

def inspect_payload(payload, *, direction, exact_secrets=(), profile='coding'):
    started=time.monotonic();found=set();strings=[];values=[];total=0;decoded_count=0
    try:
        def views(obj):
            strings=[];values=[];keys=[]
            def walk(item,depth):
                if depth>32:raise ValueError()
                if isinstance(item,dict):
                    for k,v in item.items():
                        strings.append(k);keys.append(k);walk(v,depth+1)
                elif isinstance(item,list):
                    for v in item:walk(v,depth+1)
                elif isinstance(item,str):
                    # Inspect semantic JSON contents, not JSON newline escape syntax.
                    # Otherwise a JSON-encoded newline before @app looks like an email.
                    if item.lstrip().startswith(('{','[')):
                        try:
                            from .contracts import parse_json
                            nested=parse_json(item.encode(),limit=1024*1024)
                        except Exception:nested=None
                        if isinstance(nested,(dict,list)):
                            walk(nested,depth+1)
                            return
                    strings.append(item);values.append(item)
                elif type(item) in (int,float):
                    value=str(item);strings.append(value);values.append(value)
            walk(obj,0)
            return [*strings, '\n'.join(strings), ''.join(values), ''.join(keys), ''.join(strings)]
        queue=[(v,True) for v in views(payload)]
        seen=set();decoded_candidates=set()
        for text,allow_rot13 in queue:
            if (text,allow_rot13) in seen:continue
            seen.add((text,allow_rot13));total+=len(text.encode('utf-8'))
            if total>2*1024*1024 or time.monotonic()-started>1:raise ValueError()
            found.update(_scan(text,exact_secrets,direction=='output'))
            if found:return GuardDecision(False,tuple(sorted(found)))
            if text.lstrip().startswith(('{','[')):
                try:
                    from .contracts import parse_json
                    nested=parse_json(text.encode(),limit=1024*1024)
                except Exception:
                    nested=None
                if isinstance(nested,(dict,list)):
                    queue.extend((v,allow_rot13) for v in views(nested))
            normal=''.join(c for c in unicodedata.normalize('NFKC',text) if unicodedata.category(c)!='Cf')
            joined=re.sub(r'''["']\s*\+?\s*["']''','',normal)
            escaped_unicode=re.sub(r'\\u[0-9a-fA-F]{4}', lambda m: chr(int(m.group()[2:],16)), normal)
            variants=[(v,allow_rot13) for v in (normal,unquote(normal),html.unescape(normal),escaped_unicode,joined)]
            # Whitespace removal creates synthetic long words. They must not be
            # mistaken for evidence that an ordinary sentence is ROT13 encoded.
            variants.append((re.sub(r'\s+','',joined),False))
            # ROT13 is not a self-identifying encoding. Do not reinterpret every
            # ordinary identifier (fx-rate -> sk-engr) or double the decode budget.
            rotated=codecs.decode(normal,'rot_13')
            known_rotated=(any(s and s in rotated for s in exact_secrets)
                           or 'REVIEW_POLICY_DAY14_V1' in rotated)
            rot13_candidate=(bool(re.search(r'(?i)\brot[_ -]?13\b',normal))
                             or any(len(m.group())>=19 for m in PATTERNS[0][1].finditer(rotated)))
            if known_rotated or (allow_rot13 and rot13_candidate):variants.append((rotated,False))
            for v,can_rotate in variants:
                if (v,can_rotate) not in seen:queue.append((v,can_rotate))
            for m in B64.finditer(normal):
                if m.group() in decoded_candidates:continue
                decoded_candidates.add(m.group())
                if len(decoded_candidates)>8192:raise ValueError()
                try:
                    raw=m.group();v=base64.b64decode(raw+'='*(-len(raw)%4),altchars=b'-_',validate=True).decode('utf-8')
                except (ValueError,UnicodeError):continue
                decoded_count+=1
                if decoded_count>512:raise ValueError()
                if v and (v,allow_rot13) not in seen and v!=text:queue.append((v,allow_rot13))
            if len(queue)>4096:raise ValueError()
        return GuardDecision(True,())
    except Exception:
        return GuardDecision(False,('INSPECTION_LIMIT',))
