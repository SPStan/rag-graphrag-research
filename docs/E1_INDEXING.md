# E1: индексы полного корпуса (#13)

## Подготовка продолжения RAPTOR после batch-пробы

Следующий план включает только RAPTOR MuSiQue continuation и untouched HotpotQA.
Физические cache responses проверяются отдельно от Dense leaf vectors; source
journal/manifest/artifact SHA, ordered IDs, payload SHA и reported usage обязательны.
Удачный embedding diagnostic переиспользуется, неизвестный расход failed POST
не удаляется. История двух run включается ровно один раз, E1 cost_complete=false.
Условие запуска нового полного этапа — отдельное согласование новых расходов.

```powershell
$dataRoot = '<data-root>'
$prior = "$dataRoot/indexes/e1/issue13-raptor-plan.json"
$plan = "$dataRoot/indexes/e1/issue13-raptor-batch-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 raptor-batch-resume --prior-plan $prior --plan $plan
# Только после согласования: run raptor/musique, затем raptor/hotpotqa.
```

Бюджеты новых POST: MuSiQue10970532, HotpotQA12000000 combined tokens
(LLM input/output + local embedding), максимум22970532. Target Qwen/локальный
BGE-M3 и5500 passages прежние. Для новых RAPTOR embedding options4096/4096,
truncate=false; старый verified payload/cost не заменяются новым SHA.
Один canonical claim при failed MuSiQue, свежий UUID и `musique-batch1` output;
HotpotQA папка должна быть нетронутой. Родительский plan/worktree/data pin проверяются
до claim. Нельзя выполнить plan в другой рабочей копии либо с активным index worker.
Успех подготовки не означает построенного дерева; E2/QA и Hippo остаются запрещены.

## Актуальный разбор21октября: schema-проба и physical batch

После отдельного явного разрешения на передачу двух passages/NER выполнен
**один** schema POST. Сервер HTTP400: grammar backend не реализует uniqueItems.
Второй POST не выполнялся, retry/fallback нет. Usage отсутствует: известный subtotal
диагностики0 не означает нулевого расхода; unknown reserve8679 сохранён.
Claim/failed manifest/raw/journal immutable, full_index_authorized=false.
Снятие uniqueItems или новая попытка потребуют нового плана и согласования.

RAPTOR embedding input восстановлен из producer summary по двум точным SHA:
request `f6deb464ae50c4fb94690686d8e7b734ff8713d65e7dfa96690535ad7b395f1f`,
producer response `1fdcb7aedc1d9b54d60f2ef99024f8e941664de6ffaf53e3d461d101a9823803`.
Native GGUF tokenizer:2104 с special tokens (2102 без). Проверка совпала с тремя
сохранёнными usage524/693/548; /embedding не вызывался при tokenization.
Ошибка runner: physical batch2048, input2104 при context4096; model context8192.
Подробности и pinned source — ADR-0022. Это batch-ограничение, не доказательство
слишком длинного для BGE-M3 summary. Char/cl100k оценки не использованы.

Подготовлена минимальная настройка только RAPTOR: явные num_ctx4096/num_batch4096,
truncate=false. Старые verified payload проверяются первыми, replay сохраняет
исходный SHA и историческую неполноту; новые options применяются только к uncached
embedding. Для Dense/Hippo изменение запрещено. Реальный input сверх этого окна
не обрезается: остановка и разбор, переход к8192 не автоматический.
Один localhost embedding POST на сохранённом summary отдельно согласован;
полный RAPTOR по этому согласию не запускать. Проба выполнена на clean eb6b271:
ровно1 POST, usage2104, embedding shape1×1024, сохранение/reload без новых calls.
Настройки подтверждены runtime n_batch4096/n_ubatch4096/n_ctx_slot4096.
Manifest SHA: `1997f8e6ddb5c044d64882b2fb8c9ea1a1fda097f2c8110b36e795b8bfac0385`.
Это исправление конкретного input, не готовность полного дерева.

