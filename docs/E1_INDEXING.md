# E1: индексы полного корпуса (#13)

## Протокол до запуска

Три метода × MuSiQue/HotpotQA, по **5500 пассажей** из закреплённого
`s500-c5500-seed42-v1`. Questions/labels проверяются только по хэшам при
preflight; в модели передаются исключительно title/text корпуса.
Qwen3.8-27B через целевой API, BGE-M3 локально, seed42/temperature0,
thinking=false. Точная серверная ревизия/квантование не сообщены.
Устаревший административный предел90M снят в [ADR-0016](../.adr/0016-target-api-smoke-configuration.md).
Новый пакет имеет собственные непересекающиеся лимиты:

| Метод | Лимит на датасет, все новые токены | Основание оценки |
|---|---:|---|
| Dense | 2000000 | Исторические5500 embeddings заняли78.8s; usage старого кэша неизвестен, строим заново |
| HippoRAG2 | 20000000 | Пять target OpenIE случаев:3319 tokens/7.89s; грубая экстраполяция на11000 стадий ≈7.3M/4.8ч на датасет |
| RAPTOR | 12000000 | Smoke50 leaves/30 summaries; отношение0.6 даёт около3300 summaries/датасет, но масштабирование кластеризации нелинейно |

Сумма потолков **68000000** (LLM input/output и embedding вместе).
Это консервативные ограничения остановки, не заявленный расход.
Ожидаемый порядок машинного времени всего пакета — десятки часов при
последовательных запросах; задержка API и число RAPTOR clusters могут измениться.
Пять OpenIE cases и50 passages не представляют полный корпус, прогноз неточный.
Новые E1 затраты отделены от smoke/failed history: прежний timeout не исчезает
и не превращается в нулевой расход. Человеческие активные часы автоматически
из времени агента не выводятся; фактическое значение должен заполнить исполнитель.
Срок исходной вехи18октября уже прошёл; здесь он не переносится.

## Сохранение и остановка

- Один канонический plan: `<data-root>/indexes/e1/issue13-plan.json`, создаётся
  эксклюзивно и привязан к checkout и clean commit. Другой output/worktree не
  создаёт вторую попытку по этому плану.
- Каждый run получает UUID/новую папку `indexes/e1/<batch>/<method>/<dataset>`.
  Старые индексы не перезаписываются. В Git попадают только безопасные сводки.
- До HTTP резервируются UTF-8 bytes запроса +2048 framing +output cap;
  проверяется остаток лимита. Это верхняя оценка для guard, не server usage.
- requests retry0, redirects запрещены, timeout5/300. Только последовательные
  OpenIE стадии; первая ошибка, неизвестный usage, length или невалидный JSON
  останавливает run. Автоматического повторения failed run нет.
- Private response сохраняется до проверки, физическая попытка — в durable
  журнале. Checkpoint проверяет response SHA и наличие завершённой попытки в
  журнале. Для аварийного продолжения нужны целые журнал, артефакты и checkpoint;
  оставшийся `running.lock` требует проверки процесса, его нельзя стирать вслепую.
- HippoRAG использует официальный pinned SDK и строгий parser, один passage/chunk,
  NER1024/triples3072, пустые корректные списки допустимы. JSON repair не применяется.
  Сохраняются исходные ответы и соответствие source ID → chunk ID.
- RAPTOR: официальный pinned SDK,2 уровня, cluster3000 cl100k tokens,
  reduction5/threshold0.1, summary4096. Leaf embeddings берутся из нового Dense
  того же пакета только после проверки producer journal/SHA/ordered IDs.
  Физическая стоимость leaves включается **один раз** в Dense строку; RAPTOR
  хранит producer run ID/SHA и отдельный счётчик cache hits.
- У каждого индекса проверяются покрытие и save/reload без модельных вызовов.
  Ошибка блокирует E2. E1 не содержит ответов reader и не доказывает качество RAG.

## Команды

Из checkout, содержащего E1 commit; пути ниже заменяются локальными.
Секрет хранится только в игнорируемом env-file.

```powershell
$dataRoot = '<data-root>'
$envFile = '<data-root>/<env-file>'
$plan = "$dataRoot/indexes/e1/issue13-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare --plan $plan --data-root $dataRoot --env-file $envFile
# Сначала обе Dense строки. Перед каждой следующей командой предыдущая должна завершиться.
./.venv-check/Scripts/python.exe -m scripts.run_e1 run --plan $plan --env-file $envFile --method dense --dataset musique
./.venv-check/Scripts/python.exe -m scripts.run_e1 run --plan $plan --env-file $envFile --method dense --dataset hotpotqa
& '<hipporag-venv>/Scripts/python.exe' -m scripts.run_e1 run --plan $plan --env-file $envFile --method hipporag2 --dataset musique --source '<pinned-hipporag-source>'
& '<hipporag-venv>/Scripts/python.exe' -m scripts.run_e1 run --plan $plan --env-file $envFile --method hipporag2 --dataset hotpotqa --source '<pinned-hipporag-source>'
& '<raptor-venv>/Scripts/python.exe' -m scripts.run_e1 run --plan $plan --env-file $envFile --method raptor --dataset musique --source '<pinned-raptor-source>'
& '<raptor-venv>/Scripts/python.exe' -m scripts.run_e1 run --plan $plan --env-file $envFile --method raptor --dataset hotpotqa --source '<pinned-raptor-source>'
./.venv-check/Scripts/python.exe -m scripts.run_e1 report --plan $plan
```

Для RAPTOR установить доступные `TIKTOKEN_CACHE_DIR` (уже загруженный cl100k)
и `NUMBA_CACHE_DIR`, `NUMBA_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`.
Не менять SDK среды на окружение общего offline gate.

Сводки: `results/summary/e1-indexing.json` и `.md`.
JSON содержит run ID, параметры, provenance, index path, per-operation суммы,
физические POST, время, полноту и SHA private manifest со всеми artifact SHA.
Pending/failed не являются готовыми индексами. После ошибки команда не повторяется
до разбора причины и отдельного решения о продолжении с сохранённым расходом.

Offline: `python -m scripts.check`. Дополнительные проверки реальных SDK без HTTP:
`tests/test_e1.py -k real_hipporag` с `E1_HIPPO_SOURCE` в HippoRAG среде;
`-k real_raptor` с `E1_RAPTOR_SOURCE` в RAPTOR среде. Пропуск этих тестов в
общем gate не означает проверку SDK.
