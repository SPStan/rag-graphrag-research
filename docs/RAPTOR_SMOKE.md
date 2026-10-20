# RAPTOR: малый корпус (#12)

**20 октября: исправление cap по поручению пользователя «Сделай все что нужно».**
Один remediation: summary cap4096, reader512; прежние50 passages/2levels/3QA.
Offline21 first-layer clusters требуют guard больше20: выбран100summary/200POST.
Общий бюджет continuation+remediation100000, остаток82544. 61 embedding/11 stop
summary сверены по SHA и complete producer journal; partial/length исключён.
Cache hit сохраняет producer/SHA, историческая стоимость не дублируется.
Одна новая canonical-prior claim, retry0, timeout5/300; старые claims не удалять.
Команда continuation дополнена --repair-from
results/raw/raptor-smoke/3a48630b-72fe-46a9-99eb-309035ed1a0c/manifest.json.
Новый HTTP только после offline-проверок; при ошибке/unknown/length остановка.
O/N/R/H прежние; полный корпус не разрешён. До реального результата PR Draft.

## Результат продолжения 20 октября: остановка на truncated summary

Run `3a48630b-72fe-46a9-99eb-309035ed1a0c`, чистый код `00f3e8a`,
[сводка](../results/summary/raptor-continuation.json): 50 leaf embeddings,
11 summary `nonempty/stop` и их embeddings; двенадцатый summary вернул
`finish_reason=length`, 897 input / 512 output. Строгий guard остановил run;
partial summary не принят, повторов не было. Причина этой остановки известна:
output cap512 недостаточен для данного ответа. Это не повтор прежнего timeout
и не объяснение его исхода.

Новый run: **73 POST** (61 local embedding + 12 target), **9739 embedding +
3983 LLM input + 3734 LLM output = 17456 известных combined tokens**.
Журнал проверен, новый расход полный, бюджет100000 не исчерпан. Общий учёт
трёх runs: **125 attempts**, известные subtotal embedding16138 / LLM4333+4109;
общий total=null, complete=false из-за первого timeout. Известный subtotal24580
не является полным расходом исследования. Все исторические manifest/journal SHA
повторно проверены и не изменились.

Реального завершённого дерева, save/reload и трёх reader-ответов пока нет (0/3).
Upstream строит уровень до возврата из construct_tree; промежуточные summary
сохранены в private request/response, но не объявляются готовым tree/checkpoint.
Не удалять continuation claim, не запускать заново команду выше. Следующий
технический шаг — определить отдельную ограниченную политику для truncated
summary (cap/бюджет/переиспользование проверенных результатов), сначала offline.
Увеличение cap не выполнялось, дополнительных model calls после остановки нет.
Согласие на historical unknown получено; прежний блокер согласования не выдаётся
за нерешённый. Текущий блокер — output cap и незавершённый smoke. PR Draft/Refs #12.

## Согласованное продолжение, 20 октября

Пользователь передал ответ преподавателя на вопрос о продолжении при unknown
historical usage: «Ну, я точно не против». Источник — сообщение пользователя
в этом чате 20.10.2026; внешняя ссылка не предоставлена. Это принятие данного
отклонения для ограниченного #12, не разрешение на full corpus или новые retry.

Один свежий запуск на прежних 50 passages / 3 вопросах. Верхние guards сохранены:
100000 **новых** combined tokens, 100 POST, 20 summary, cap512, input16000 bytes.
Timeout 5/300 s, retry=0, redirects off; новая ошибка/unknown usage останавливают
запуск. Исторический timeout не объяснён и не исправляется задним числом.
Все старые 51 + 1 диагностическая попытка входят в aggregate; complete=false,
total=null. Новый run имеет отдельный бюджет и journal. Старые embeddings и
summary не переиспользуются: это свежая сборка, её стоимость учитывается заново.
Исходные manifests/journals сверяются с опубликованными SHA; data/model/embedding
digest проверяются до расходов. Exclusive/fsynced claim рядом с каноническим
prior запрещает второй continuation независимо от output/worktree и остаётся
при аварии. Старые raw/claims/summary не меняются.