Текущий physical known E1 **6405867**, cost_complete=false. Верхний бюджетный
charge **6452489** включает прежние reserves27521, RAPTOR10422 и schema8679.
Ни один reserve не назван измеренным расходом. RAPTOR MuSiQue для будущего
продолжения:12M−1016942 known−10422 unknown reserve−2104 diagnostic=**10970532**.
Начатый failed run остаётся terminal; повтор всей команды запрещён.

### Воспроизведение родного подсчёта без embeddings

Проверить GGUF SHA из ADR. Запустить поставляемый с Ollama `llama-server.exe`
на отдельном loopback-порту: `--embedding --no-warmup --gpu-layers 0
--ctx-size 8192 --parallel 1 --host 127.0.0.1 --port 11993 --model <bge-blob>`.
Это tokenizer-проверка; не вызывать /embedding, /embeddings или /completion.

```powershell
$raw = Get-Content '<raptor-run>/requests/aa23318465e56bcdf8d5331a4a4a0f724187c597ecda53645eaa0efb0cfff16d.response.json' -Raw | ConvertFrom-Json
$body = @{content=$raw.choices[0].message.content; add_special=$true; parse_special=$false} | ConvertTo-Json -Depth 5
$tokens = Invoke-RestMethod -Uri 'http://127.0.0.1:11993/tokenize' -Method Post -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body))
$tokens.tokens.Count # 2104; add_special=false даёт2102
```

Выполненная embedding-проба использовала тот же source SHA и существующий
Transport.embed с row.embedding_options, один canonical claim при failed prior.
Operator и его SHA сохранены локально; экспорт включает options, token counts,
producer response SHA и operator SHA. Все raw/journals старого run неизменны.
Новый полный RAPTOR/QA не запускался.

Экспорт включает unknown reserve текущего failed RAPTOR10422, историю и
диагностику отдельно от measured tokens. Если исходный reserve потерян,
budget_charge_upper_bound=null, budget_reservation_complete=false, а не ноль.

## Offline-подготовка schema-пробы — 21 октября

Подготовка выполнена в отдельном audit worktree, без изменения живого runner.
Исходные payload двух cyclic cases восстановлены из pinned prompt manager,
исходных title/text и NER из verified response cache. SHA исходных запросов
совпали полностью; проверен61 файл SDK против pinned Git blobs. QA gold не используется.

```powershell
$prior = '<data-root>/indexes/e1/issue13-cycle-plan.json'
$probe = '.cache/e1-schema-probe/plan.json'
& '<hipporag-venv>/Scripts/python.exe' -m scripts.run_e1 prepare-schema-probe --prior-plan $prior --plan $probe --source '<pinned-hipporag-source>'
```

Команда только восстанавливает/проверяет и пишет private plan; маршрута запуска
модельных запросов в ней нет. При воспроизведении использован запрет
`requests.Session.request`; HTTP не выполнялся. Старые raw/manifest/plan неизменны.
Payload остаются локальными, в Git публикуются только counts/SHA:

| Case | Исходный request SHA256 | Schema request SHA256 | Резерв input+output |
|---|---|---|---:|
| 1 | `14160c662cfc367cb21f6185a132d7f6823f019b83057b4b5fcaa03b8e9373d5` | `19df1d19e21cba63469f9fb7776caa50274cfd2f56a7d5dbbe1e837018776871` | 8679 |
| 2 | `735c0f400433b9ab032325dcd8475d353440213d217dcec21bfab7b9f2668e06` | `b59cb5484dccf8784dc1b0dbad465be45738ee8d2e9aa278f41c6348e02d4a28` | 8990 |

Private plan SHA256: `443812bb6f72c57a1f22bbe53e248a8fabfeddd1c3ca3921a53528289c5312a1`.
В новом payload меняется только response_format: json_schema/strict с triples,
массивом3 непустых строк на тройку и uniqueItems=true. Модель, исходные messages,
seed/temperature/thinking и cap3072 прежние. Никакой дедупликации partial JSON.

Предел предложения: **2 POST**, NER0, retry0, остановка при первом отказе.
Общий резерв **17669** = UTF-8 bytes сериализованных payload +2048 framing/case
+3072 output/case. Это верхняя оценка guard, не измеренные server input tokens;
дополнительные server tokens пока неизвестны. Остаток Hippo **16065954** уже
вычитает всю известную историю и прежний unknown reserve7922. Резерв пробы
не прибавляется к physical_known_tokens до реальных ответов.

