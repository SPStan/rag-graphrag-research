# RAPTOR: малый корпус (#12)

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
