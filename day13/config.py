"""No dotenv, CLI secrets or provider URL overrides."""
import hashlib
import hmac
import ipaddress
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

@dataclass
class Settings:
    api_key: str = ''
    ip_key: bytes = b''
    origin: str = 'https://example.com'
    price_date: str = '2026-11-08'
    data_dir: Path = Path('/var/lib/day13')

    @property
    def ready(self):
        try: age=(date.today()-date.fromisoformat(self.price_date)).days
        except ValueError: return False
        return bool(self.api_key and self.api_key!='UNCONFIGURED' and len(self.ip_key)>=32 and 0<=age<=7)

    def ip_id(self, raw):
        ip=ipaddress.ip_address(raw)
        if getattr(ip,'ipv4_mapped',None): ip=ip.ipv4_mapped
        value=str(ipaddress.ip_network(f'{ip}/64',strict=False)) if ip.version==6 else str(ip)
        return hmac.new(self.ip_key,value.encode(),hashlib.sha256).hexdigest()

    @classmethod
    def load(cls):
        directory=Path(os.environ.get('CREDENTIALS_DIRECTORY','/run/credentials/day13.service'))
        def read(name):
            try: return (directory/name).read_bytes().strip()
            except OSError: return b''
        key=read('deepseek')
        if len(key)>1024 or not key.isascii() or any(c in b' \r\n\t' for c in key): key=b''
        return cls(api_key=key.decode('ascii'),ip_key=read('ip-hmac'),
                   price_date=os.environ.get('DAY13_PRICE_DATE','2026-11-08'))