```powershell
.cache/raptor-venv/Scripts/python.exe -m scripts.run_raptor_smoke --data-root '<data-root>' --env-file '<data-root>/<env-file>' --source .cache/raptor-source --continuation-prior 'results/raw/raptor-smoke/bb0b97d2-b0ca-4d09-926c-76d2309b0853/manifest.json' --continuation-diagnostic 'results/raw/raptor-summary-diagnostic/3525d53a-8a93-4e17-a784-6337feb520a7/manifest.json' --execute
```

Путь continuation — абсолютный или относительно текущей worktree. Это новая
однократная команда с HTTP, не воспроизведение без расхода. Прежние запреты ниже
описывают состояние до переданного согласия; O1/N1/R1/H1 не меняются. До фактического
завершения дерева/reload/reader PR остаётся Draft, #12 открыта.

## Один повторный summary по разрешению пользователя, 14 октября

Пользователь явно попросил попробовать отправить запрос ещё раз, не ожидая
восстановления прежнего usage. Выполнена **одна** отдельная диагностика с тем
же payload/SHA, model/seed/temperature и output cap 512; изменён read timeout
на 300 s (connect 5 s), transport retry=0, redirects off. Отдельный предел новых
tokens 5000 и максимум один POST. Exclusive/fsynced claim рядом с каноническим
prior manifest блокирует повторное выполнение диагностики; дерево/reader и
embedding не запускались. Это разрешение пользователя, не согласие куратора.

Run `3525d53a-8a93-4e17-a784-6337feb520a7` на tracked HEAD `af954b7`:
**completed**, nonempty summary, finish_reason=stop, **350 input + 375 output =
725 target tokens**, reasoning 0. Server input совпал с локальными 350.
[Безопасная сводка](../results/summary/raptor-summary-diagnostic.json) содержит
ссылку на prior, manifest/request/response/script/journal SHA и оба учёта.
Private raw и замороженный operator.py:
`results/raw/raptor-summary-diagnostic/3525d53a-8a93-4e17-a784-6337feb520a7/`.
Операторский скрипт использует существующие Journal/recorded_call и был
выполнен из локальной `.cache`, его SHA фиксируется отдельно от tracked HEAD.

Всего #12: 50 локальных embedding POST и 2 remote summary POST. Из remote
один завершён с 725 tokens, исход прежнего запроса по-прежнему неизвестен.
Совместный journal summary: **52 attempts**, known embedding subtotal 6399,
known LLM input/output 350/375, **complete=false, aggregate_total=null**.
Исходные raw/manifest не переписаны; прежний unknown не стал нулём.
Один успешный ответ спустя время не устанавливает причину предыдущего timeout.
Tree/save/reload и три reader-вопроса всё ещё не выполнены; дальнейших расходов
эта диагностика не разрешает. PR остаётся Draft/Refs #12, научное согласование
и принятие отклонения отдельно.

### Опубликованный operator.py и команда диагностики

По ревью `41b64eee` доступна [обезличенная копия operator.py](operators/operator.py).
Это исторический одноразовый оператор, не библиотечный модуль: код выполняется
при запуске/импорте. От выполненного private operator отличаются **только**:

1. Личный абсолютный путь `.env` заменён на `TARGET_API_ENV_FILE`.
2. `ROOT.parents[1]` заменён на `ROOT.parents[2]` из-за расположения в `docs/operators`.

Остальные инструкции совпадают, включая claim до HTTP, отсутствие циклов,
один `session.post`, timeout 5/300, retry=0, redirects off, reservation <=5000,
cap512, durable journal и сохранение prior unknown в aggregate. Исторический
SHA в исходных raw/summary остаётся прежним; публичная версия не объявляется
побитовым оригиналом:

