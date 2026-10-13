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

Фактический run `70d727d7-00ff-414e-aeb8-f61e49d7800f` на чистом коде `56da1da`: **blocked_target_context_contract**, 5 случаев. [Безопасная summary](../results/summary/openie-target-preflight.json). Проверены все 61 Python-файлов установленного HippoRAG относительно `1438aba3`; SHA исходных manifest/corpus/state/cache до/после совпали. Частный case snapshot и пустой модельный журнал также проверены по SHA. Все три metadata GET получили HTTP 200, но нужные поля null. Новых модельных попыток 0; полная модельная проверка и исправление OpenIE не выполнены.

Исторический источник: qwen2.5:3b, Q4_K_M, num_ctx=4096, temperature=0, seed=42; NER truncated при 512 output tokens, triples при 2048. Новая модель iairlab/qwen3.8-27b: tokenizer/revision/context/output/quantization неизвестны. Output caps 1024/3072 в таблице — только предложение из прежнего stage-cap протокола, не подтверждённая конфигурация API.

| Стадия / passage SHA prefix | До: status / форма | Prompt bytes | Предлагаемый output cap | После: target |
|---|---|---:|---:|---|
| openie_ner / af7c103c3e75 | truncated / non_json | 1818 | 1024 | Не отправлен: context-fit неизвестен |
| openie_ner / 80c59521880e | truncated / non_json | 1589 | 1024 | Не отправлен: context-fit неизвестен |
| openie_triples / f520187048cf | truncated / non_json | 2825 | 3072 | Не отправлен: context-fit неизвестен |
| openie_triples / bf2985f3129a | truncated / non_json | 3051 | 3072 | Не отправлен: context-fit неизвестен |
| openie_ner / 225264f9bf8f | request_error / absent | 993 | 1024 | Не отправлен: context-fit неизвестен |

В отличие от полного расхода #10, эти нули означают отсутствие новых запросов модели, а не восстановление неизвестного старого расхода. Usage исторического request_error остаётся unknown; target usage не измерен. Индекс не изменялся и ready_for_indexing=false.

Целевые offline-тесты preflight/plan: 10 passed. Общий gate: 231 passed, 13 skipped; девять skips — SDK-набор, проверенный отдельно в #9, четыре прежних integration skips. Активные часы пользователя не измерялись; machine waiting не приписывается его труду.

## Следующее необходимое действие

Провайдер/куратор должен подтвердить context window, максимальный output, exact tokenizer/backend revision либо серверный endpoint точного счёта этих prompts. После проверки fit отдельно выполнить до пяти выбранных примеров с пофазным журналом, согласованным бюджетом и максимум двумя исправлениями одной причины. Этот PR не разрешает старый attempt 4, очередь из 196 repair задач, embeddings, rebuild или QA.