Локальный валидатор отвергает length, неизвестный usage, partial JSON,
дубли JSON fields/triples, лишние поля, неверную длину и пустые элементы.
Семантическая поддержанность проверяется отдельно по passage. Успех2/2 не
доказывает серверный enforcement uniqueItems и не разрешает полный rebuild.
Синтаксис схемы проверен `jsonschema.Draft202012Validator.check_schema` в SDK-среде;
локальные uniqueItems и длина tuple также проверены. Это не проверка backend.

Статус: **подготовлено offline; отдельное согласие на эту пробу получено21октября**.
Запуск отложен до завершения фоновой очереди и интеграции offline-исправлений в
живую копию. Команда запрещает запуск из отдельного audit checkout либо при
running manifest/lock индексатора. План сверяется повторной offline-реконструкцией;
SHA согласованного private plan передаётся явно. Canonical claim при failed prior
сохраняется после ошибки/аварии и запрещает второй запуск из другого каталога.

```powershell
# Только после остановки всей очереди, интеграции и offline gate в живой копии.
& '<hipporag-venv>/Scripts/python.exe' -m scripts.run_e1 run-schema-probe --plan '<audit-worktree>/.cache/e1-schema-probe/plan.json' --prior-plan $prior --source '<pinned-hipporag-source>' --env-file '<data-root>/<env-file>' --approved-probe-sha256 443812bb6f72c57a1f22bbe53e248a8fabfeddd1c3ca3921a53528289c5312a1
```

Результат сохраняется отдельно в `hipporag2/musique-schema-probe1` с raw,
journal, manifest/artifact SHA и full_index_authorized=false. Экспорт E1 добавляет
физические попытки диагностики к Hippo history ровно один раз, включая unknown;
их резерв отмечен отдельно от measured usage. Число triples не подтверждает факты:
semantic_support остаётся not_reviewed до отдельной проверки по исходному passage.

## 21 октября: повторный цикл и независимый RAPTOR

Cycle child остановлен после2329/5500 проверенных passages. На другом passage
исходный ответ:1038 input/3072 output,163 tuples/4 уникальных; корректирующий:
1091 input/3072 output,191 tuples/4 уникальных. Оба finish_reason=length.
Расход обеих попыток **8273** известен; частичные triples не приняты. Дополнительного
transport retry не было. Первая успешная проба не гарантировала отсутствие других
циклов. Третьего запроса на этот passage не выполнять без нового проверенного
протокола: повтор той же инструкции и увеличение cap не устраняют причину.

Общий физический known E1=5386821; historical unknown сохраняется. Исходные
failed manifests, журналы и plans неизменны. Причина SDK `unresolved_triples_stop`
отражается в безопасном `failure_diagnostic`: finish_reason, request SHA,
полнота usage и количества повторов, без текста passages/ответов.

После разбора отказа разрешено отдельно выполнить две независимые RAPTOR строки.
Они используют готовые Dense vectors и собственные прежние лимиты12M на датасет;
сброса бюджета/повтора HippoRAG нет. Новый канонический plan с lineage сохраняет
все failed/unknown; меняет code_commit только у нетронутых RAPTOR строк.
Проверяет SHA артефактов/журналов и отсутствие работающих workers; один claim рядом
с prior действует между worktrees. Plan запрещает запуск любого другого метода
до HTTP. При ошибке RAPTOR остановка, автоматического retry нет.

```powershell
$dataRoot = '<data-root>'
$prior = "$dataRoot/indexes/e1/issue13-cycle-plan.json"
$plan = "$dataRoot/indexes/e1/issue13-raptor-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 independent-raptor --prior-plan $prior --plan $plan
# Выполнить RAPTOR musique, затем hotpotqa командами run ниже с новым $plan.
```

