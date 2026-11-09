# Day14-v2 — LLM gateway и security review

Python3.12/FastAPI, OpenAI-compatible `/v1/chat/completions`, `/v1/models`, `/v1/limits`
и независимый `/v1/security/reviews`. Bearer authentication, постоянный бюджет,
проверки входа/выхода, ограниченное декодирование DLP и строгий review-контракт.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/configure.py
```

`configure.py` скрыто запрашивает ключ провайдера и создаёт приватную `.local/credentials`.
Существующую папку не перезаписывает. Не публикуйте её содержимое или журналы.

```sh
export DAY14_TOKENS_FILE="$PWD/.local/credentials/tokens.json"
export DAY14_UPSTREAM_KEY_FILE="$PWD/.local/credentials/upstream-key"
export DAY14_DATA_DIR="$PWD/.local/data"
.venv/bin/python -m gateway
```

Один worker, локальный адрес `http://127.0.0.1:8141/v1`. Примеры service/nginx находятся
в `deploy/`; installer предназначен для заранее подготовленного администратором хоста,
а не для запуска партнёром. Не запускайте его вслепую на чужом сервере.

OpenCode2.2.6 проверен с V2-конфигурацией `opencode-v2.example.json`. Токен передаётся
через `DAY14_PROXY_TOKEN`; конфликтующие max_tokens/max_completion_tokens отклоняются.
Файл `openapi.json` описывает API. Unit suite содержит91 тест; они используют синтетические данные.

Прокси сам не делает тесты и принятие кода обязательными. Для полного защищённого
цикла используйте [Day15](../day15-defense/README.md).
