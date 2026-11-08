"""Read only the agreed local generic password; never print subprocess output."""
from pathlib import Path
import subprocess

class KeychainError(Exception):
    pass

def read_api_key() -> str:
    try:
        result = subprocess.run(
            ['/usr/bin/security', 'find-generic-password', '-s', 'YOUR_KEYCHAIN_SERVICE',
             '-a', 'YOUR_KEYCHAIN_ACCOUNT', '-w', str(Path.home() / 'Library/Keychains/login.keychain-db')],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=False)
        if result.returncode:
            raise KeychainError('Keychain: объект недоступен или доступ отменён')
        key = result.stdout.decode('utf-8').strip()
        if not key or len(key) > 1024 or any(c.isspace() for c in key) or not key.isascii():
            raise KeychainError('Keychain: некорректное значение')
        return key
    except KeychainError:
        raise
    except Exception:
        raise KeychainError('Keychain: чтение не выполнено') from None