Gitleaks на a994322 ошибочно распознал `cycle_repair_request_key` как API-key.
Значение — SHA256 payload, совпадающий с object_id в журнале и именем checkpoint.
Экспорт переименован в `cycle_repair_request_sha256`; исключение ограничено точным
historical fingerprint (commit/file/rule/line), остальные находки не скрываются.
Это исправление CI, не подтверждение готовности шести индексов. PR Draft/#13 открыта.

## Продолжение после цикла triple JSON

Network child остановлен:736 input/3072 output, length. В ответе на93словный
пассаж168 полных tuples, уникальных3 (каждая56раз). Это цикл; частичный JSON
не принимается. Caps1024/3072 прежние. `unique-triples-v1` добавляет последнее
user-сообщение: только triples, каждую поддержанную тройку один раз, без
named_entities, закрыть JSON после исчерпания разных фактов.

Сначала probe на том же source ID: NER только из verified cache, triple SHA
до HTTP совпадает с оборванным. Только stop/полный JSON/непустые уникальные triples
разрешают основной run. `cycle-probe.json` хранит результат, повторной оплаты
этой пробы при основной индексации нет. Исходные SDK prompts остальных passages
прежние. Только length с явным циклом (≥12 tuples, unique≤1/4) допускает один
корректирующий запрос. Всего≤20 коррекций/dataset, включая probe; обе попытки
учтены в журнале, связь payload SHA — в `cycle-repairs.json`. Новая неудача либо
иной length/parse/unknown останавливают пакет; transport retry0. HotpotQA получает
тот же policy только после успешной MuSiQue пробы и готового индекса.

Кэш объединяет оба предыдущих run; cache hits прослеживаются до physical producer,
length не попадает в accepted cache. Новые127317 известных tokens вычитаются из
остатка17150781: остаётся **17023464**. Unknown7922 сохраняется в резерве,
новых unknown в length нет. E1 суммирует всю историю, cost_complete=false.
Новая папка/UUID, один canonical claim; прежние raw/manifest/plan неизменны.
Это техническая адаптация extraction, не доказательство качества и не согласование O/N/R/H.

```powershell
$dataRoot = '<data-root>'
$envFile = '<data-root>/<env-file>'
$prior = "$dataRoot/indexes/e1/issue13-network-plan.json"
$plan = "$dataRoot/indexes/e1/issue13-cycle-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 cycle-resume --prior-plan $prior --plan $plan --passage-id '<verified-source-id>'
& '<hipporag-venv>/Scripts/python.exe' -m scripts.run_e1 run --plan $plan --env-file $envFile --method hipporag2 --dataset musique --source '<pinned-hipporag-source>'
```

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


## Уточнение отчётности после аудита 21 октября

`physical_known_tokens` — новые физические затраты с историей, без двойной оплаты
cache hits. `physical_usage_complete` — полнота этих журналов.
`standalone_known_subtotal` каждой строки добавляет для RAPTOR историю Dense
producer; `standalone_cost_complete` учитывает её unknown и историческую полноту.
Общий `cost_complete` требует полноты самостоятельных стоимостей всех строк.
`reused_leaf_build_cost` включает известные failed-попытки producer, а не только
последний успешный запуск. Исходные журналы при атрибуции не изменяются.
`measured_run_seconds` — длительность текущего run; `attributed_construction_seconds`
— сумма историй метода и производителя. Последнее не измерено как новый cold run.

Offline-аудит готовится в отдельном checkout: фоновая очередь использует закреплённый
commit. До её окончания не заменять исходники/HEAD работающего checkout.
Существующий restore валидирует topology; новая проверка дополнительно сравнивает
весь сериализованный round-trip. Полный E1 artifact пока не объявляется проверенным.
Диагностика HippoRAG описана как предложение в ADR-0022; новых POST аудит не выполняет.


## Подтверждённая остановка RAPTOR — 21 октября

Очередь завершилась `stopped_recorded`: MuSiQue manifest failed/HTTPError,
последняя физическая операция index_embedding, HTTP 413, ответ сервера
`the input length exceeds the context length`. Usage отказа неизвестен,
`tree.json` отсутствует; HotpotQA не стартовал. Это не потеря всего уже
оплаченного материала: проверить возможность reuse сохранённых ответов по SHA.

