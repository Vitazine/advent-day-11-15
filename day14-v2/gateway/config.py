"""Server-controlled settings. Credentials are files, never CLI values."""
import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

@dataclass
class Settings:
    data_dir: Path = Path('.local')
    token_hashes: dict[str,str] = field(default_factory=dict, repr=False)
    api_key: str = field(default='',repr=False)
    model: str = 'deepseek-flash'
    price_date: str = '2026-11-08'
    context_limit: int = 1_048_576
    input_rate: int = 300
    cache_rate: int = 6
    output_rate: int = 1200
    timeout: float = 120
    audit_cap: int = 20*1024*1024
    @property
    def ready(self):
        try: return bool(self.api_key) and 0 <= (date.today()-date.fromisoformat(self.price_date)).days <= 7
        except ValueError: return False
    @classmethod
    def load(cls):
        def read(var):
            path=os.environ.get(var)
            return Path(path).read_text().strip() if path else ''
        return cls(data_dir=Path(os.environ.get('DAY14_DATA_DIR','.local')),
                   token_hashes=json.loads(read('DAY14_TOKENS_FILE') or '{}'),
                   api_key=read('DAY14_UPSTREAM_KEY_FILE'),
                   price_date=os.environ.get('DAY14_PRICE_DATE','2026-11-08'))