```text
historical operator.py SHA256 23d4d21262f0e9cf8fa9135f0dd22e3810be55f303b1a2beaeca01150ae4a299
published operator.py SHA256  86b9712bc79794db53e4de0ce75e0a68d8f3f6d6563afca0c9b4adb94db4028e
```

Команда для обезличенной версии (требует исходные private prior/raw и settings;
ключ в команду не вставляется):

```powershell
$env:TARGET_API_ENV_FILE = '<data-root>/<env-file>'
.venv-check/Scripts/python.exe docs/operators/operator.py
```

Это команда **отправки** исторической диагностики, не разрешение повторять её.
В нашей worktree claim уже израсходован: повтор завершается `FileExistsError`
до HTTP. Не удалять claim и при переносе prior переносить его вместе с файлами;
это локальная защита, не серверная идемпотентность. В другой worktree без private
prior команда также не может выполнить запрос. Для проверки кода без API:

```powershell
.venv-check/Scripts/python.exe -m pytest tests/test_raptor_summary_operator.py -q
```

Тесты исполняют именно опубликованный файл с fake HTTP и отдельным временным
prior: один POST и отказ повтора, timeout/missing usage с неполным итогом,
SHA/budget guards до HTTP, отказ retry adapter. Исходные raw/claim не затрагиваются.
Реальное дерево/три reader-вопроса не выполнены. Продолжение при неизвестном
historical usage и актуальные O1/N1/R1/H1 должны быть согласованы отдельно;
решение куратора не подменяется просьбой пользователя о разовом resend.

## Уточнение контракта 14 октября

Пользователь сообщил: общий context 262144 токена, output до остатка окна,
native HF `Qwen/Qwen3.8-27B` tokenizer/chat template, vLLM 0.29.0. Отдельного
server count endpoint нет, prompt usage доступен только после ответа.
Лимиты теперь известны со слов пользователя; значения unknown в исходных
manifest/summary описывают момент failed run и не исправляются задним числом.
Это не ответ об исходе того запроса: unknown remote usage остаётся unknown,
причина ReadTimeout не установлена. Новых модельных вызовов в этой проверке нет.

HF tokenizer/template для локального подсчёта закреплён в отдельном SDK-worktree
на `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`. Точный HF commit deployment
отдельно не сообщён; native local count не подменяет server usage. Большое
окно само по себе не исключает timeout ожидания/выполнения запроса.

Сохранённый первый summary request проверен этим tokenizer с его исходными
`chat_template_kwargs`: local input 350, output cap 512, сумма 862 токена.
SHA запроса `bb342926b8cd94a0ecc08326577c17d7da35dd3d204143897d6307b48d08663e`
совпал с опубликованной сводкой. По переданному контракту prompt помещается;
это не измерение расхода фактически выполненного/отменённого сервером запроса.

Официальная реализация, отклонения и лимиты — [ADR-0020](../.adr/0020-raptor-small-corpus-adapter.md).
Адаптер: `scripts/run_raptor_smoke.py`. Данные и `.env` хранятся локально.
Команды ниже запускаются из отдельной тематической worktree.

```powershell
git clone https://github.com/parthsarthi03/raptor .cache/raptor-source
git -C .cache/raptor-source checkout 7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767
uv venv --python 3.12 .cache/raptor-venv
uv pip install --python .cache/raptor-venv/Scripts/python.exe -r requirements-raptor-smoke.txt
uv pip check --python .cache/raptor-venv/Scripts/python.exe
$env:TIKTOKEN_CACHE_DIR = "$PWD/.cache/tiktoken"
$env:RAPTOR_SOURCE = "$PWD/.cache/raptor-source"
$env:NUMBA_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
.cache/raptor-venv/Scripts/python.exe -m pytest tests/test_raptor_smoke.py -q
```

