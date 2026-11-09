# Проверенная совместимость

OpenCode CLI 2.2.6 из Desktop, SHA256 закреплён в opencode/manifest.json.
Реально использованы V2 `providers`, пакет `@opencode/ai/providers/openai-compatible`,
`settings.baseURL`, env credential и deny-all permissions. Запуск private standalone,
чистые XDG/cwd, исходники только как JSON attachment. Tools не предоставляются.

V2 отправляет max_completion_tokens вместе с max_tokens. Gateway day14-v2 принимает
равные значения, нормализует в max_tokens для upstream, конфликтующие запрещает.
Токен реального gateway остаётся в runner; OpenCode получает временный localhost
relay token. Каждый forward резервирует бюджет, включая retry/title-запросы.

Наличие бинарника/конфига не считается e2e. Приватные e2e-записи и doctor.json в публичную копию не включены.
Цена доверия: закреплённый OpenCode исполняется на Mac без ОС-изоляции; его
встроенный permission механизм и отсутствие чужой конфигурации являются границей.

Официальные справочники, использованные при интеграции:
https://opencode.ai/docs/config/
https://opencode.ai/docs/providers/
https://opencode.ai/docs/permissions/
https://opencode.ai/docs/plugins/
