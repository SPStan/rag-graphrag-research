# Целевой API: ограниченная проверка issue #8

## Учёт попыток для issue #9 (offline-реализация)

Новые запуски создают рядом с результатом `*.tokens.jsonl`. Каждая физическая попытка имеет `started` (сохранён и fsync до транспорта) и `finished` с общим `attempt_id`; `operation_id` связывает явные повторы. Журнал хранит run ID, метод, датасет, provider, модель, фазу (`index`, `retrieval`, `reader`), операцию, ID объекта, статус, время, безопасный код ошибки и раздельные `llm_input_tokens`, `llm_output_tokens`, `embedding_input_tokens`. Отсутствие поля usage означает `null` и неполный итог; неприменимое поле другого типа токенов также `null`, но при агрегации не считается пропуском. Записи не содержат prompt, response, ключей и заголовков. Таймаут имеет неизвестный исход и расход. `total_tokens` и reasoning входят в сведения ответа, но не прибавляются второй раз.

| Путь вызова | Provider и фаза | Точка записи | Offline-проверка |
|---|---|---|---|
| `check_target_api.local_embedding` | local Ollama, index | вокруг `/api/embed` | `test_token_accounting` |
| `check_target_api.remote_generation` | target API, reader | вокруг `/chat/completions` | `test_token_accounting`, `test_check_target_api` |
| `run_dense.embed_corpus` | local Ollama, index | `post_json` каждого batch | `test_token_accounting`, `test_dense` |
| `run_dense.run`: query/embed и chat | local Ollama, retrieval/reader | `post_json` до проверки вектора/ответа | `test_token_accounting`, `test_dense` |
| `run_hipporag`: native embed | local Ollama, index/retrieval | каждый POST, включая split после HTTP 400 | `test_token_accounting`, `test_run_hipporag` |
| `run_hipporag`: SDK chat | HippoRAG SDK, OpenIE/retrieval/reader | `chat.completions.create` ниже SQLite cache | fake SDK в `test_token_accounting` |

HippoRAG SDK retries для этого runner отключены (`max_retry_attempts=0`); явные OpenIE retry остаются отдельными SDK вызовами. Cache hit фиксируется без новой физической попытки и без повторного прибавления исторических токенов. Если producer run неизвестен, `historical_cache_cost_complete=false`. Путь HippoRAG проверен fake SDK и старыми offline-тестами; реальное окружение и будущая целевая модель на нём не проверялись.

Manifest хранит имя, SHA-256 и сводку журнала. Экспорт MLflow/Langfuse проверяет SHA, run ID и сумму до записи, экспортирует ссылку/артефакт с тем же run ID и помечает старые manifests как `legacy_unknown`. Post-hoc экспорт не является новым модельным расходом. Для проверки полноты: сверить количество `started` с транспортными попытками, отсутствие незавершённых записей, `complete` каждой фазы/provider, `historical_cache_cost_complete`, SHA в manifest и итог из `known_subtotal`. При `complete=false` subtotal нельзя называть полным total.

Корневой Langfuse trace хранит проверенную `token_accounting_summary`, `token_accounting_complete` и `historical_cache_cost_complete`. `token_accounting_status=verified` подтверждает целостность журнала, **не** полноту затрат. Usage дочерней generation observation остаётся usage финального ответа из rows; дополнительные попытки и неизвестный расход видны в корневой summary и не прибавляются к нему второй раз.

Для закреплённого HippoRAG commit `1438aba` проверено по исходному коду: `BaseConfig.max_retry_attempts=0` допускается и передаётся в `OpenAI(max_retries=0)`; OpenAI SDK документирует ноль как отключение retry. Runner дополнительно проверяет значения `llm.max_retries` и `llm.openai_client.max_retries` до вызовов. Перед первым разрешённым малым запуском ещё нужно подтвердить поведение фактической установленной версии SDK на подставном HTTP-транспорте; fake `create` в текущем offline-наборе этого не доказывает.

Синтетический контроль: index embedding 19, retrieval embedding 7, reader LLM 23 input и 4 output дают раздельно 26/23/4. Дополнительный reader timeout без usage оставляет эти известные суммы, но полный итог неизвестен. Повторное чтение журнала не увеличивает числа. Это тестовый пример, не результат эксперимента.

Статус на 6 октября 2026: **простая генерация и локальные эмбеддинги проверены вместе**. Первый короткий запрос к Qwen не вернул текст; отдельная ограниченная диагностика нашла рабочий способ выключить reasoning, после чего итоговый smoke прошёл с пределом 32 токена. Это проверка интерфейса, не benchmark качества и не проверка OpenIE.

## Подтверждённые условия и границы

