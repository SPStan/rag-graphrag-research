# Целевой API: ограниченная проверка issue #8

## Dense target smoke — issue #10

План [dense-target-smoke-plan.json](../results/summary/dense-target-smoke-plan.json) фиксирует первые пять development ID каждого набора и SHA. Малый корпус: все supporting-пассажи этих вопросов плюс 20 фиксированных distractors; результаты являются проверкой работоспособности, не benchmark. Для MuSiQue и HotpotQA используется один неизменённый one-shot MuSiQue reader, cosine top-5 и общий answer parser/оценщик. Выбор и пределы — [ADR-0018](../.adr/0018-dense-target-functionality-smoke.md).

Команды из корня новой рабочей копии; `<data-root>` содержит закреплённые `data/processed/{musique,hotpotqa}`. `<env-file>` — локальный игнорируемый файл с настройками из раздела «Повторение»; ключ не передавать в командной строке.

```powershell
python -m scripts.run_dense_target --data-root '<data-root>'
python -m scripts.run_dense_target --data-root '<data-root>' --env-file '<env-file>' --execute
```

Первая команда проверяет данные и план без запросов к моделям. Вторая расходует токены: последовательно до пяти reader-запросов на набор, Qwen3.8-27b, max_tokens=512, temperature=0, seed=42, reasoning выключен. Лимит 100 000 суммарных local embedding / remote LLM токенов на набор; reader input ≤16 000 UTF-8 байт. Неизвестный usage, неподдерживаемый формат, неполный ответ или нарушение лимитов останавливают запуск; перед повтором разобрать failed manifest. Ни SDK, ни скрытого retry в этом пути нет; Requests adapter дополнительно проверяется на `max_retries.total=0`.

Для отдельной диагностики разрешён один ID исходного плана: `--dataset musique --diagnostic-question 2hop__21104_16334 --execute`. Корпус остаётся тем же; запросы/контекст и ответы сохраняются локально до validation. Диагностический бюджет — 20 000 токенов; `--diagnostic-prior-run '<manifest>'` допускает вторую попытку только после проверенной первой, с остатком общего бюджета, без цепочки третьих попыток. Выбор следующей попытки требует конкретного обоснования по первому ответу. В выполненной диагностике понадобился только один remote POST.

Новая execution version `standalone-answer-line-v1` сохранена в существующем plan отдельно от исходных datasets. Общий target parser `run_dense.extract_target_reader_answer` распознаёт `Answer:` в начале отдельной строки, отклоняя несколько финальных строк. Прежний parser сохраняет историческую семантику inline-маркеров. Новый parser version записан в rows/plan и суффиксе metric version; оценщик не смешивает версии. Reader prompt, cap=512 и параметры API не менялись. Index embedding отправляется batch по 8 пассажей; повторный расход полностью учитывается.

Raw JSONL, `*.manifest.json`, `*.metrics.json`, `*.tokens.jsonl` сохраняются в игнорируемом `results/raw`. Failed manifest хранит наблюдаемые и незавершённые ID. Перед оценкой `evaluate_dense` проверяет порядок ID; локальная автоматическая оценка выполняется после успешного завершения всех пяти ответов. Отдельная проверка файла:

```powershell
python -m scripts.evaluate_dense '<raw-jsonl>' --labels '<data-root>/data/processed/<dataset>/labels.json'
```

SDK-проверка HippoRAG остаётся условием его будущего запуска, Dense использует непосредственно Requests. Draft #10 зависит от открытого PR #28; слияние и научное согласование не подразумеваются.

### Фактический результат 8 октября

[Безопасная сводка](../results/summary/dense-target-smoke.json): MuSiQue run `0b41ddc1-9e9f-4243-8679-e91d86b085ee`, код `afd60ab`. Первый ответ принят; второй не прошёл проверку `finish_reason=stop` и однозначного `Answer:`. Запуск остановлен, три оставшихся вопроса не отправлены, HotpotQA не начинался. Файл failed manifest и journal находятся в `results/raw` рабочей копии `dense-target-smoke`; SHA опубликованы в сводке. Первоначальный invalid response не сохранён целиком, поэтому точная причина (finish reason либо parser) не устанавливается; для будущих запусков добавлено сохранение локального `*.reader-error.json` с SHA и обоими признаками. Повторных вызовов после остановки не было.

