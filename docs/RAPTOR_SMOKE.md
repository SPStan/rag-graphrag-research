# RAPTOR: малый корпус (#12)

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
измерение reader input tokens и пересмотр неизвестного target context contract.

Проверки: обычный `python -m scripts.check`; отдельно opt-in SDK test выше.
Фактический smoke и стоимость будут опубликованы в
`results/summary/raptor-smoke.json`. Активные часы человека не измерялись;
автоматическое время запуска хранится отдельно в manifest.
