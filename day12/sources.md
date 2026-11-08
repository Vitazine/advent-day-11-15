# Проверенные источники — 7 ноября 2026

- [Модель и API](https://api-docs.deepseek.com/): deepseek-flash соответствует DeepSeek-V4.1-Flash-1017 на дату проверки. Это алиас, не закреплённый immutable snapshot.
- [Тарифы](https://api-docs.deepseek.com/quick_start/pricing/): верхняя peak-оценка без кэширования $0.30/миллион входных и $1.20/миллион выходных токенов. В выходные опубликован off-peak вдвое ниже; стенд сохраняет верхнюю оценку.
- [Tool calls](https://api-docs.deepseek.com/guides/tool_calls/): non-thinking поддерживается; Chat Completions не поддерживает искусственно вставленные tool calls. Поэтому чтение запрашивается самой моделью.
- [API-контракт](https://api-docs.deepseek.com/api/create-chat-completion/): tools, tool_choice, tool messages, max_tokens.
- [Условия API](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) и [общие условия](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html): проверены перед прогоном. Эксперимент тестирует собственное downstream-приложение на синтетических данных, не атакует инфраструктуру провайдера, не извлекает чужие данные и не обходит мониторинг. Это интерпретация области эксперимента, не обещание одобрения провайдером или отсутствия блокировки.
- [Greshake et al., 2023](https://arxiv.org/abs/2302.12173), «Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection»: первичная работа о превращении извлекаемых данных в инструкции. Воспроизводимый здесь механизм — инструкция во внешней странице меняет поведение читающего агента. Это собственная упрощённая адаптация, без Bing, OCR, внешней пересылки и утверждения об идентичном payload.

Проверка /models отдельно подтверждает доступность API ID. Полное имя версии берётся из официальной документации, поскольку ответ API может вернуть только алиас.
