# Issue #11 — ограниченная проверка проблемных OpenIE случаев

## Обновление 14 октября: контракт и локальный подсчёт

Пользователь передал параметры deployment: context **262144** токена суммарно
на вход и ответ, отдельного output cap нет (context минус input), backend
**vLLM 0.29.0**. Tokenizer и chat template — родные `Qwen/Qwen3.8-27B` из HF;
серверного count endpoint нет, только `usage.prompt_tokens` после генерации.
Это переданный пользователем контракт, не значения из metadata GET.

Родные tokenizer/template загружены без весов из
[HF revision 1d4bf0f](https://huggingface.co/Qwen/Qwen3.8-27B/tree/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0).
Локально использован Qwen2TokenizerFast / transformers 4.45.2, явно выбран
`chat_template.jinja`, `add_generation_prompt=true`, `enable_thinking=false`.
`apply_chat_template(tokenize=true)` совпал с encode от полного rendered prompt
при `add_special_tokens=false`. Сами messages взяты из исходного snapshot;
его SHA `7a911365e515e9ce270a878684b9afc3de6ad2a6dd93b79f677a830cb52a0e29`
совпал с исходным preflight. QA answers/support labels не читались.

| Stage / passage SHA prefix | Native input tokens | Output cap | Input + cap | Fit 262144 |
|---|---:|---:|---:|---|
| NER / af7c103c3e75 | 489 | 1024 | 1513 | да |
| NER / 80c59521880e | 383 | 1024 | 1407 | да |
| triples / f520187048cf | 664 | 3072 | 3736 | да |
| triples / bf2985f3129a | 721 | 3072 | 3793 | да |
| NER / 225264f9bf8f | 278 | 1024 | 1302 | да |

SHA256 файлов закреплённого tokenizer snapshot:

```text
tokenizer.json        0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3
tokenizer_config.json b11349aafa7cdc6a320767cf7ceb29ed82f7eda5d65e8e0819e76f0ce947bf27
chat_template.jinja   c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041
```

Локальные файлы — `.cache/qwen38-tokenizer/<revision>/`; диагностические
rendered SHA и counts — `.cache/qwen38-context-fit.json` в SDK-worktree.
Это локальная проверка по указанному контракту, не подтверждённые сервером
counts: точный HF commit deployment отдельно не сообщён. При первом разрешённом
OpenIE запросе нужно сопоставить `usage.prompt_tokens` с локальным счётом
того же messages/options; несовпадение не скрывать и не выдавать за exact fit.

Новых модельных попыток **0**. Исторический blocked preflight от 13 октября
не перезаписан. Его таблица ниже описывает состояние до этого ответа пользователя.
Генерация/качество OpenIE и готовность индекса по-прежнему не проверены,
`ready_for_indexing=false`; научное согласование отдельно. Лимиты не объясняют
ReadTimeout RAPTOR #12 и не восстанавливают расход его failed запроса.

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

## Ответ на предварительное ревью PR #30 (13 октября)

Ревью `0038c096` не содержит нового подтверждённого дефекта кода: оно требует
завершить реальную проверку и научное согласование. Дополнительно проверены
read-only GET `/openapi.json`, `/v1/openapi.json` и `/docs` на целевом API:
все HTTP 404. Документированный token-count endpoint этим способом не найден;
это не доказывает, что у провайдера такого endpoint нет. Модельные запросы
не отправлялись, исходный preflight и исторические артефакты не перезаписаны.

Для снятия блокера нужен ответ провайдера для **этого deployment**, а не лимиты
похожей модели из литературы:

> Для `iairlab/qwen3.8-27b` подтвердите context window и предел output/input;
> укажите backend revision, tokenizer revision и chat template либо документированный
> серверный счётчик токенов полного messages payload (с chat wrapper/special tokens).
> Нужно проверить пять сохранённых OpenIE prompts с output caps 1024 для NER
> и 3072 для triples. Caps пока предлагаемые; нужен подтверждённый fit.

Точные серверные input counts заменяют локальный tokenizer, но сами по себе
не заменяют context/output limits. Gate: input + запрошенный output укладываются
в подтверждённый context, output — в разрешённый максимум; model/revision и
messages SHA связывают проверку с теми же запросами. Только затем отдельный
бюджет и максимум две коррекции каждой причины, с полным журналом; таблица
до/после обновляется по реальным ответам, `ready_for_indexing=false` сохраняется
до прохождения всех проверок. Ни fit, ни согласие куратора нельзя вывести из
одного успешного Dense ответа.

По сообщению бота карточка уже зарегистрирована: `eb27b8fa5654329712648d28:0`.
H1/N1/O1/R1 пока **не утверждены**. Проверка актуального решения:

```text
/research_status https://github.com/SPStan/rag-graphrag-research/pull/30
```

Команды research-status/submit недоступны в текущем наборе инструментов;
GitHub комментарий или самостоятельное «ДА» агента не заменяют решение
назначенного куратора. PR сохраняется Draft/Refs #11, issue открыта до реальных
критериев и актуального согласования; затем Ready for review для полного ревью.
