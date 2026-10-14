# Issue #11 — ограниченная проверка проблемных OpenIE случаев

## Фактический target-run 14 октября

Run **b1549680-6917-47e4-a614-3540fcda01a6**, чистый код **2e46d0a**:
пять POST, все `finish_reason=stop` / `valid_nonempty` через pinned parser,
без partial recovery, retry и коррекций. Для каждого запроса серверный
`usage.prompt_tokens` **точно совпал** с закреплённым native count.
[Безопасные результаты и SHA](../results/summary/openie-target-live-check.json).
Локальный исходный counts artifact ниже сохраняется как pre-server snapshot;
фактическая серверная сверка записана в новом live result, не задним числом.

| Stage / passage SHA prefix | До | После | Input: native = server | Output tokens | Values |
|---|---|---|---:|---:|---:|
| NER / af7c103c3e75 | truncated, cap 512 | valid_nonempty, cap 1024 | 489 | 134 | 12 |
| NER / 80c59521880e | truncated, cap 512 | valid_nonempty, cap 1024 | 383 | 165 | 20 |
| triples / f520187048cf | truncated, cap 2048 | valid_nonempty, cap 3072 | 664 | 179 | 6 |
| triples / bf2985f3129a | truncated, cap 2048 | valid_nonempty, cap 3072 | 721 | 194 | 10 |
| NER / 225264f9bf8f | request_error, usage unknown | valid_nonempty, cap 1024 | 278 | 112 | 10 |

Расход **этого run**: **2535 input + 784 output = 3319 target tokens**,
в пределах бюджета 20000; reasoning tokens по всем пяти ответам 0.
Журнал целостен/полон, пяти физическим POST соответствуют пять пар start/finish.
Raw request/response, manifest и token journal:
`results/raw/openie-target-live-b1549680-6917-47e4-a614-3540fcda01a6/`
в SDK-worktree. В сводке — request/response/rendered SHA, response/client IDs,
commit, параметры и journal/manifest SHA. Активные часы человека не измерялись,
автоматический request span записан отдельно.

Все 61 Python-файл установленного SDK сверены с `1438aba3`, исходные
manifest/corpus/state/cache SHA до/после совпали. Старый индекс не исправлялся:
**ready_for_indexing=false**. Это приёмка формата/завершения пяти development
stage-prompts, не оценка точности извлечения или эффективности HippoRAG.
Изменились и модель, и stage caps: нельзя приписать улучшение одной причине.
Исторический request_error остаётся с неизвестным usage; complete=true относится
только к пяти новым POST. Расход failed RAPTOR #12 не изменился и не восстановлен.
Глобальная идентичность tokenizer/backend revision не доказана совпадением
пяти input counts; точный HF commit deployment отдельно не сообщён.
Научное согласование и полное техническое ревью отдельно; PR остаётся Draft.

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

Локальные tokenizer файлы — `.cache/qwen38-tokenizer/<revision>/`.
Проверяемые counts и rendered SHA опубликованы в
[openie-target-context-counts.json](../results/summary/openie-target-context-counts.json):
пять passage ID/stage, input/output reserve, SHA полного rendered prompt,
SHA исходного case snapshot, HF revision и SHA tokenizer/template. Текстов,
ответов и credentials в артефакте нет. Команда воспроизведения — ниже.
Это локальная проверка по указанному контракту, не подтверждённые сервером
counts: точный HF commit deployment отдельно не сообщён. При первом разрешённом
OpenIE запросе нужно сопоставить `usage.prompt_tokens` с локальным счётом
того же messages/options; несовпадение не скрывать и не выдавать за exact fit.

Новых модельных попыток **0**. Исторический blocked preflight от 13 октября
не перезаписан. Его таблица ниже описывает состояние до этого ответа пользователя.
Генерация/качество OpenIE и готовность индекса по-прежнему не проверены,
`ready_for_indexing=false`; научное согласование отдельно. Лимиты не объясняют
ReadTimeout RAPTOR #12 и не восстанавливают расход его failed запроса.

### Воспроизведение native counts и rendered SHA

Запускать из корня worktree в изолированном SDK env. Фактически проверены
`transformers==4.45.2`, `tokenizers==0.20.3`; эти версии команда проверяет явно.
Используется только tokenizer, веса не нужны. В `<private-case-snapshot.json>`
указать исходный `results/raw/openie-target-70d727d7-00ff-414e-aeb8-f61e49d7800f.cases.json`
либо его побитовую копию. Snapshot не публикуется; его можно получить локальным
preflight из раздела «Воспроизведение» при наличии исторических данных/SDK.
Один только безопасный JSON не содержит исходных messages и не позволяет
воссоздать их из SHA; отсутствие raw не считать успешной репродукцией.

Команда проверяет input SHA и порядок cases, скачивает **только три tokenizer
файла** с закреплённого публичного HF revision, если их нет в локальном cache,
и проверяет их SHA. При заполненном cache работает без сети. Целевой API не
используется; `.env`/API-ключ не нужны. Сравниваются **все** counts и rendered
SHA с опубликованным артефактом, который команда не перезаписывает.