Не ждать автоматического продолжения и не считать snapshot running текущим.
Граница «после остановки всей очереди» для интеграции достигнута. Согласие
пользователя на Hippo schema-пробу 2 POST/17669 сохраняется; повторно его
не запрашивать, если проверка подтверждает прежние payload, бюджет и условия.
Это согласие не разрешает новую RAPTOR-индексацию или полный Hippo rebuild.

Перед решением по RAPTOR восстановить точный вход embedding и связь с summary;
посчитать его родным tokenizer BGE-M3 с учётом специальных токенов и контекста
локального сервера. Лимиты Qwen4096 и cl100k3000 измерены в других токенах.
Не заменять точный подсчёт числом символов. Не включать скрытую обрезку.
Варианты (пока не приняты): ограниченное пересуммирование проблемного узла с
проверкой BGE-контекста; либо явное разбиение и агрегация embeddings с отдельной
версией адаптера и одинаковой политикой обоим датасетам. Любой вариант сначала
offline, с сохранением failed/unknown и проверенным reuse, затем ограниченная
проверка по утверждённому плану. Одна исправленная summary не доказывает
работоспособность всей индексации.


## Последняя остановка и подготовленное продолжение RAPTOR —21октября

MuSiQue run68b112fc завершился failed в14:51MSK: при Layer1 pinned UMAP
отвергает n_neighbors=1 в рекурсивной группе2–4nodes. Новый расход1477962
известен полностью (1540POST), tree.json отсутствует; HotpotQA не запущен.
Это отдельная ошибка от раннего embedding HTTP413, чей unknown сохранён.

Локальный адаптер `pinned_gmm_umap_singletons_n_le_4_v1` завершает такие группы
singleton clusters. Обычные UMAP/GMM и recursive defaults сохранены; SDK bytes
проверяются против закреплённого Git. Политика одинакова для обоих датасетов;
её следует указывать при интерпретации E1. Подробности/альтернативы — ADR-0022.

После clean commit подготовить одноразовый canonical plan, без модельных вызовов:

```powershell
$prior = '<data-root>/indexes/e1/issue13-raptor-batch-plan.json'
$plan = '<data-root>/indexes/e1/issue13-raptor-clustering-plan.json'
./.venv-check/Scripts/python.exe -m scripts.run_e1 raptor-clustering-resume --prior-plan $prior --plan $plan
```

Команда проверяет immutable history, полный текущий usage, все response SHA,
Dense leaf producer, отсутствие активных workers/Hotpot outputs. Один claim
рядом с каноническим failed prior не допускает повторного продолжения в другой
папке. Новый MuSiQue output musique-cluster1; остаток9492570tokens,
HotpotQA12000000. Старая история/unknown сохраняются. Создание плана не запускает
HTTP; после этой остановки реальный stage требует отдельного решения о
продолжении. Offline-проверки не являются результатом реальной индексации.


Offline проверка исправления21октября завершена:349tests passed/16skipped;
отдельный pinned RAPTOR SDK test passed (fake models, index/save/reload,
исходный n_neighbors сбой для2/3/4nodes, HTTP forbidden). На полном MuSiQue
проверены2542physical response entries и5500Dense leaves;2548summary/embedding
callback воспроизведены из кэша,0physical attempts. Layer0 полностью совпал
с сохранёнными запросами. Layer1 завершил кластеризацию и остановился перед
первым uncached запросом; дерево ещё не построено. Safe proof result SHA:
`bf45c18ce135397ef4ab71e8b9d58f815470bce189da1ec53d0890c8fe356a1b`. Исходный failed manifest SHA:
`138e35a8c8993e732e7e623345a2a9aee70746fc3032fc9bfff28f1e6d88d276`.
Следующее продолжение использует обычный tracked run_e1 transport, без отдельного
модельного operator; новые HTTP сохраняются в том же формате journal/checkpoints.


## HotpotQA: summary length и подготовка одной пробы —21октября

