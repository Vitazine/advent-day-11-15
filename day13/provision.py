#!/usr/bin/env python3
"""Run locally in your own terminal. Secrets stay in process memory and SSH stdin."""
import getpass
import json
import subprocess
import sys
from pathlib import Path


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Запустите в обычном терминале: требуется скрытый ввод.')
    key=getpass.getpass('Новый API-ключ DeepSeek (ввод скрыт): ').strip()
    password=getpass.getpass('Пароль сайта (15–64 байта, ввод скрыт): ')
    confirmation=getpass.getpass('Повторите пароль сайта: ')
    if password!=confirmation or not 15<=len(password.encode())<=64:
        raise SystemExit('Пароли не совпадают или длина вне диапазона.')
    if not key.startswith('sk-') or any(c.isspace() for c in key):
        raise SystemExit('Некорректный формат API-ключа.')
    command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','IdentitiesOnly=yes',
             '-i',str(Path.home()/'.ssh/YOUR_SSH_KEY'),'YOUR_SSH_USER@192.0.2.10',
             'sudo -n /usr/local/sbin/day13-set-credentials']
    result=subprocess.run(command,input=json.dumps({'api_key':key,'password':password}).encode(),
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        raise SystemExit('Настройка не завершилась. Проверьте SSH-доступ; значения не выведены.')
    print('Ключ установлен. Пользователь сайта: day13. Пароль — введённый вами.')
    print('Откройте https://example.com/day13/')

if __name__=='__main__':
    try: main()
    except (KeyboardInterrupt,EOFError): raise SystemExit('Отменено.')