```powershell
$env:OPENIE_CASE_SNAPSHOT = '<private-case-snapshot.json>'
$countCode = @'
import hashlib
import json
import os
from pathlib import Path
import requests
import tokenizers
import transformers
from transformers import AutoTokenizer

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

report = json.loads(Path('results/summary/openie-target-context-counts.json').read_text(encoding='utf-8'))
require(transformers.__version__ == report['runtime_transformers'], 'transformers version mismatch')
require(tokenizers.__version__ == report['runtime_tokenizers'], 'tokenizers version mismatch')
source = Path(os.environ['OPENIE_CASE_SNAPSHOT']).read_bytes()
require(sha(source) == report['source_snapshot_sha256'], 'case snapshot SHA mismatch')
cases = json.loads(source)
require(len(cases) == len(report['cases']) == 5, 'expected five cases')
directory = Path('.cache/qwen38-tokenizer') / report['hf_revision']
directory.mkdir(parents=True, exist_ok=True)
for name, expected_sha in report['files'].items():
    path = directory / name
    if not path.exists():
        url = f"https://huggingface.co/{report['hf_model']}/resolve/{report['hf_revision']}/{name}"
        response = requests.get(url, timeout=(5, 60))
        response.raise_for_status()
        require(sha(response.content) == expected_sha, 'download SHA mismatch')
        path.write_bytes(response.content)
    require(sha(path.read_bytes()) == expected_sha, 'tokenizer file SHA mismatch')
tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)
require(type(tokenizer).__name__ == report['tokenizer_class'], 'tokenizer class mismatch')
tokenizer.chat_template = (directory / 'chat_template.jinja').read_text(encoding='utf-8')
caps = {'openie_ner': 1024, 'openie_triples': 3072}
actual = []
for case, expected in zip(cases, report['cases']):
    source_case = case['source_attempt']
    require((source_case['stage'], source_case['passage_id']) ==
            (expected['stage'], expected['passage_id']), 'case identity/order mismatch')
    ids = tokenizer.apply_chat_template(case['messages'], tokenize=True, **report['options'])
    rendered = tokenizer.apply_chat_template(case['messages'], tokenize=False, **report['options'])
    require(ids == tokenizer.encode(rendered, add_special_tokens=False), 'render/tokenize mismatch')
    cap = caps[source_case['stage']]
    actual.append({
        'stage': source_case['stage'], 'passage_id': source_case['passage_id'],
        'input_tokens': len(ids), 'output_cap': cap, 'total_reserved': len(ids) + cap,
        'fits_262144': len(ids) + cap <= report['context_window'],
        'rendered_sha256': sha(rendered.encode('utf-8')),
    })
require(actual == report['cases'], 'counts/rendered SHA differ from published artifact')
print('Verified 5 native counts and rendered SHA; server_usage_verified=false; ready_for_indexing=false')
'@
$countCode | .cache/hipporag-sdk-venv/Scripts/python.exe -
if ($LASTEXITCODE -ne 0) { throw 'Native token count verification failed' }
```

Это воспроизведение локального подсчёта, не серверная сверка или реальная
проверка OpenIE. В безопасном артефакте `server_usage_verified=false`,
`new_model_attempts=0`, `ready_for_indexing=false`.

Gitleaks `generic-api-key` ошибочно классифицировал два публичных SHA256 в
полях `tokenizer.json` / `tokenizer_config.json`. Их происхождение и значения
приведены выше. `.gitleaksignore` содержит только два fingerprint коммита
`d2ae33e` с этим файлом/правилом/строками; правила и полный history scan не
отключены, другие коммиты и значения не исключаются.

## Историческая граница preflight и отдельный live-протокол

### Отдельный ограниченный target-протокол 14 октября

Режим `--target-openie-check` явно отправляет до пяти выбранных messages;
`--target-api-check` остаётся metadata-only. Один запрос на случай, максимум
пять HTTP POST и **20000** input+output tokens на этот run; planned native
input+caps **11751**. Temperature 0, seed 42, thinking disabled, JSON-object,
output caps 1024 NER / 3072 triples. Retry=0, redirects запрещены, connect/read
timeout 5/120 s. Никаких автоматических исправлений; это меньше допустимых
двух исправлений причины. Это новые OpenIE cases, не повтор failed RAPTOR.

До отправки проверяются SHA snapshot и всех tokenizer файлов, identity/order
cases, native count/rendered SHA, установленный pinned SDK и исходные
manifest/corpus/state/cache SHA. После ответа usage записывается до проверки
структуры; prompt_tokens должны совпасть с native count. Первый mismatch,
неизвестный usage, request error или невалидный/truncated результат останавливает
весь run. Parser — существующий `make_pinned_openie_parser`, partial recovery
отключён. Фазы/операции и все попытки записаны в durable Journal. Для диагностики
отправляется и сохраняется X-Client-Request-Id без credentials.

```powershell
.cache/hipporag-sdk-venv/Scripts/python.exe -m scripts.preflight_hipporag_repair_prompts --target-openie-check --data-root '<data-root>' --manifest '<source-manifest>' --env-file '<env-file>' --case-snapshot '<private-case-snapshot.json>' --sdk-source '<sdk-source>'
```

Claim создаётся через exclusive create/fsync в общем
`<data-root>/results/raw/openie-target-claims/<snapshot-sha>.claim.json`, а не
в output/worktree. Повтор того же snapshot блокируется и после ошибки; не
удалять claim для обхода бюджета. Любое дальнейшее продолжение требует отдельного
протокола с сохранением всех предыдущих попыток/неизвестных затрат.
Raw нового run — `results/raw/openie-target-live-<uuid>/`: manifest, request/
response JSON и token journal. Исторические SQLite/индексы не пишутся; source
SHA проверяются до/после. Даже успешные пять cases не чинят весь старый индекс:
`ready_for_indexing=false` сохраняется. Реальные результаты фиксируются после
запуска, не подменяются offline-тестами. Общий gate до запуска: 243 passed /
13 skipped; targeted offline tests preflight/execution: 21 passed.

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
