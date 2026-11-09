# Day15 — обязательные проверки и партнёрский API

[Самостоятельный запуск через API](PARTNER_START.md) · [Клиент](tools/partner_client.py)

API предлагает создание задания, статус, принятие и скачивание только принятого
артефакта. JSON files/task, постоянная принадлежность токену, идемпотентность,
лимиты бюджета/запусков, единственное активное задание, отказ при сбоях.

Доверенный runner проверяет весь снимок: фиксированные Ruff/Bandit/AST/unittest
на Linux, независимый review, совпадение SHA256 и политики перед accept. Сгенерированный
код не исполняется вне ограниченного worker. Root broker проверяет Unix peer UID;
непривилегированное API не получает SSH/sudo. Native generator используется API-режимом,
OpenCode CLI — отдельным локальным режимом.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m redteam.run --mode deterministic
```

58 unit/regression-тестов,32 синтетических сценария (24 атакующих,8 чистых).
`requirements-worker.txt` задаёт отдельное окружение исполнителя. Административные
примеры systemd/nginx и installer находятся в `deploy/`. Перед собственным deployment
нужны свои credentials, хост, совместимые версии API/worker и проверенный rollback.

Публичная копия очищена от эксплуатационных данных: SSH-хост — пример. Она не
содержит приватного evidence, поэтому `runner doctor` не может подтвердить готовность
по одному клону. Партнёру для API-запуска doctor и административная настройка не нужны.

Лимиты исходников: Python/FastAPI,20 файлов,192KiB UTF-8. Нет установки зависимостей
из проекта. `.git`, `.opencode`, `.env`, conftest.py и startup hooks отклоняются.
Worker:192MiB RAM,50%CPU,64tasks,120секунд,1MiB вывода, отключённая сеть, read-only source.
Общее ядро, эвристики и недоверенные тесты остаются ограничениями защиты.
