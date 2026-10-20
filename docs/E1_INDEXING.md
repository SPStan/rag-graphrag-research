# E1: индексы полного корпуса (#13)

## Продолжение после RemoteDisconnected

20октября первый HippoRAG2 MuSiQue остановлен:1560 полностью проверенных
passages, NER следующего passage сохранён, triple POST получил ConnectionError
(сервер закрыл соединение без ответа). Причина удалённого разрыва не установлена;
предыдущий долгий запрос завершился успешно. Автоматического retry не было.
Failed manifest и6592 артефакта сохранены; journal verified, полная стоимость false.

Проверены **3293 успешных ответа**:172 embedding batch,1561 NER,1560 triples.
В них известны1531342 LLM input/625395 output/684560 embedding tokens.
GET `/models` после остановки вернул200 и целевую модель; генерация в preflight
не выполнялась. Новый протокол: один дочерний run в новой папке, replay только
совпадающего SHA payload при совпадающих corpus/model/digest/seed/options.
Проверяются immutable plan lineage, manifest/artifact SHA, physical attempt,
response usage и checkpoint; оборванный ответ не попадает в кэш.

Резерв неизвестного POST **7922** восстановлен из checkpoint до HTTP.
Из20M вычитаются2841297 известных +7922 reserved; новый лимит **17150781**.
Unknown не превращается в измеренный расход. Суммарные E1 known/attempts/time
включают первый run; cost_complete остаётся false. Проверенная стоимость одного
ответа не означает полную стоимость его producer run: cache hits сохраняют
producer_usage_complete=false, соответствующее ограничение наследуется.

Для новых remote POST задан `Connection: close`, чтобы не использовать старое
keep-alive соединение. Это мера против возможного stale connection, а не
подтверждение причины отказа. Transport retry0/timeout5/300/redirects=false прежние.
При новой ошибке остановка; второй child по тому же prior запрещает claim рядом
с каноническим failed manifest. Исторические файлы/планы не переписываются.

```powershell
$dataRoot = '<data-root>'
$envFile = '<data-root>/<env-file>'
$prior = "$dataRoot/indexes/e1/issue13-continuation-plan.json"
$plan = "$dataRoot/indexes/e1/issue13-network-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 network-resume --prior-plan $prior --plan $plan
& '<hipporag-venv>/Scripts/python.exe' -m scripts.run_e1 run --plan $plan --env-file $envFile --method hipporag2 --dataset musique --source '<pinned-hipporag-source>'
# После успешного завершения — оставшиеся Hippo HotpotQA/RAPTOR строки этого plan.
```

Готовые Dense строки остаются прежними. RAPTOR проверяет producer Dense по всей
цепочке закреплённых планов. Corpus, scientific O/N/R/H и общий потолок68M не меняются.
Техническое продолжение не объявляется новым согласованием куратора.

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

### Разобранный локальный отказ20октября

Первый Dense MuSiQue завершён:5500,172POST,684560 embedding tokens/113.705s.
Первый Dense HotpotQA остановлен на третьем batch: два успешных,9333 известных
embedding tokens, затем HTTP400 из внутреннего `/tokenize` Ollama:
Windows `Only one usage of each socket address ... is normally permitted`.
Это локальный socket allocation failure, не отказ формата корпуса и не target API.
После паузы число TIME_WAIT снизилось; ни сервисы, ни исторические данные не удалялись.

Техническое продолжение внутри исходного #13: pacing0.1s на входной текст
(batch32 не чаще3.2s), одна новая папка/UUID только для этой failed Dense строки.
Первый failed manifest/journal/ответы остаются неизменными. Расход отказа неизвестен:
его UTF-8 request reservation восстанавливается по точному SHA payload и вычитается
из остатка2M вместе с9333 известными токенами. Это резерв бюджета, не измеренный usage.
Полнота суммарной стоимости Hotpot/E1 останется false, даже если новый индекс готов.
Остальные ещё не начатые строки выполняются тем же продолженным планом;
готовый MuSiQue не пересчитывается. Согласие куратора на новый unknown не заявляется;
эта техническая попытка ограничена исходным объёмом/бюджетом #13, где неполнота
расхода допускается только с явным указанием.

```powershell
$dataRoot = '<data-root>'
$envFile = '<data-root>/<env-file>'
$prior = "$dataRoot/indexes/e1/issue13-plan.json"
$plan = "$dataRoot/indexes/e1/issue13-continuation-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 continue --prior-plan $prior --plan $plan
# Далее run --method dense --dataset hotpotqa; остальные pending строки — из этого plan.
```

Claim лежит рядом с каноническим failed manifest и запрещает второе продолжение
между каталогами/worktrees. Повтор команды continue отклоняется до HTTP.
Новая ошибка снова останавливает строку; новых автоматических продолжений нет.

Первый preflight продолжения отклонил строковый parent path до HTTP; исправлена
конвертация в Path. `run_e1 seal --plan $plan` допускает привязку к исправленному
clean commit только до первого нового журнала/lock; прежняя версия plan сохраняется
отдельно с SHA. Это не новая попытка и не сброс spent/claims.

Из checkout, содержащего E1 commit; пути ниже заменяются локальными.
Секрет хранится только в игнорируемом env-file.
Следующий блок показывает исходное создание пакета. Если canonical plan уже
существует, prepare не повторять; для текущего продолжения использовать plan выше
и пропустить готовый Dense MuSiQue.

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
./.venv-check/Scripts/python.exe -m scripts.run_e1 verify --plan $plan
```

Для RAPTOR установить доступные `TIKTOKEN_CACHE_DIR` (уже загруженный cl100k)
и `NUMBA_CACHE_DIR`, `NUMBA_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`.
Не менять SDK среды на окружение общего offline gate.

Сводки: `results/summary/e1-indexing.json` и `.md`.
JSON содержит run ID, параметры, provenance, index path, per-operation суммы,
физические POST, время, полноту и SHA private manifest со всеми artifact SHA.
Для продолжения таблица показывает cumulative_seconds обоих run; новые физические
затраты и полная цепочка сохраняются отдельно в JSON.
Pending/failed не являются готовыми индексами. После ошибки команда не повторяется
до разбора причины и отдельного решения о продолжении с сохранённым расходом.

Offline: `python -m scripts.check`. Дополнительные проверки реальных SDK без HTTP:
`tests/test_e1.py -k real_hipporag` с `E1_HIPPO_SOURCE` в HippoRAG среде;
`-k real_raptor` с `E1_RAPTOR_SOURCE` в RAPTOR среде. Пропуск этих тестов в
общем gate не означает проверку SDK.