Для pytest на Windows при конфликте прав старого temp-каталога назначить
`TEMP`/`TMP` на доступный новый локальный каталог. Для реального запуска
Ollama должен отвечать на `/api/tags`, BGE-M3 иметь digest. API settings:
`TARGET_API_BASE_URL`, `TARGET_API_MODEL`, `LITELLM_API_KEY`,
`OLLAMA_EMBED_MODEL`; секреты не входят в Git. Сначала только план:

```powershell
.cache/raptor-venv/Scripts/python.exe -m scripts.run_raptor_smoke --data-root '<data-root>' --env-file '<data-root>/<env-file>' --source .cache/raptor-source
# Тот же вызов с --execute отправляет passages/questions целевому API.
.cache/raptor-venv/Scripts/python.exe -m scripts.run_raptor_smoke --data-root '<data-root>' --env-file '<data-root>/<env-file>' --source .cache/raptor-source --execute
```

Raw: `results/raw/raptor-smoke/<run-id>/`: immutable уникальный каталог запуска,
manifest, durable token journal, все запросы/ответы, tree.json, ответы с node/leaf
provenance. При ошибке сохраняется failed manifest; автоматически повторять
расходующий запуск нельзя. Валидация response происходит после записи raw/usage.
Reader получает только тексты узлов и вопрос, не ответы и supporting labels.
Reload JSON в том же запуске не вызывает индексацию. Можно отдельно прочитать
сохранённый tree без callback/Builder:

```python
from pathlib import Path
from scripts.run_raptor_smoke import load_source, restore_tree
from scripts.run_dense import read_json
sdk = load_source(Path('.cache/raptor-source'))
tree = restore_tree(read_json(Path('<run-dir>/tree.json')), sdk)
```

Top-5 — узлы разных уровней; длина и тип записаны для каждого. Provenance coverage
считает исходные passages в ancestry, не сохранение фактов в summary. EM/F1
считаются общими функциями после генерации. Три вопроса и support-preserving
корпус не устанавливают эффективность; full corpus/holdout не запускаются.
Для будущей задачи 7 нужны отдельный протокол, одинаковые data/reader/model,
измерение reader input tokens и сверка фактических параметров deployment с
контрактом, переданным 14 октября. Отдельно остаются исход timeout и неизвестный
server usage неудачного summary; локальный fit не закрывает эти вопросы.

Проверки: обычный `python -m scripts.check`; отдельно opt-in SDK test выше.
Общий gate: 235 passed / 14 skipped; изолированный SDK: 11 passed. Полный offline
adapter flow строит официальный synthetic tree, reload и три shared-reader
вызова на подставном HTTP. Только этот synthetic fixture расширяет summary/request
guards до 100/300: его soft clustering создаёт больше 20 узлов. Production guards
20/100 отдельно проверяются до отправки; реальный бюджет не увеличен.
Фактический run `bb0b97d2-b0ca-4d09-926c-76d2309b0853` на `2b699a2`:
50 leaf embeddings, 6399 локальных tokens; первый summary ReadTimeout через
120 s без ответа/usage. Реальное дерево/reload/reader не завершены, расход
удалённого запроса неизвестен. [Сводка](../results/summary/raptor-smoke.json)
содержит SHA manifest/journal/request и явно неполный итог. PR #31 остаётся Draft,
issue #12 открыта. Нельзя заменить неудачный запуск новым и считать затраты нулём.
Следующий протокол должен сохранить эту попытку в общем учёте, определить
бюджет при неизвестном usage и разрешить причину timeout. Увеличение timeout
само по себе не восстанавливает потерянный usage и не доказывает совместимость.
Активные часы человека не измерялись; автоматическое время хранится отдельно.

Gitleaks для исторического `496e87a` ошибочно распознал опубликованный SHA256
журнала под ключом tokens.jsonl как ключ API. Значение проверено против
фактического журнала и journal_sha256. Удалена только дублирующая запись
artifacts; сохранён journal_sha256. Исключён один точный fingerprint этой
исторической находки; полный scan истории и остальные правила сохранены.