Куратор сообщил: адрес `https://api.duckduck.cloud/v1`, модель `iairlab/qwen3.8-27b`, локальный BGE-M3 вместо удалённой модели эмбеддингов. Контекст Qwen3.8 — 262k токенов по сообщению куратора; в этом smoke предел не измерялся. Он также сообщил о поддержке JSON mode/JSON Schema и `enable_thinking: false`, закреплённых именах моделей и снятии прежнего административного лимита 90 млн токенов. Точную ревизию backend, применение параметра и устойчивость под параллельной нагрузкой эта проверка не установила. Протокольный предел issue #8 — 50 000 учтённых токенов — сохраняется.

Для этого endpoint проверен параметр `chat_template_kwargs: {enable_thinking: false}` в теле запроса. [Qwen quickstart](https://github.com/QwenLM/Qwen3/blob/main/docs/source/getting_started/quickstart.md) показывает такой способ для OpenAI-совместимого vLLM. Это не устанавливает тип лабораторного backend; результат подтверждён только фактическим ответом и usage.

## Повторение

Локально в игнорируемом Git файле `.env.target-api` указать:

```text
TARGET_API_BASE_URL=https://api.duckduck.cloud/v1
TARGET_API_MODEL=iairlab/qwen3.8-27b
LITELLM_API_KEY=<ключ из закрытого канала>
OLLAMA_EMBED_MODEL=bge-m3:latest
```

Запустить Ollama с уже установленным BGE-M3. Для чистой рабочей копии сначала создать проверочное окружение по `AGENTS.md` (`UV_PROJECT_ENVIRONMENT=.venv-check`, затем `uv sync --locked`). Из корня рабочей копии:

```powershell
.\.venv-check\Scripts\python.exe scripts\check_target_api.py --output results/summary/target-api-new-check.json
```

Скрипт читает настройки из окружения и `.env.target-api` в текущей папке. Он проверяет настройки и **резервирует новый файл отчёта до запросов**; существующий файл не перезаписывается. Стандартный smoke делает по одному локальному и удалённому запросу без retry с `max_tokens=32` и `chat_template_kwargs: {enable_thinking: false}`. Известные локальные токены и время сохраняются даже при некорректных векторах; в этом случае удалённого вызова нет. Локальный usage проверяется до удалённого вызова; известные поля удалённого usage сохраняются и при превышении лимита или неполном ответе. Исходный отчёт `results/summary/target-api-check.json` сохранён как свидетельство первой попытки, успешный — в `results/summary/target-api-verified.json`. Для диагностики одного удалённого запроса без локального embedding предусмотрен `--generation-only --max-tokens 64 --output <новый файл>`. Ключ и заголовки авторизации в отчёт не попадают.

## Полученный результат

| Часть | Результат | Учёт |
|---|---|---|
| Локальный BGE-M3, первый smoke | 2 из 2 векторов, размерность 1024, digest `79076464…2146bab`, 5,64 с | 19 локальных prompt tokens |
| Удалённая Qwen3.8: исходный smoke | 1 запрос, текстового `message.content` не получено; `remote_answer_missing` | Неизвестен: ответ не сохранён после ошибки проверки |
| Диагностика, top-level `enable_thinking=false`, cap 256 | Ответ «Четыре», `finish_reason=stop` | 63 input + 71 output = 134; из output 65 reasoning tokens |
| Диагностика, `chat_template_kwargs`, cap 64 | Ответ «Четыре», `finish_reason=stop` | 23 input + 4 output = 27; reasoning tokens = 0 |
| Итоговый smoke, `chat_template_kwargs`, cap 32 | Ответ «Четыре» и 2 локальных вектора размерности 1024; обе части `verified`; локальный BGE-M3 — 4,776 с | 19 локальных embedding tokens отдельно; удалённые 23 input + 4 output = 27, reasoning tokens = 0 |
| `GET /user/daily/activity` | Не проверялся: схема и права доступа не подтверждены | Суточную статистику нельзя приписать одному запросу |

Был ещё один запрос с `chat_template_kwargs`, ответ которого не сохранился из-за отказа файловой системы записать отчёт; его usage **неизвестен**. Итого отправлено пять удалённых запросов: исходный smoke, top-level диагностика, два диагностических chat-template запроса и итоговый smoke. Это **превысило исходный предел issue #8 в один запрос**: после первого блокера пользователь отдельно попросил «Попытайся решить сам» вместо обращения к куратору, и диагностика выполнялась по этому последующему поручению. [Куратор принял это отклонение в PR #26 7 октября 2026 года](https://github.com/SPStan/rag-graphrag-research/pull/26); два случая неизвестного usage остаются неизвестными, их нельзя считать нулевыми. Новых вызовов при исправлении замечаний ревью не было. При top-level варианте 65 reasoning tokens позволяют предположить, что исходный cap 32 был исчерпан рассуждением; доказать это для первого ответа нельзя. На успешном chat-template ответе reasoning tokens = 0. JSON mode, JSON Schema, стабильность backend, работа OpenIE и генерация на датасете ещё не проверялись. Перед E1/E2 нужны отдельные ограниченные проверки и замороженный протокол; обращаться к куратору за разъяснением этого короткого ответа уже не требуется. Полные данные датасетов и индексы не затрагивались.