RAPTOR MuSiQue957006e6 завершён:5500leaves,7438nodes, слои5500/1274/664,
точный save/reload0calls. HotpotQA ff75d8dd остановился23:12MSK на Layer1:
finish_reason=length, input3011/output4096/total7107. Ответ разворачивается
в каталог ТВ/кино/актёров (1785word tokens,600unique words); плотный цикл
как в предыдущем HippoRAG не установлен. Не увеличивать cap вслепую и не
принимать частичный ответ. Исходные response/journal/manifest остаются immutable.

HotpotQA2827physical POST:1414summary/1413embedding; known2693810.
Все usage в этом запуске известны, включая failed7107. Общий E1 known13052767,
upper budget charge13099389; старые unknown других строк сохраняются.
Остаток HotpotQA9306190 из12M не расширяется.

Предложена одна диагностическая проба `raptor_summary_300_words_v1`:
сохранить исходный user context целиком, добавить system-ограничение≤300слов,
компактная проза/без каталогов/повторов/новых фактов, cap1536. Успех требует
stop/nonempty/≤300whitespace words/≤4000UTF8bytes и известного usage.
Последний byte guard ограничивает диагностический ответ, не является точным
подсчётом BGE и не доказывает embedding compatibility или качество summary.
Семантическая поддержанность проверяется отдельно по context, без QA gold.

Подготовка проверяет точный SHA восстановленного исходного payload, все
source response SHA, завершённость журнала, Dense leaf producer и отсутствие
живых index workers. Новый payload имеет отдельный SHA; частичный старый текст
не очищается, не продолжается и не попадает в probe input. Общие параметры
температуры/seed/thinking и модель прежние. Проба не является принятой политикой
для полного benchmark; готовый MuSiQue из-за этой пробы не повторяется.

```powershell
$prior = '<data-root>/indexes/e1/issue13-raptor-clustering-plan.json'
$probe = '<private-dir>/hotpot-summary-probe-plan.json'
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-summary-probe --prior-plan $prior --recovered-payload '<offline-dir>/failed-payload.json' --plan $probe
# После конкретного согласования ровно1POST, без embedding/NER/retry:
./.venv-check/Scripts/python.exe -m scripts.run_e1 run-summary-probe --plan $probe --env-file '<env-file>' --approved-probe-sha256 '<plan-sha256>'
./.venv-check/Scripts/python.exe -m scripts.run_e1 report --plan $prior
```

Один claim summary-probe-once рядом с каноническим Hotpot prior действует
между каталогами/worktrees и сохраняется после ошибки. Любой изменённый
payload/code/config/SHA отклоняется доHTTP. Даже при ошибке сохраняются known,
unknown reserve и failed manifest; summary_probe входит в общий экспорт E1.
Максимум1target POST,0embedding/NER, стоп при первой ошибке. Успешный probe
имеет full_index_authorized=false: новый index continuation требует отдельного
решения и проверенного использования нового response SHA. Случайно прочитать
length как usable cache нельзя: explicit diagnostic flag возвращает его
только в failures, стандартный resume продолжает отклонять такой checkpoint.


Offline восстановление выполнено:2826verified responses воспроизведены,
0physical attempts. Канонический request SHA совпал с исходной попыткой:
`b243e8505a98c45dbe7f8a85fd505444554f611bc7bc0eb7cb1d358fc185ebdf`.
Файл восстановленного payload SHA:
`2be68e791be7f63960551e923c6b3ee772c21ad28c5297fdefce5d08603d7c32`.
Parent failed manifest SHA:
`9d6e9c32da818dae32722d35e46b960d55fc9d2e071effd16dbdddef3cbf2d87`.
Payload private; подготовка самостоятельно пересчитывает канонический request
SHA, поэтому произвольный новый context не пройдёт доHTTP. Probe требует
reported completion_tokens≤1536; известные токены сохраняются и при нарушении.

Дополнительный fresh-process MuSiQue reload прошёл с запретомHTTP:5500passages,
7438nodes, exact round-trip, journal SHA до/после одинаков. Tree SHA:
`241faf584908cf5cc06a5d531e1d108be47b5b6359da12d556ee74da6dc104a6`.
Manifest SHA `c57bd6e2bcbbfb3cb72c22925b7cfc5d1073167b6d40f184fc0b145c7774896b`.
Это проверка готового MuSiQue, не повторная индексация и не оценка качества.