Измеренный расход: index embedding 4215, query embedding 49; reader input 3226 / output 505. Все пять транспортных попыток имеют полный usage: один corpus embedding, два query embedding и два reader POST. Это полнота расхода выполненных попыток, не завершение плана на пяти вопросах. EM/F1/recall для полного плана не рассчитывались; критерии обоих завершённых датасетов ещё не выполнены. Дальнейший запуск — после отдельного решения о диагностике reader. Issue #10 и PR остаются открытыми/Draft с `Refs #10`.

### Завершение после диагностики 8 октября

Диагностический run `418cc922-198f-49cd-a748-8a75cd272bae` воспроизвёл ошибку: структура ответа валидна, `finish_reason=stop`, reasoning tokens=0, 1790 input / 195 output. Старый parser ошибочно считал фразу «Synthesize the answer:» внутри объяснения ещё одним финальным маркером. Новая версия выделяет отдельную строку `Answer:`; сохранённый diagnostic response успешно разобран offline без второго remote запроса. Старый run остаётся failed, утраченный исторический response не восстанавливается.

Оба финальных run выполнены на `4a60f2d` с теми же five-ID/corpus планами, prompt и output cap:

| Датасет | Run ID | Ответов | EM | F1 | recall@5 | Embedding tokens | LLM input / output |
|---|---|---:|---:|---:|---:|---:|---:|
| MuSiQue | `2ef2397b-2ec2-4696-a5bd-d55542998b6a` | 5 | 0,80 | 0,9333 | 1,0 | 4369 | 7702 / 1170 |
| HotpotQA | `291f34e6-6c03-4a66-a0a7-e9e6519ee875` | 5 | 0,40 | 0,48 | 1,0 | 4434 | 7593 / 883 |

Оба завершённых файла проверены существующим оценщиком: все пять ID в ожидаемом порядке, SHA результатов, journals и сохранённых reader request/response совпадают. Reasoning usage всех десяти reader-ответов — 0 по ответам API. Метрики относятся к малым development-корпусам с сохранёнными supporting-пассажами и не устанавливают научную эффективность метода.

Полный расход работы включает исходный failed run, одну диагностику и два финальных run: **17 311 local embedding, 20 311 LLM input, 2753 output tokens**, 39 физических попыток, из них 13 reader POST. Все usage известны; не путать это с расходом только финальных ответов. Полные параметры, source hashes, длительности, метрики, исторические ошибки и файлы — в [обновлённой сводке](../results/summary/dense-target-smoke.json). Raw находятся в `results/raw` рабочей копии `dense-target-smoke`, ключ — в игнорируемом env основной папки. Команда реального повторения, использованная после коммита:

```powershell
.\.venv-check\Scripts\python.exe -m scripts.run_dense_target --data-root 'C:\Users\Elisei\Documents\ChatGPT\Rag, GraphRAG' --env-file 'C:\Users\Elisei\Documents\ChatGPT\Rag, GraphRAG\.env.target-api' --execute
```

Технический smoke завершён; PR #29 пока Draft/Refs #10 из-за открытой зависимости PR #28 и неподтверждённого актуального научного согласования. Merge отдельно; #11/#12 не запускались.

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

HippoRAG SDK retries для этого runner отключены (`max_retry_attempts=0`); явные OpenIE retry остаются отдельными SDK вызовами. Cache hit фиксируется без новой физической попытки и без повторного прибавления исторических токенов. `producer_run_id` указывает происхождение, но не доказывает расход: `historical_cache_cost_complete=true` допустим только при проверенном завершённом журнале производителя с полной index-фазой и совпадением batch count/usage. Старый manifest без журнала остаётся неизвестным. Путь HippoRAG проверен fake SDK и старыми offline-тестами; реальное окружение и будущая целевая модель на нём не проверялись.

Manifest хранит имя, SHA-256 и сводку журнала. Экспорт MLflow/Langfuse проверяет SHA, run ID и сумму до записи, экспортирует ссылку/артефакт с тем же run ID и помечает старые manifests как `legacy_unknown`. Post-hoc экспорт не является новым модельным расходом. Для проверки полноты: сверить количество `started` с транспортными попытками, отсутствие незавершённых записей, `complete` каждой фазы/provider, `historical_cache_cost_complete`, SHA в manifest и итог из `known_subtotal`. При `complete=false` subtotal нельзя называть полным total.

При оборванной **последней** строке JSONL корректные строки читаются без изменения файла; summary получает `journal_corrupt_tail=true`, размер хвоста и `complete=false`. Failed manifest может сохранить такую сводку и SHA исходного повреждённого журнала. Возобновление записи в него запрещено. Повреждение завершённой строки или строки внутри файла остаётся ошибкой чтения и не скрывается как допустимый хвост.

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
