# Issue #11 — ограниченная проверка проблемных OpenIE случаев

## Текущая граница

Источник: development run `e78eff08-532a-40b3-a359-49a6b08b32a7`, исходный граф из 5500 passages. Terminal outcomes: 37 NER truncated, 122 triples truncated, один NER request_error. Это 160 исходов стадий, не обязательно 160 документов. Отдельной terminal parse_error группы в этом источнике нет; broken JSON при length относится к усечению. 159 ответов доступны в неизменяемом историческом SQLite-кэше по SHA; request_error не имеет ответа и его исторический usage неизвестен.

Протокол выбора и причины — [ADR-0019](../.adr/0019-target-openie-context-prerequisite.md). До пяти представителей: минимальный/максимальный размер сохранённого truncated response отдельно для NER/triples, один отсутствующий ответ. Bytes характеризуют примеры, а не дают число target tokens. Правильные QA-ответы и supporting labels не читаются для подготовки prompts.

Целевые metadata endpoints `/v1/models`, `/model/info`, `/v1/model/info` доступны с нашим ключом, но не предоставляют проверенные context/output limits и tokenizer/revision модели `iairlab/qwen3.8-27b`. Пользователь подтвердил, что эти лимиты неизвестны. Поля LiteLLM `max_input_tokens` и `max_output_tokens` имеют разный смысл; общий контекст нельзя выводить из одного max_tokens ([официальная схема](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.schema.json)).

**Блокер:** нет проверяемого контракта контекста и точного target счётчика input tokens для выбранных prompts. Прежний usage локальной qwen2.5:3b и byte lengths этого не заменяют. Генерация не запускается, готовность индексации не заявляется. Режим preflight не имеет пути chat completions, embeddings, repair или rebuild.

## Воспроизведение

Из рабочей копии с отдельным SDK-окружением по `requirements-hipporag-sdk-check.txt`; чистый checkout HippoRAG `1438aba3` находится в `<sdk-source>`. `<data-root>` содержит исходные `data/processed` и исторический run; индекс/SQLite пути берутся из исходного manifest. `.env` не коммитится.

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:LITELLM_LOCAL_MODEL_COST_MAP = 'True'
.cache/hipporag-sdk-venv/Scripts/python.exe -m scripts.preflight_hipporag_repair_prompts --target-api-check --data-root '<data-root>' --manifest '<source-manifest>' --env-file '<env-file>' --sdk-source '<sdk-source>' --output '<new-report.json>'
```

Новый output обязателен: существующий target report не перезаписывается. Источники проверяются SHA до/после, кэш открыт immutable/read-only; все установленые Python-файлы HippoRAG сравниваются с закреплённым source checkout. Исторические ответы и подготовленные prompts сохраняются только локально в `results/raw/openie-target-<run-id>.cases.json`; безопасная summary содержит IDs/SHA/параметры/статусы без текста и секретов. Новые попытки модели учитываются пустым журналом: ноль физически отправленных запросов; target usage для неотправленных случаев не измерен (`null`), неизвестный исторический usage также не подменяется нулём.

## До/после и готовность

До: сохранённые truncated/request_error воспроизводятся существующим строгим классификатором. Синтаксически исправный или частично восстановленный JSON с finish_reason=length всё равно отвергается. После: целевая генерация **не выполнялась**, исправление качества извлечения **не подтверждено**. По этой причине issue #11 остаётся открытой с конкретным блокером, а PR — Draft/Refs #11. Сохранённый граф не объявляется пригодным для основного сравнения.

Фактический новый run ID, пять строк до/после, SHA и результат проверки будут внесены после выполнения no-generation preflight. Machine waiting не считается активными часами пользователя; активные часы не измерялись.

## Следующее необходимое действие

Провайдер/куратор должен подтвердить context window, максимальный output, exact tokenizer/backend revision либо серверный endpoint точного счёта этих prompts. После проверки fit отдельно выполнить до пяти выбранных примеров с пофазным журналом, согласованным бюджетом и максимум двумя исправлениями одной причины. Этот PR не разрешает старый attempt 4, очередь из 196 repair задач, embeddings, rebuild или QA.
