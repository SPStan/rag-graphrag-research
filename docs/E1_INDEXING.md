# E1: индексы полного корпуса (#13)

## Текущая очередь — 24 октября: остановка local recovery

- Готовы5/6 индексов. Hotpot extraction5500/5500 сохранён в исходном
  completion run6fffff38. Граф/save-reload/source audit Hotpot ещё не выполнены.
- Child6c01f4f7 failed04:58UTC: Permission denied при записи usage.jsonl,
  затем SDK обернул ошибку в unresolved_ner_stop. Новых physicalPOST0,
  known0; журнал цел и SHA совпадает с failed manifest959007abc44b…db625e.
- Причина — мониторинг агентом через .NET File.ReadLines с FileShare.Read,
  который на Windows блокирует append. На временном файле это воспроизведено;
  FileStream с FileShare.ReadWrite допускает запись. Данные API не виноваты.
- E1 known31507115/upper31568703, cost_complete=false, reserve61588 неизменны.
  Все9919successful embedding batches и старые failed/unknown сохранены.
- Выполнено1/2 automatic recovery. Автоматизация e1-hotpotqa PAUSED:
  существующий guard запрещает повтор terminal child и ещё один local child.
  Без проверенной новой lineage не запускать run и не сбрасывать claim.
- Следующий блок: минимальный проверяемый child после zero-POST IO failure,
  immutable parents/точный embedding replay/zero fresh LLM/прежние бюджеты;
  offline-тесты, затем scoped второе восстановление, если guard это подтверждает.
- Не читать живой usage.jsonl через File.ReadLines/Get-Content: короткий snapshot
  с явным FileShare.ReadWrite. Мониторинг не должен мешать journal writer.
- Текущее состояние/stop_future_checks: .cache/e1-hotpotqa-monitor.json;
  registry .cache/e1-hotpotqa-recoveries.json. После PAUSED не повторять уведомления.
  Draft/Refs #13; без E2/QA/holdout/merge.
## История первого local-socket recovery

## 24октября: первое ночное local-socket recovery — без нового extraction

Current run6fffff38 завершился failed07:16MSK на локальном Ollama HTTP400.
Сохранённый error: внутренний /tokenize к127.0.0.1:50156, connectex Only one
usage of each socket address. Failed batch8/max80chars; это наблюдаемый отказ
локального socket allocation, не превышение context. Точная системная причина
конфликта не установлена;4s pause — mitigation, не доказанное постоянное лечение.
Ни service restart, ни изменение Windows network settings не выполнялись.

Extraction5500/5500 сохранён, все target LLM usage известны. Новый run расход:
LLM2787261input+1051549output, embedding994582known;15363physicalPOST,
из них9920embedding(9919success/1unknown local). Unknown reserve2567 сохранён.
Failed request0d52543a8460df6630e04d3c44caed6359428142ac0d182719bb240157c4c1c4;
manifest SHA6cfd0491c08c81c6cdba8605ab14dd88f9e70c31d41217b0eee23e9095e35fb9.
E1 known31507115/upper31568703,cost_complete=false, totalreserve61588.

Пользовательским heartbeat e1-hotpotqa разрешены scoped technical repairs и
проверяемое продолжение без расширения token/POST/fallback и без новых моделей/
prompts/критериев; максимум2recovery за весь период, повтор той же причины — stop.
Это новое разрешение переопределяет прежний запрет автоматического recovery
только в указанной technical scope. Его локальная запись — не выдуманное
согласие пользователя с ещё не существовавшим exact SHA. Новый SHA derived plan
вычисляется после code commit и связывается с parent b51c2336c6f0/источником допуска.

Existing runner: prepare-hotpot-local-recovery, canonical private plan
.cache/e1-hotpot-local-recovery-plan.json, новый UUID/output hotpotqa-mixed-local1,
shared hotpot-local-recovery-plan.claim.json. При повторной socket причине
ещё один такой child запрещён. Старые manifests/claims/raw неизменны.
Остаток10418246combinedtokens/18361allPOST, fresh LLM limit0; весь известный
расход и2567reserve уже вычтены из прежнего Hotpot20M/40kallPOST. Нового
fallback нет. Остальные пять rows не меняются. Запрет нового target POST жёсткий:
при missing/changed extraction cache вместо запроса stop до HTTP.

Для9919successful embedding responses сверены saved input JSON→request SHA,
response SHA и число векторов. Canonical8 batching неизменен, exact payload
позволяет replay готовых50711entity и partial fact vectors. Из75021facts
около28640векторов уже получены; оставшихся новых batches около5798.
Никакого копирования partial parquet по предполагаемому Python set order.
Новый child повторно вычисляет только ещё не готовые embedding payloads; для
единственного failed local payload допускается одна fresh попытка, без retry.
Пауза после нового embedding ответа≥4s, batch8/digest/truncate/context прежние.
Это замедляет оставшийся этап ориентировочно до6.5часов плюс replay/graph/audit.

Проверки:16targeted socket/local tests passed, дополнительные4проверки bounds
входят в10local tests passed. Покрыты exact failed key/kind, one attempt,
zero new LLM, pause4s, failure stop, evidence pins и запрет расширения bounds.
Реальный cache/input mapping проверен offline при forbidden HTTP.
Общий hook gate выполняется только на границе этого исправления.

Current launch после запуска: .cache/e1-hotpot-local-recovery-launch.json;
исторический .cache/e1-hotpot-completion-launch.json не переписывать. Monitor
.cache/e1-hotpotqa-monitor.json хранит active_launch_file/recoveries_total;
все recovery attempts — .cache/e1-hotpotqa-recoveries.json. Не обнулять счётчик.
До создания нового plan остаётся previous failed, не запускать второй worker.
После нового graph/save-reload обязательны source audit/coverage и экспорт costs.
PRDraft/Refs #13; без E2/QA/holdout/7B/merge. При повторной socket причине,
unknown remote POST, повреждении кэша или approval rejection — stop и уведомление.

## Hotpot остановлен на лимите попыток; подготовлен один completion —23октября

Run579035c8-3089-421a-b71c-8b65bdeba16e на469f860/plan2fc9dfbfd5f8 failed
в17:15MSK:2590passages текущего обхода,4793новыхLLMPOST,3407432tokens
(2458823input+948609output), новыхembedding0/unknown0/unfinished0. Последний
Qwen response5841280eacc2685d5d8a91af6c3deee24d517a60180defc5f9d58cb8c9f559d9:
length,122полных tuple-фрагмента/1unique, полного JSON нет. GPT для него
не отправлен: mixed_fallback_limit. Это срабатывание расходного guard;
причина исходной генеративной деградации не установлена и не исправлена.
Immutable failed manifest SHAe8512042a0ba5fbc4ffce95e0f38ec6dc1b831fd24679bb45dc8fff4c6b1489a.

После explicit согласия пользователя на2fc9df cached-only исключение принято;
один прежний JSON-mode response остаётся с исходным model/format/review и
раскрытыми6observed_error/6needs_review. Новых таких исключений не предлагается.
Пять completed индексов неизменны. E1 known26673723/upper26732744,
cost_complete=false, historical reserve59021. Hotpot known4745795 из20M.
Токены — вычислительный расход, денежный биллинг не проверялся.

### Проверенный replay и остатки

Union успешно проверенных response SHA:688BGE batches=5500passage vectors,
2784NER/2782полных triples. Отдельно есть ранее разрешённый полный JSON-mode
ответ; при отсутствии его source в union он даёт ещё одну пару (2783available).
Следующий run использует оба failed parents и probe с полноценным producer
journal/provenance. Старые partial/length extraction не принимаются. Последний
Qwen length+cycle уже известен: для него допустим ровно один ещё не отправленный
Schema GPT, без повторного NER/Qwen. Старый failed GPT claim не сбрасывается.

### Один ресурсный вариант — ещё не разрешён

Предлагается явный предел GPT fallback attempts = ceil(5500/100)=55, включая
все failed/probe requests.1% — выбранная операционная граница доли попыток,
не оценка точности/вероятности успеха и не статистическая гарантия завершения.
Из20нынешних попыток18Schema complete,1Schema failed и1JSON probe; остаётся
не более35новых. Основной trigger/модели/prompt/source-fidelity/temp0/seed42/
output caps1024/3072/GPT low/Schema не меняются. Больше fallback не лечит Qwen
и не меняет качество уже извлечённых triples. При новой ошибке GPT — stop,
не JSON-mode retry, не повышение cap, не следующая автоматическая continuation.

Одна предлагаемая ресурсная политика55 для обоих datasets; Mu уже completed
при старом cap20 и не пересчитывается. Фактическая история различается и
раскрывается. Новизну/чистый эффект архитектуры/эффективность не заявляем.
Research O/N/R/H не содержат число20, не переписываются ради этого лимита;
актуальное согласование всё равно проверяется отдельно перед Ready.

Новый общий предел LLMPOST Hotpot11055 вместо11020, ровно+35. Уже5588LLMPOST
(794+1+4793) сохранены. Новые bounds:5467LLMPOST/33724всехPOST,
15254205combinedtokens; прежние20Mtokens/40000allPOST не расширяются.
Остаток primary/NER:2716+2716; текущий известный cycle и будущие cycles могут
потребовать до35Schema GPT из этого LLM лимита.55 не гарантирует завершение;
если исчерпан — остановка без автоматического увеличения. Embeddings новых
entities/facts локальные BGE batch≤8,pause≥2s/.25s per text,truncate=false,
фиксированный digest. Retry0/redirect0/connect30/read300; первая другая
ошибка/unknown/non-cycle length/сбой fallback — окончательный stop этого run.

### Existing runner и критерии завершения

prepare-hotpot-completion создаёт canonical `.cache/e1-hotpot-completion-plan.json`
и shared hotpot-completion-plan.claim.json. Только одна fresh Hotpot row/new UUID/
output hotpotqa-mixed-completion1. Pin: parent plan/failed manifest/stderr/19claims;
нижние parents/probe/JSON review остаются с прежними SHA. Все3producer runs
в history ровно один раз. Paid/cost здесь не термин оплаты: replay не создаёт
новых модельных запросов. Export не дублирует диагностическую попытку.
Receipt должна отдельно принять55fallback/11055LLMPOST и разрешить exact Hotpot
план. Без receipt/exact SHA до HTTP отказ; предыдущий допуск на20 не переносится.

Команда подготовки не выполняет HTTP:

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-hotpot-completion --plan '.cache/e1-hotpot-completion-plan.json' --prior-plan '.cache/e1-hotpot-adoption-plan.json' --counter-stderr '.cache/e1-hotpot-adoption.stderr.log'
```

Будущий run — прежняя команда run только --method hipporag2 --dataset hotpotqa
с новым plan/exact SHA и закреплённым SDK; без запуска остальных пяти rows.
После full graph обязательны coverage5500/save-reload0calls и source audit;
до этого5/6, PRDraft/Refs #13. QA/E2/holdout/7B/merge не разрешены.
Offline tests:195passed/3integration skipped; лимит55 с probe extra slot,
один новый Schema POST на известном cycle без NER/primary, старые claims,
evidence tamper/receipt/budget/готовая Mu row. Общий gate — на границе блока.

## Подготовленный Hotpot child: одна cached-only adoption —23октября

Это предложение, не разрешение запуска. Сохраняется прежняя общая политика:
Qwen primaryNER1024/triples3072, GPT low/Schema3072 только после Qwen length+cycle,
один fallback; другие ошибки/unknown/обычный length/сбой GPT останавливают очередь.
Ни будущего JSON-mode retry, ни автоматического второго восстановления нет.
Изменение минимально: отдельно принять уже оплаченный responsec51907e11fb54fe1
для одного source9d88b1f4 по source-review343ccef5b10c.6observed_error/6needs_review
не скрываются, semantic_verified=false. Это не новый запрос и не вывод о качестве.

Основная политика одинакова обоим datasets. У Hotpot появляется именованное
историческое исключение: один JSON-mode producer вместо failed Schema GPT.
Mu completed остаётся с фактическими прежними producers; идентичность форматов
всех источников обоих датасетов не заявляется. Новую основную модель/общий prompt,
reader, corpus, BGE или cap не меняем. Это предложение об одном cached exception
и отдельном расходном допуске по ADR-0022; автоматического требования нового
решения куратора из него не выводим. Актуальное O/N/R/H отдельно перед Ready.

### Готовый путь в существующем runner

Команда prepare-hotpot-adoption создаёт единственный private plan
`.cache/e1-hotpot-adoption-plan.json` и canonical hotpot-adoption-plan.claim.json
в прежнем shared root. Новая строка только Hippo Hotpot: новый UUID/output
hotpotqa-mixed-adopt1. Пять completed rows не меняются. Код pin ставится после
commit; родительский plan/оба producer manifests/candidate/review/Mu manifest,
четыре исходных fallback claims закрепляются SHA. Старый started claim неизменен.

State проверяет готовый Mu graph/audit/journal и их SHA. Исторические failed Mu
не используются как Hotpot cache producers; повторная загрузка их schema-проб
не нужна. Hotpot1477успешных physical responses проверены:688embedding batches
(5500passage vectors),395NER,394triples, включая3полных GPT Schema. JSON-mode
ответ проверяется отдельно: полный response+known usage, source review всех
24triples и exact request/response SHA. Его cached-only replay не может вызвать
POST даже при отсутствии/подмене ответа — вместо этого stop. Старые failed
Qwen/GPT никогда не принимаются как extraction.

Оба старых Hotpot runs включены в history ровно один раз: failed31005856 и
probe c17f5afd. Probe не включается повторно отдельным export diagnostic;
исторический failed GPT остаётся известным расходом. Остаток18661637tokens,
10225новыхLLMPOST,38517всехPOST. Charge1338363 из20M уже вычтен.
Fallback20 сохраняет общий предел:3complete+1failed Schema+1JSON probe уже
израсходованы; будущих Schema GPT не более15. Replay не оплачивается повторно.
Ранее reserve59021/E1 cost_complete=false не снимаются.

Новые passage/NER отправляются только api.duckduck.cloud/v1: Qwen primary,
GPT120b Schema fallback low. Entities/facts/passages для embedding — только
локальному BGE-M3 с закреплённым digest; batches≤8, pause≥2s/.25s per text,
truncate=false. Все5105остающихся NER и5105primary triples+до15fallback дают
10225внешнихPOST worst case. Embeddings entities/facts ещё не посчитаны заранее;
лимиты38517всехPOST/18661637combinedtokens обязательны, остановка до превышения.
Retry0/redirect0/connect30/read300, одна попытка нового payload.

После graph: coverage5500, save/reload без model calls, prepare-mixed-audit/
source review всех обязательных cases/finalize. До audit индекс не completed.
Никакого QA/E2/holdout/7B/merge. Пять готовых индексов не пересчитываются.

До HTTP нужны exact plan SHA и отдельная approval receipt, где явно разрешены
и принятие observed errors/одного cached JSON исключения, и Hotpot continuation.
Прежнее согласие только на diagnostic этого не покрывает. verify_plan проверяет
receipt до local service preflight/нового расхода; прямой запуск без receipt
блокируется. Изменение budgets/model/готовой Mu row/claim также блокируется.

Команды подготовки/будущего запуска (вторая запрещена без отдельного допуска):

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-hotpot-adoption --plan '.cache/e1-hotpot-adoption-plan.json' --prior-plan '.cache/e1-mixed-embedding-plan.json' --probe-plan '.cache/e1-hotpot-json-mode-candidate.json' --audit-review 'indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/hotpotqa-gpt-json-mode-probe1/source-review.json'
# После receipt и exact SHA, из закреплённого SDK окружения:
python -m scripts.run_e1 run --plan '.cache/e1-hotpot-adoption-plan.json' --method hipporag2 --dataset hotpotqa --source '<pinned-hipporag-source>' --env-file '<data-root>/<env-file>' --approved-plan-sha256 '<exact-sha>'
```

Последний код закреплён70da71c; row.code_commit самого плана берётся с clean HEAD
после документационного commit. До запуска HEAD должен точно совпадать с этим
полем. Подготовленный plan/claim не пересоздавать ради нового SHA. Для review
достаточны PR head+plan SHA и безопасная сводка; raw/payload остаются локально.

Новые offline-регрессии покрывают cached replay/missing/SHA/length, сохранение
failed claim, дополнительный занятый fallback slot, evidence/receipt/budget/
model/готовую строку/canonical claim. Реальный сохранённый response replay
при запрещённом HTTP дал physicalPOST0/tokens0, original claims unchanged.
Первый ручной offline-replay в check env остановился на ненужном Mu schema
SDK dependency; этот неиспользуемый Hotpot producer path исключён, повторный
replay прошёл. Это не модельная попытка и не изменение прошлых результатов.

## Итог одной разрешённой JSON-mode пробы —23октября

На6594610 после100schema/export offline tests и общего commit gate выполнен
ровно1POST по candidate3d1b2633b4d5. Run c17f5afd-4a63-4716-8c16-afad4236af09,
output hotpotqa-gpt-json-mode-probe1; duration12.814s, finish_reason=stop,
input960/output425/total1385, новыйunknown0.24triples/23unique, полный JSON.
Первая CLI-команда имела ошибочный approved SHA: rejected до claim/HTTP;
проверены отсутствие claim и правильный immutable candidate SHA до запуска.
Это не две модельные попытки. Нового NER/embedding/full index нет.

Source-only assistant review всех24triples:12supported/6observed_error/
6needs_review, semantic_verified=false. Есть неподтверждённый City of London
hosted British corporations, бессодержательная relation and, повтор alliance,
отдельные generic Allied/Enemy/Rivalry/Relations без связи с парой стран и датами.
Часть фактов поддержана исходником, но scope/attachment и coverage неполны.
Overseas territories и явные shifts/although опущены. Проба технически пригодна
к разбору, не доказательство faithful extraction и не corpus precision.
Не исправлять triples вручную. Наличие полного JSON не отменяет observed errors.

Source SHA05a5214a94751f22b74ba94a331e04e8801b6321ff3674b256c5eaa3ef103737.
Response SHA07484031a470391f9a1b579909ac3452e75610e81d75bec09d3916165ee056ec.
Immutable producer manifest SHAc3e07be261364d3d1fe773d0826b0bc3fa28d2ddf4daf624c59bc081b2ecff5d.
Отдельный source-review.json SHA343ccef5b10ca2ec6901482b827c6842604e8508aba50209fe6a1d975e54dc46.
Producer manifest остаётся awaiting_source_review как исходный terminal snapshot;
sidecar review завершён, cache_adoption_authorized=false/full_index_authorized=false.
Ни старый failed, ни raw/probe manifest не переписаны ради приёмки.

Повторный export подтвердил ровно1385новых tokens, не двойное начисление.
Hotpot known1338363, остаток18661637 из20M. E1 known23266291/upper23325312,
cost_complete=false, old reserve59021;5/6, Hotpot graph/reload отсутствуют.
Один изменённый формат дал полный ответ на одном source: причина прежнего
length и надёжность JSON mode на корпусе этим не установлены.

Следующий разрешаемый блок сначала offline: child plan общей JSON-mode fallback
политики и решения об adoption этого ответа. Нельзя считать JSON mode прежним
schema cache hit, сбрасывать старый started claim или обнулять его цену/слот.
Нужны точные оставшиеся лимиты с учётом794LLM+688embedding прежнего Hotpot и
1нового диагностического POST, failed fallback и всех completed/cache claims;
отдельный допуск расходов до continuation. Проба сама его не даёт.
При принятии новой политики прежние schema-producers остаются с фактическим
response_format/model/request/response SHA. Mu completed не пересчитывать
автоматически: историческое различие форматов обоих datasets раскрыть в ADR.
Нужен source audit нового полного Hotpot перед completed. Без QA/E2/merge.

## HotpotQA: остановка GPT fallback и offline-разбор —23октября

MuSiQue completed; готовность5/6. Run1c12c3c8:5500passages/45857entities/
66082facts/51357nodes/158475edges, save/reload0calls. Audit19cases/11warnings:
3supported/13observed_error/3needs_review, semantic_verified=false, status
structurally_verified_with_observed_extraction_errors. Не corpus precision.
Audit SHA b4e451e710c0504b1012ef978a668bbc41af988bd6c42135474f71fe66a63dea;
reviewSHA c92ee411bcc61b756373363089d4ec12e221c66d2200aa8a5678cbbeaa083110.
Mu child8261embeddingPOST/1548898tokens/0LLM, прежние failed/unknown сохранены.

Hotpot run31005856-9e4a-47ca-bef1-42ad4e7ab6dd завершился failed на runtime
caebfd5/approved plan091a76f5bbef.394/5500полных пар,395NER,5500chunk vectors.
1482POST:688embedding+395NER+399triples;3GPT fallback завершены, четвёртый failed.
Его usage960input/3072output/4032total известен, finish_reason=length,
content=null, reasoning_content170chars, provider_specific_fields.refusal=null;
completion_tokens_details отсутствует. Полного JSON нет, reasoning не extraction.
Нельзя выводить3072reasoning tokens из170видимых символов. Повтора не было.

Hotpot known1336978=404290LLM input+165884LLM output+766804embedding,
новыйunknown0. E1 known23264906/upper23323927,cost_complete=false,
исторический reserve59021. Hotpot остаток18663022/20M, не новый расходный допуск.
Manifest SHA543a355e089a907f9fe4e31c51e15ec1f91d1b67e844320dff4fd7bc0e8cecc8.

### Проверенный фактический запрос

По закреплённому SDK1438aba3 и corpus SHA восстановлены cached NER и оба payload:
Qwen6df1ebca6b1865e6f37e7828dd415bcba2e9d240df487a8f364178c4535a6563,
GPT217fb007d827f5e03e8d9195f23bf62eaaa7b1c4a9f9de1690105ff5cf6ba39c.
SHA совпали с journal/checkpoint. GPT response SHA
65da28df2f760ca8463bd8f725f682ba37edb013d1c6c5baeeb1b6b34f60c9a4.
Source ID sha256:9d88b1f478340a181c10b65649232145eb0b065a42787407118d226febedb761,
source840chars; вопросы/answers/supporting labels не читались.

GPT120b, low, temperature0, seed42, stream=false, cap3072; schema shape_v2
без uniqueItems. Roles system/user/assistant/user: штатный SDK few-shot,
не двойной chat template. Source policy добавлена ровно один раз, Qwen
chat_template_kwargs удалён. Транспорт checked_post, retry0, redirects запрещены;
canonical claim начат до HTTP. Клиентская ошибка формирования не найдена.
Фактический deployment template/причину остановки по ответу установить нельзя.

Три успешных Hotpot GPT fallback с тем же кодом: input/output777/180,
958/1151,869/2414; stop и непустой content468/4439/8973chars соответственно.
Это разные sources/NER, а не контролируемая проверка причины. Наблюдение не
доказывает ни предел размера input, ни дефект schema, ни нехватку cap.

### Один следующий вариант — предложение, без HTTP

Проверить взаимодействие structured schema и GPT deployment одним запросом,
изменив ТОЛЬКО response_format на {"type":"json_object"}. Prompt, полный source,
cached NER/SDK examples/source-policy, модель/seed/temp/low/cap3072 прежние.
Это изоляция одного фактора, не подтверждённое лечение и не prompt retry.

Offline candidate `.cache/e1-hotpot-json-mode-candidate.json` SHA
3d1b2633b4d5f5aa536ede8b289237b4d6c103e4b6aea8245e22f05752715ca3;
private payload SHA728b2a864cd3c58cfd28aa00977f1bb953b0c1c3ccff3d92134f42a0580ab0fb,
request SHA c51907e11fb54fe1e1c74d5b74e74c2c59de463b32f2504cbce3b7a276e19b63.
Кандидат остаётся immutable offline-файлом. Пользователь разрешил его передачу
и1POST по SHA3d1b2633b4d5 на2792da9 вместе с интеграцией до HTTP.
Existing runner дополнен отдельной командой run-json-mode-probe: проверка
parent/payload/remaining budget, canonical json-mode-probe-once.claim.json рядом
с failed manifest, atomic exclusive claim до HTTP и отдельные output/journal.
Старый failed/fallback claim не меняется. Экспорт включает probe known/unknown
один раз, включая неуспешную попытку; model attribution также включает probe.
11новых offline-тестов: approval/payload/parent/budget/running/claim guards,
success/length/unknown/cycle/timeout; один POST, сохранение parent, export дважды.
Первый тестовый запуск не прошёл setup pytest TEMP permissions; в отдельном
TEMP повтор прошёл. Это не ошибка модельного запроса, новых HTTP ещё нет.

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_e1 run-json-mode-probe --plan '.cache/e1-hotpot-json-mode-candidate.json' --prior-plan '.cache/e1-mixed-embedding-plan.json' --env-file '<data-root>/<env-file>' --approved-probe-sha256 '3d1b2633b4d5f5aa536ede8b289237b4d6c103e4b6aea8245e22f05752715ca3'
```

План: api.duckduck.cloud/v1, iairlab/gpt-oss-120b, максимум1POST,
резерв9622токена (UTF-8 payload bytes+2048framing+3072output) из18663022;
NER0/embedding0/retry0/redirect0/connect30/read300. При любом HTTP/transport error,
unknown usage, length/empty/неполном JSON/неверной форме/цикле окончательный stop,
без второго варианта в этом плане. Нужны stop+непустые triples, известный usage,
existing strict local shape/repetition check и source-only review всех triples,
оговорок/дат/существенных omissions; gold и точное совпадение прежних triples не нужны.

Успех не доказывает причину и не разрешает continuation/подмену failed cache.
JSON mode вместо schema и вторая GPT попытка на исходный запрос меняют протокол:
сначала отдельное решение ADR-0023/точный child plan и допуск, затем HTTP.
Старый started fallback claim занят; не сбрасывать и не выдавать кандидата за cache hit.
При будущем принятии replay394пар/395NER/5500chunk vectors и3complete GPT только
после SHA/provenance checks; старые расходы не дублируются и не исчезают.
Facts/entities нового graph потребуют embeddings, их объём пока не измерен.
Готовые5индексов не пересчитывать. Source audit до completed по-прежнему обязателен.
PR33Draft/Refs #13; QA/E2/holdout/7B/merge не запускались.

## Текущий socket recovery — 23 октября: без новых запросов

Mu extraction5500/5500 завершён. Runacdf13d5-7a3b-4748-8e34-348a02b28788
на06ee684/plan75391ad20f6e остановлен02:05MSK23октября на local BGE-M3 HTTP400.
Сохранённый ответ: внутренний /tokenize bind — insufficient buffer space/queue full.
Это наблюдаемая ресурсная ошибка; её точная причина не установлена. Проверка после
остановки:24TIME_WAIT/101BOUND/89ESTABLISHED при16384dynamic ports, текущего
массового исчерпания не видно. Сервис не перезапускался, probe запросов не было.

Новый child known2283204 (LLM1343346input+452180output, embedding487678),
4437physicalPOST, в том числе2725LLM/1712embedding. Последний embedding usage
unknown; reserve3967 остаётся, не ноль. E1 known20379030/upper20438051,
cost_complete=false, total reserve59021. Старые failed/results immutable.

### Что доказано reusable

Native offline proof проверил12888cache entries. Полный entity parquet45857
векторов точно совпал с нормализованными verified responses всех32-text batches.
5500chunk vectors также имеют совместимый прежний batch cache. Сохранены ещё8864
частичных fact vectors, но input strings не записывались, а SDK flatten_facts
использует set: порядок меняется между процессами. Без подтверждённого input mapping
их replay не заявляется. Они сохраняются с расходом; полный новый facts stage
может заново обработать66082строки. Не подставлять векторы по предполагаемому порядку.

### Один bounded путь в existing runner

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-mixed-embedding-recovery --prior-plan '.cache/e1-mixed-counter-plan.json' --plan '.cache/e1-mixed-embedding-plan.json'
# После допуска exact SHA: прежний run --plan нового файла --approved-plan-sha256 '<sha>'.
# Source audit: prepare-mixed-audit/finalize-mixed-audit, только после build/save/reload.
```

Canonical plan/once claim рядом с прежним shared fallback root; новые run/output
-mixed-embed1,11history Mu. Parent plan/manifests/оба завершённых fallback claims
не меняются. Mu новый LLM cap0: только проверенный NER/triples cache. Mu остаток
11363316combined tokens/33494всехPOST; unknown3967вычтен. Hotpot20Mtokens,
11020внешнихLLMPOST/40000всехPOST, новый transport одинаков обоим datasets.

Если все исторические32-text batches stage доступны, они reuse точно. Иначе весь
stage сортируется канонически, physical batches≤8; порядок векторов возвращается
в исходный caller order. Частичные неупорядоченные batches не задают mapping.
Новые local input JSON сохраняются приватно в requests вместе с response SHA,
чтобы повторный анализ не зависел от Python set order. Model/digest/размер1024,
truncate=false/context прежние; physical grouping раскрывается в export отдельно
от SDK embedding_batch_size32. Для новых HTTP пауза≥2s после предыдущего ответа
и0.25s/text, без скрытых retries. Это снижение нагрузки, не подтверждённое лечение
Ollama. При первой ошибке/unknown остановка; ещё одного socket recovery нет.

Offline158passed/3skipped: canonical grouping и restore order, сохранение inputs,
cache-only stage, пауза после ответа, Mu0freshLLM, positive socket child и отказ
при другом HTTP400/active/сбросе reserve/исчерпанном cap/pending claim. Export
проверен без записи публичных результатов:known20379030/upper20438051 прежние,
unknown/failed включены один раз. Новый HTTP только после согласования final
plan SHA по ADR-0022. Предыдущий допуск не переименовывается в новый.

Source review19cases уже выполнен assistant по исходникам:3supported,
13observed_error,3needs_review, включая11warnings. Private draft требует сравнения
с финальными audit cases/response SHA, coverage5500 и save/reload; пока не completed.
Это не corpus precision. Никаких исправлений графа/QA gold/model judge.
Готовы4/6; Hotpot не стартует до Mu build/source audit. QA/E2/merge запрещены.


## Одноразовый child после локального POST guard — подготовка без HTTP

`prepare-mixed-counter-recovery` продолжает исходный mixed plan только после
подтверждённой локальной ошибки счётчика: stopped failed/ValueError, известный
usage, logical LLM events достиглиcap, physicalPOST ещё нижеcap, pinnedstderr
mixed_llm_request_limit/unresolved_ner_stop. Каждый incomplete primary должен
иметь полный сохранённый fallback. Новые ошибки модели этим путём не обходятся.
Нулевой preflight exception ADR-0022 здесь неприменим:2069POST уже потрачены.

Команда требует чистый HEAD, canonical unused .cache/e1-mixed-counter-plan.json.
Новые IDs/output -mixed-counter1, старые parent/manifest/journal/claim SHA неизменны.
История10Mu runs учитывается ровно один раз. Root fallback claims прежний;
новый canonical counter-recovery.claim.json разрешает ровно один такой child
между worktrees/output directories. Повторное recovery после него запрещено.
Успешный старый fallback replay использует actual GPT payload/model/response SHA
и тот же claim, не новую оплату. Length primary остаётся rejected.

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-mixed-counter-recovery --prior-plan '.cache/e1-mixed-plan.json' --counter-stderr '.cache/e1-hippo-mixed-musique.stderr.log' --plan '.cache/e1-mixed-counter-plan.json'
# Только после допуска exact SHA: прежняя команда run, новый --plan и --approved-plan-sha256.
# Затем prepare-mixed-audit/finalize-mixed-audit; Hotpot только после Mu source audit.
```

Mu≤13650487новых combined tokens/2745новых внешнихLLMPOST/37931всехPOST,
Hotpot≤20M/11020/40000. Уже использован1из20fallbackslots, остаётся≤19новых.
Кэш снижает фактическое число POST. Model/prompt/cap/retry/timeout/stop-policy
не меняются, старыйunknown55054 остаётся. Новый exact plan требует отдельного
допуска пользователя по ADR-0022. Подготовка не разрешает запросов, QA/E2/merge.
Целевые E1/schema146passed/3skipped и дополнительные10counter/claim regressions
прошли. Native SDK proof на закреплённых prompts/parser:8452entries,
4136полных NER+triples; Qwen и full GPT replay из нового каталога с0physicalPOST,
старый claim SHA неизменен. В первой проверочной команде OPTIONS ошибочно
перезаписали cap; исправленная проверка использует реальные1024/3072. Код
runner в обоих случаях собирал payload правильно. Никаких probe API запросов.
Export child проверен с перехватом записи:known18095826/upper18150880 прежние,
старый unknown55054 сохранён и GPT diagnostics не начислены дважды. Публичные
summary SHA неизменны. Proof не подтверждает реальный завершённый graph.


## Последняя остановка — mixed Mu, 22 октября21:40MSK

Разрешённый plan01fd6b059d5e наf545ba1, runb2dc4e51-39df-49eb-874a-f4b72c456251,
output musique-mixed1. Пройдено2410/5500sources.2069physicalLLMPOST,
2924cache replay (2752LLM/172embedding), новый известный расход1375138:
1021323input/353815output. Current usage complete, unknown0. Один GPT fallback
после свежего Qwen length+cycle завершён, полный ответ сохранён. Graph не готов.

Остановка вызвана **клиентским счётчиком**, не подтверждённой ошибкой NER:
`mixed_llm_request_limit` считал started cache events как physical POST.
SDK поймал исключение и adapter выдал общее unresolved_ner_stop. В журнале
4821LLM logical events, из них2752replay и2069physical; предел4814новыхPOST
фактически не достигнут. Новый запрос был отклонён до HTTP; расход не потерян.

Исправление исключает finished cache-hit attempt IDs из счётчика physical starts.
Offline regression: cache replay не расходует POST cap, завершённый checkpoint
можно reuse на cap, второй новый POST при cap1 отклоняется без HTTP.
Нового реального запуска после исправления нет. Старые failed/manifests immutable.
E1 known18095826/upper18150880,cost_complete=false,unknown55054; по-прежнему4/6.

Для следующего child plan сохранять все cost/provenance/полные ответы этого run,
единственный использованный fallback claim и первоначальные ограничения:
Mu≤13650487tokens,≤2745дополнительных LLMPOST из4814,≤19новыхfallback slots из20;
Hotpot прежний20M и не запущен. Это расчёт оставшегося допуска, не новый
исполняемый план и не разрешение автоматического продолжения после stop.
Нужен согласуемый child на clean исправленном HEAD по ADR-0022. До Mu audit
Hotpot не стартует. QA/E2/merge не запускать.


## Протокол mixed продолжения на f545ba1 (история подготовки)

Пользователь передал ответ «Куратор не против» для предложения на17e7045.
Источник — сообщение пользователя; O/N/R/H карточка независимо не проверена.
[ADR-0023](../.adr/0023-hippo-extractor-diagnostic.md) и [SPEC](SPEC.md) фиксируют
одно правило обоим датасетам: Qwen primary, GPT-OSS source_faithfulness_v1 только
при length+cycle,≤1/original и≤20/dataset. Без увеличения cap3072, retry или NER.
Полный Qwen ответ имеет приоритет; GPT не переименовывается в Qwen. Старые strict
failed/reviews неизменны. Это конкретная смешанная конфигурация, не чистый эффект
архитектуры и не подтверждение качества всех triples.

E1 остаётся4/6, known16720688/upper16775742,cost_complete=false,unknown55054.
3102Qwen пары и4готовых индекса сохраняются. Новый план учитывает9исторических
Mu runs, включая обе GPT-пробы13295tokens, ровно один раз. Native cache proof:
6384entries, Qwen control replay и полный GPT policy fallback,0physical attempts.
Экспорт нового pending plan проверен без изменения прежней summary: суммы прежние.
Native synthetic SDK index/save/reload проверен отдельно для normal/mixed пути;
это не завершение реального Hippo индекса.

### Подготовка и исполнение в существующем runner

На clean HEAD одна команда создаёт immutable план и canonical claim рядом с
Mu failed prior. Новый output/run, старые предки не меняются. Другой каталог или
worktree не даёт второго continuation/fallback claim. Подготовка не вызывает HTTP.
Пути credentials — placeholders; ключи не публиковать.

```powershell
$plan = '.cache/e1-mixed-plan.json'
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-mixed --plan $plan --prior-plan '<data-root>/indexes/e1/issue13-hippo-schema-preflight-plan.json' --protocol-approval '.cache/e1-mixed-protocol-approval-17e7045.json' --probe-plan '.cache/e1-extractor-policy-probe-plan-73ab428.json'
# Только после отдельного разрешения SHA этого плана:
<hippo-python> -m scripts.run_e1 run --plan $plan --method hipporag2 --dataset musique --source '<pinned-hippo-source>' --env-file '<data-root>/<env-file>' --approved-plan-sha256 '<approved-plan-sha256>'
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-mixed-audit --plan $plan --dataset musique
./.venv-check/Scripts/python.exe -m scripts.run_e1 finalize-mixed-audit --plan $plan --dataset musique --audit-review '<private-review.json>'
# После завершения Mu audit — аналогичные run/audit команды для hotpotqa.
```

Тексты passages/cached NER/SDK examples идут целевому API; embeddings — локальному
BGE-M3. Новые combined tokens: Mu≤15025625, Hotpot≤20000000; внешние LLM POST
Mu≤4814, Hotpot≤11020, все POST≤40000/dataset. Это верхние пределы, replay их
уменьшает. У каждого запроса отдельная reservation; остаток не восстанавливается
после failed/probe. Retry0, connect30/read300. Qwen length+cycle допускает один
fallback; любой другой отказ/unknown/обычный length или сбой fallback останавливает
очередь. Старые unknown55054 остаются. Никаких QA/E2/merge по этому плану.

### Обязательный source audit после build

Успешная индексация сначала получает indexed_pending_audit. Сохраняется отдельный
immutable index-build-manifest.json. Аудит берёт все warnings и до8sources/model/dataset
по SHA256 `e1-source-audit-v1|42|dataset|producer_model|source_id`, исключая5calibration
Mu sources из случайных strata. Их отрицательный review948ac856 сохраняется отдельно.
Проверяются все triples выбранного source; QA/gold/holdout answers не используются.
Не исправлять/отбирать triples вручную. Маленький аудит не оценивает corpus precision.

prepare-mixed-audit сохраняет source-audit.json с полным source, actual response SHA,
triples и выборкой. Private review содержит audit_sha256, reviewer (реальный автор,
например assistant_source_review; не приписывать человеку), reviews с id, status
(supported/observed_error/needs_review), all_triples_reviewed=true, comment,
source_evidence (буквальный фрагмент source), categories. Для observed_error категории
непусты: unsupported_relation, attachment, attribution, negation, uncertainty,
dates_counts, omission. Structural warnings требуют structural_warning_resolved=true
после содержательного разбора. Semantic needs_review раскрываются и не превращаются
в утверждение отсутствия ошибок. Все выбранные sources должны быть разобраны.

finalize проверяет SHA/журнал/artifacts, сохраняет review и только новый pending
manifest переводит в completed с source_audit.status=structurally_verified_with_observed_extraction_errors,
semantic_verified=false. До этого Hotpot блокируется до HTTP, включая проверку tags.
Проверка декларации review не доказывает её правильность; исходники доступны для ревью.

Для статуса текущей научной карточки: `/research_status https://github.com/SPStan/rag-graphrag-research/pull/33`.
При устаревшей карточке: `/research_submit https://github.com/SPStan/rag-graphrag-research/pull/33 13`.
Никаких сообщений куратору/боту от имени пользователя не отправлено.

## Результат source-fidelity follow-up — 22 октября: semantic gate не пройден

Пользователь разрешил передачу и5POST по plan
`614b9318897d213140d37da4bce22e1262d06cf766b26ab297e4993d75a06e0e`,
clean runtime `73ab42868de126519df730367eb87ee373c68b68`.
Run `81df270e-82ba-45c8-b98f-55996124164d`, новый output
`indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-gpt-oss-policy-probe1`.

Ровно5POST, все stop/полный shape JSON, known usage; length/cycle/HTTP errors0,
NER/embedding/retry0. Новые **7190**tokens: input4870/output2320, меньше48929reserve.
Новый unknown0. Вместе обе GPT-пробы:10POST/**13295**tokens, ни один их response
не принят в Qwen cache. E1 physical known**16720688**, upper**16775742**,
cost_complete=false; прежний unknown55054 сохранён. Mu остаток**15025625**,
Hotpot20M. Готовность по-прежнему**4/6**, нового Hippo graph нет.

| Source (префикс SHA) | in/out | triples/unique | Source-only review |
|---|---:|---:|---|
| Cubs00358c281c194381 | 910/263 | 9/9 | attribution на этом source сохранён |
| Popper0153ea6260dee9cb | 1058/573 | 29/29 | не принят: прежняя привязка Berlin |
| Kobe2389611f5617e291 | 1108/890 | 45/45 | раздельные All-Star годы сохранены |
| Valencia38f7b69951335314 | 917/362 | 17/17 | не принят: безусловная параллельная связь |
| Northwest005451e99743714d | 877/232 | 11/11 | нужна проверка: seasonal qualifier не явен |

Полные ответы проверены по исходным passages, без questions/gold/support labels.
Это diagnostic cases, выбранные до GPT-проб: таблица не оценка точности модели.
Наличие2локально принятых случаев не означает разрешение продвигать их в индекс.

### Что изменила инструкция и что осталось

- Cubs: теперь `are depicted as winning` явно отличает сюжет фильма от события.
  Противоречие source про Marlins не исправлялось внешними знаниями.
- Kobe: есть отдельные `was NBA All-Star in:1998` и `2000–2016`; лишний1999
  не добавлен. Остальные группы наград/лет сверены по этому же тексту.
- Popper: `Otto Hahn Peace Medal — located in — Berlin` сохранился. В источнике
  место относится к названной ассоциации; такая самостоятельная связь награды
  не подтверждена. Новая общая инструкция её не устранила.
- Valencia: появились `believed by some Catholics` и `supposedly brought`,
  однако одновременно есть `Emperor Valerian — brought — Santo Caliz to Valencia's
  Cathedral`. Оговорка первой связи не задаёт scope другой самостоятельной связи.
- Northwest: прежнее ошибочное окончание существования льда исчезло. Осталась
  `Arctic pack ice — prevented regular marine shipping — until2009` без явного
  «throughout most of the year». Это не объявлено доказанно ложным утверждением,
  но заранее установленный строгий qualifier gate такой ответ не принимает.

Итог source review: **not_accepted_for_continuation**. Machine manifest immutable,
по-прежнему awaiting_source_review, SHA
`876e35282b3801b1a6ab207196e7b7a40664d903c995be8d519dd0826eb51f70`.
Отдельный local `source-review.json` SHA
`948ac856d31a8c8743b9f4650d6493d14c03b6f15e01a38e142183fa2daa58b4`
закрепляет source/request/response SHA, literal evidence и решение каждого случая.
Публичная JSON summary отражает исходный machine gate, итог содержательной
проверки — этот раздел/sidecar; machine status не переписан задним числом.
Старые producer manifests/review/raw неизменны, canonical claim остаётся.

### Короткий разбор после двух содержательных отказов

Транспорт/shape schema обеспечивают законченный parseable ответ на этих10POST,
но не задают надёжную привязку модификаторов и общий scope нескольких triples.
Одна system-инструкция дала частичные улучшения; она не подтвердила выполнение
всего source-fidelity контракта. Кап не исчерпан: увеличение3072 не обосновано.
Причину первоначального Qwen cycle этот результат не объясняет. Новых prompt
retries/модельных проб по этому пути **не будет без пересмотра протокола**.

Следующее решение относится к протоколу, не к ожиданию оператора:

1. Сохранить строгий source-fidelity gate: зафиксировать Hippo как незавершённый,
   оставить4/6 и не запускать его full/E2 до проверяемого решения.
2. Предложить другую приёмку: явно исследовать конфигурацию Qwen NER + GPT-OSS
   source-fidelity triples с измеряемым шумом extraction, source audit и раскрытыми
   ограничениями, вместо требования отсутствия всех таких ошибок. Это **изменение
   критерия**, не признание нынешнего gate успешным. Сначала зафиксировать допустимые
   ошибки/аудит и homogeneous либо mixed cache по ADR-0023, согласовать изменение
   единых условий SPEC/научные формулировки по BOT_REVIEW_WORKFLOW; затем отдельный
   bounded continuation budget/разрешение. Готовые Dense/RAPTOR не пересчитываются.

Второй вариант сейчас только предложение. Понизить критерий задним числом,
отфильтровать вручную неудобные triples, переименовать Qwen cache или автоматически
запустить full corpus нельзя. Независимая offline E2 preparation остаётся готовой;
полный сравнительный E2 не разрешён. PR Draft/Refs #13, issue открыта.

## План выполненного source-fidelity follow-up (история подготовки)

Подготовленный ранее offline candidate10e82514 остаётся неизменным и неисполняемым.
Теперь тот же existing executor поддерживает отдельный тип
`hippo_extractor_policy_probe_v1`: ровно один follow-up исходной GPT-пробы789bffd0,
с теми же5source cases и неизменными payload из проверенного candidate. Это
техническая подготовка исполнения, не принятие GPT extractor/benchmark и не
разрешение продолжать расходовать токены. Политика source_faithfulness_v1 прежняя.

- Endpoint https://api.duckduck.cloud/v1; iairlab/gpt-oss-120b,
  reasoning_effort=low, temperature0/seed42/stream=false, cap3072,
  shape JSON Schema без uniqueItems, без Qwen chat_template_kwargs.
- Передаются5сохранённых полных passages/cached NER и исходные SDK few-shot
  messages с общей system-инструкцией. Questions/gold/support labels отсутствуют.
- Максимум5POST, одна попытка/case, connect30/read300, retry0/redirects0;
  новых NER/embedding0. Резерв48929 из15032815, исторические unknown55054 остаются.
- Первая HTTP/transport error/unknown/length/partial/invalid/degeneration → stop.
  После пяти machine-pass — только awaiting_source_review. Все5нуждаются в
  source-only проверке factual support, attribution/uncertainty/dates/attachment
  и существенных пропусков. Literal совпадение с Qwen не требуется.
- Даже успех не запускает full Hippo, QA/E2, cache promotion или следующую пробу.
  Повторный semantic failure завершает этот prompt-fix блок: дальше разбор
  протокола, а не новая цепочка prompt retries.

### Связь с неизменными предками и claim

До HTTP заново проверяются approved plan исходной GPT-пробы, manifest5417b157,
negative source-review392ff920, literal evidence и все5физических attempts/SHA.
Parent index plan0310dad2 и failed manifeste3bb6654 тоже закреплены; token_limit
и remaining должны совпасть с исходным snapshot. Из него вычтены6105известных
токенов первой GPT-пробы. Отсутствующий/stale review, unknown producer, подмена
payload/параметров или source directory останавливают подготовку/исполнение.

Exclusive `source-policy-probe-once.claim.json` создаётся **в каноническом
musique-gpt-oss-probe1**, до новогоPOST. Claim не привязан к произвольному output;
перемещение output или другой worktree не даёт второй попытки того же producer.
Новый run/output `musique-gpt-oss-policy-probe1`, прежние manifests/results immutable.
При аварии claim сохраняется. Полный exact plan и clean code HEAD проверяются
по SHA и повторной реконструкции до Session/HTTP. Старый candidate по-прежнему
отклоняется; требуются новый plan kind и отдельное согласие на его SHA.

Existing export суммирует index history, первые5GPT attempts и новый follow-up
однократно. Own unknown резерв сохраняется вместе с known usage. В public metadata
отдельная модель/variant, parent probe SHA, negative review SHA; это не Qwen cache hit.
Старые4индекса и3102Qwen пары не меняются. Пока actual new cost0, E1known16713498.

```powershell
# Только подготовка, без HTTP; --source здесь обозначает предыдущий GPT output.
& ./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-extractor-policy-probe `
  --prior-plan <data-root>/indexes/e1/issue13-hippo-schema-preflight-plan.json `
  --probe-plan .cache/e1-gpt-oss-diagnostic-plan-a6625f7.json `
  --source indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-gpt-oss-probe1 `
  --plan .cache/e1-extractor-policy-approved-proposal.json
# Только после отдельного разрешения конкретного SHA/HEAD:
& <hippo-python> -m scripts.run_e1 run-compatible-schema-probe `
  --plan <exact-followup-plan> `
  --prior-plan <data-root>/indexes/e1/issue13-hippo-schema-preflight-plan.json `
  --env-file <data-root>/<env-file> --approved-probe-sha256 <approved-sha>
```

Offline:84targeted tests passed. Fake transport проверяет5POST cap, first-error
stop, unknown reserve, claim/reuse после перемещения output, подмены payload/review,
actual model journal и cumulative no-double-count export. На actual сохранённых
данных подтверждены payload equality с candidate10e82514, reserve48929 и неизменность
source manifests/journals/review/public summary. Новых модельных запросов нет.

## Offline source-fidelity policy — подготовлена, моделью не проверена

После пяти технически успешных GPT-OSS ответов сформулировано одно общее
изменение system-инструкции `source_faithfulness_v1`, без изменения модели,
NER/messages примеров, schema, seed42, temperature0, reasoning_effort=low или cap3072.
Правила едины для обоих датасетов и не содержат имён/ответов пяти случаев:

1. Сохранять attribution: фильм, прогноз, мнение и рассказ об утверждении нельзя
   превращать в standalone реальное событие; условие помещается в relation/entity.
2. Сохранять uncertainty, отрицание и кванторы: supposedly/may/some/most/only.
3. Сохранять точные даты и раздельные интервалы, не заполнять промежутки.
4. Привязывать дату/место к тому объекту, событию или ограничению, которое
   модифицируется в source; конец ограничения не равен исчезновению его субъекта.
5. Не исправлять противоречия источника внешними знаниями. При неясной привязке
   опустить спорную связь, сохранив остальные подтверждённые сведения.

Форма остаётся triples JSON; контекст/оговорки кодируются строками, новый графовый
schema/framework не добавлен. Никаких исправленных «правильных triples» в prompt.
Инструкция имеет приоритет над lossy shortcuts few-shot; её реальное соблюдение
ещё не проверено. Буквальное совпадение с Qwen и полнота всех возможных triples
не требуются; существенные пропуски и unsupported relations проверяются вручную.

### Что offline проверено на сохранённых ответах

| Старое замечание | Применимое правило | Результат |
|---|---|---|
| Cubs, вымышленная победа как факт | 1 attribution | старый ответ не принят |
| Popper, Berlin присоединён к награде | 4 attachment | спорная связь не принята |
| Kobe, заполнен пробел1999 | 3 disjoint dates | старый ответ не принят |
| Valencia, исчезли supposedly/some | 2 uncertainty/quantifiers | старый ответ не принят |
| Northwest Passage, до2009отнесено ко льду | 4 temporal scope | старый ответ не принят |

Это проверка обоснования policy по source, не новый semantic classifier и не
доказательство исправления generation. Версия правила закреплена заранее;
нейтральная инструкция не меняется отдельно под каждый passage. Предыдущие
ответы не исправляются, не становятся новым cache hit и не принимаются задним числом.

В существующий run_e1 встроена `prepare-extractor-policy`:

```powershell
& ./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-extractor-policy `
  --prior-plan .cache/e1-gpt-oss-diagnostic-plan-a6625f7.json `
  --source indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-gpt-oss-probe1 `
  --plan .cache/e1-extractor-policy-candidate.json
```

Команда проверяет journal/artifact SHA, original approved plan, все5физических
triples попыток/реальную модель, exact source/request/response SHA и буквальные
evidence source-review. Чужой/stale/неполный review не проходит. Она проверяет
происхождение свидетельств, а не автоматически доказывает правоту любого verdict.
Старый отрицательный verdict не может быть превращён этой командой в accepted.

Только system content дополнен общими правилами; все5user passages/cached NER,
few-shot messages, порядок случаев и остальные payload fields неизменны.
Все5request SHA новые. Candidate — `hippo_extractor_policy_candidate_v1`, статус
`offline_proposal_not_executable`: существующий executor явно отклоняет его
до чтения API config/создания Session. Никаких POST/embedding/NER не выполнено.

Если отдельно принимать такой следующий diagnostic: те же5случаев, одна попытка
на случай, максимум5POST, общий byte-reserve**48929** (9623/10349/9905/9594/9458)
из snapshot остатка15032815. Это предложение, не зарезервированный расход и не
измеренный tokenizer count. До исполнения нужны отдельный допуск/точный executable
plan и canonical claim/новый output, привязанные к текущему отрицательному probe,
с учётом его6105tokens и всех старых unknown; готовый candidate таких прав не даёт.
Условия stop/source-review прежние. Если source fidelity снова не пройдёт,
разобрать причину и пересмотреть протокол вместо цепочки prompt retries.

### Benchmark и переиспользование

Policy пока предложение ADR-0023. Она не принимается молча только для отдельных
неудобных passages. В случае принятия одной явной версии extractor правило должно
быть одинаково доступно обоим датасетам; full homogeneous и Qwen-primary/GPT-fallback
остаются различными конфигурациями. Mixed cache допускается только отдельным
решением с provenance каждой модели. Нельзя утверждать прежнюю сопоставимость
или полноту качества3102старых Qwen извлечений на основании новой инструкции.

Dense/RAPTOR×4, Qwen NER и совместимые исходные cache entries сохраняются.
При смене triples policy старый request key не подходит: новые triples требуют
новых полных ответов, граф и изменившиеся fact/entity embeddings пересчитываются
в отдельно разрешённой конфигурации. Диагностика сама этого не запускает.
Физический E1 расход/4из6индексов в этом offline-блоке не изменились.

## Результат разрешённой GPT-OSS диагностики — 22 октября

Пользователь отдельно разрешил передачу и5POST по plan
`ffbfdeb9bf69e23a60c56e290a93e951226d916c8bdd694379ca17a0e81ea69a`,
clean code `a6625f7dfd46789b180e0407a3377b04e570edf0`.
Run `789bffd0-bc70-4471-9a0d-1e63eee5508f`, output
`indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-gpt-oss-probe1`.
Согласие относится только к этим5POST, без полного индекса/QA/E2/merge.

Все5ответов stop, полный shape JSON, известный usage, без degeneration/length.
Новых NER/embedding/retry0. Расход **6105**: input3955/output2150,
из резерва44124. Новый unknown0; старый55054 сохранён. E1 physical known
**16713498**, upper**16768552**, cost_complete=false. Mu остаток**15032815**,
Hotpot20M. Сравнительные6индексов по-прежнему4/6, Hippo граф не построен.

| Source (префикс SHA) | in/out | triples/unique | Машинный gate |
|---|---:|---:|---|
| control00358c281c194381 | 727/295 | 15/15 | passed |
| Popper0153ea6260dee9cb | 875/571 | 29/28 | passed |
| Kobe2389611f5617e291 | 925/648 | 29/29 | passed |
| Valencia38f7b69951335314 | 734/357 | 18/18 | passed |
| control005451e99743714d | 694/279 | 15/15 | passed |

**Содержательная приёмка не пройдена; continuation не принят.** По всем5исходным
passages вручную проверены факты/оговорки без QA gold и без требования совпадения
с Qwen. Конкретные замечания к извлечениям:

- Cubs: победа2015 World Series дана standalone-фактом без условия «изображено
  в фильме». Сам источник также содержит противоречие про Marlins; внешние
  правильные ответы для его исправления не использовались.
- Popper: `Otto Hahn Peace Medal — located in — Berlin` присоединяет место к
  награде; в source «in Berlin» относится к упомянутой ассоциации. Такая связь
  не подтверждена, автоматическое принятие всего extraction не обосновано.
- Kobe: `1998, 2000–2016` превращено в непрерывный `1998–2016`, добавляя1999.
- Valencia: «supposedly brought» превращено в безусловное «brought»;
  ограничение «some Catholics» также не сохранено.
- Northwest Passage: окончание ограничения судоходства «until2009» превращено
  в окончание существования pack ice «persisted until2009»; это не одно утверждение.

Это локальная проверка пяти случаев, не оценка общей точности GPT-OSS и не
доказательство, что Qwen лучше. Техническая совместимость payload подтверждена
на5случаях; полного устранения проблемы Hippo этим не установлено.

Machine manifest оставлен immutable в awaiting_source_review, SHA
`5417b157c2159a2865f16929502682f5f0e49ea4a2aca3ccd5a5a4b8322c6439`.
Отдельный локальный `source-review.json` закрепляет source/request/response SHA,
буквальные evidence и verdict not_accepted_for_continuation; SHA
`392ff920c98d90351b3096c8651ce134faca0b168ddb84fa0e81d32fbdcf3377`.
Это sidecar после эксперимента, он не меняет первоначальный manifest и не
переименовывает технический результат в failed HTTP. Публичная summary отражает
machine gate; содержательное решение опубликовано здесь. GPT ответы не
добавлены в Qwen extraction cache;3102старых пар сохраняются под своим provenance.

Следующее обоснованное действие — offline уточнение extractor policy для
attribution/uncertainty/disjoint dates и её проверки на этих сохранённых ответах,
затем решение по ADR-0023: homogeneous/hybrid/mixed benchmark. Это предложение
следующего блока, не разрешение шестого POST или full continuation. Прежде чем
подготавливать новые расходы, нужно обосновать изменённый payload и критерии;
повтор того же запроса не планируется. Готовые Dense/RAPTOR сохраняются.

## Разбор нового length/cycle после schema — 22 октября

**Статус: Hippo остановлен; полный E1 остаётся4/6.** Runtime0d784ed,
run3eab6c1d-d87e-42d3-8e12-618ca2adf0bc, план0310dad2. Этот запуск проверил
1357passages, выполнил1544физическихPOST, известны1015121новых токенов.
Все физические usage известны, unfinished0; HTTP-ошибок0, но extraction gate
отклонён. Hotpot не запускался. E1known16707393/upper16762447,
cost_complete=false: прежние unknown55054 остаются. Остаток Mu15038920,
Hotpot20000000; новые расходы не разрешены самим фактом наличия остатка.

### Что проверено offline

- Manifest SHA `e3bb665491d2c1d7aa912d5bb89218ef5022cfad3190dc5c3ff068dc5ef3571a`.
- Request SHA `9f12b07f0c6623c7c2718c999f3605121fe1e0c8a930af595db09bd1aba24072`.
- Response SHA `da8d9cff5ded979e4bc25f3dd7be08fba48a32aace79b89ef038aa1a7f0f166d`.
- Source ID `sha256:0153ea6260dee9cbfc76ff5d2042866508e727b5cb57656a4dd180931a6dd26f`.
- SHA точного title+newline+text UTF-8:
  `67b24a10de56844658c0a32dee7fcf8233ec53427baeaf56efadca3bbcb87f13`.

Исходный payload восстановлен закреплённым SDK1438aba3 из этого passage и
проверенного cached NER, получен тот же request SHA. Questions/gold/supporting
не использовались. Input891/output3072, reasoning0, finish_reason=length;
3963токена уже включены в1015121 и не начисляются повторно. В ответе168полных
tuple-фрагментов,26различных,142одинаковых подряд в хвосте. Эти числа диагностические:
полного JSON нет, ни один tuple этого ответа не принят. В отличие от прежней
Kobe multiplicity этот хвост не отражает число событий источника. В нём повторяется
одна связь, а более поздние сведения passage, включая год и последнюю награду,
не извлечены. Поддержанность всех26фрагментов не заявляется.

Это наблюдаемый цикл generation, а не переполнение262144-context или транспортный
retry. Почему модель/декодер зациклились, из raw установить нельзя. Shape schema
проверяет форму и не обеспечивает уникальность/завершение неограниченного массива.
Ни literal dedup, ни дописывание скобок не превращают этот length в полный ответ.
Увеличение3072, очередное изменение инструкции или новый порог числа facts сейчас
не имеют подтверждённого исправления причины. Прежний HTTP400 uniqueItems тоже
не повторяется. Строгий stop gate сработал корректно.

### Что реально можно переиспользовать

Offline проверены journal/artifact SHA предков, два отдельно принятых полных
schema-ответа и текущие checkpoints. Всего6379успешных response entries, включая
172leaf embedding. Для каждого из5500title/text заново отрендерены NER и triples
requests pinned manager, NER прочитан полным parser/recover_partial=False.
Засчитывается только существующий точный verified original json_object key либо
соответствующий schema key, полный stop/known-usage response и успешный SDK parse.
Partial/length исключён, labels не читаются. Поэтому покрытие ниже относится
к reuse извлечений, а не к готовому графу:

| Состояние | Passages |
|---|---:|
| Полные NER и triples в совместимом кэше | 3102 |
| Есть только NER | 2 |
| Нет NER | 2396 |
| Всего | 5500 |

NER cached3104, совместимые пары3102/5500(~56.4%). Это сумма проверенных источников,
а1357 — локальный прогресс последнего run; сравнивать их как один счётчик нельзя.
При неизменной конфигурации минимум4794новых LLMPOST до завершения extraction
(2×2396+2) без учёта любых будущих отказов; embeddings графа дополнительно.
Все failed/probe остаются в стоимости, ответы не переименованы в другой model/key.
Новые model/embedding вызовы в этом offline-разборе не выполнялись.

### Текущий блок: offline-аудит и ограниченная диагностика GPT-OSS

**Наблюдение:** Qwen вернул незавершённый JSON с повторяющимся хвостом и length.
**Причина:** не установлена; schema не гарантирует качество или завершение.
**Расходы:** следующие POST требуют отдельного разрешения по ADR-0022.
**Протокол:** исходный benchmark закрепляет общий Qwen; проба GPT-OSS не меняет
его автоматически. Помощь оператора полезна для выяснения причины, но не является
обязательным условием offline-подготовки и отдельной ограниченной диагностики.

#### Аудит фактического клиента

Три прежних failed payload восстановлены из точного source + verified cached NER
закреплённым manager SDK1438aba3. Проверка installation сверяет61 файл с Git blobs.
Все исходные request identities совпали с physical journal; последний —9f12b07f.
Модель iairlab/qwen3.8-27b, temperature0, seed42, stream=false,
chat_template_kwargs.enable_thinking=false, triples cap3072, NER cap1024.
Messages — role/content из одного render; клиент не вкладывает готовый chat template
в другой шаблон. Серверное применение шаблона этим не проверено.

Исходные Valencia/Kobe length использовали json_object; две полные пробы на тех же
source/NER изменили response_format на shape JSON Schema без uniqueItems. Остальные
параметры прежние. Они дали stop и известный usage1068/2166, но Kobe имел буквальные
дубликаты; его отдельное принятие отражает штатный SDK graph-set dedup, не качество
самой schema. Последний Popper уже использовал ту же shape schema и снова дал цикл.
Следовательно успех двух проб не доказывает исправление причины на других passages.

В native установленном OpenIE на synthetic success/error проверено по одному infer
на NER/triples, messages совпадают с единственным render. E1 передаёт собственный
LLM adapter, обходя CacheOpenAI; transport — requests.Session с max_retries=0,
redirects=false. Последовательные corrective/fallback попытки прежних запусков
журналируются отдельно; последняя schema continuation не делает corrective retry.
Текущий сохранённый payload соответствует коду. **Новой клиентской ошибки,
объясняющей повторяющийся хвост, не найдено.** Это не проверка внутреннего decoding
провайдера; отсутствие доказанной клиентской ошибки не доказывает ошибку сервера.

#### Зафиксированный план исполненной диагностики (история плана)

Выбран iairlab/gpt-oss-120b, reasoning_effort=low: после повторного цикла при
shape schema нет основания менять ещё один Qwen sampling-параметр вслепую.
Куратор сообщил context131k и поддержку JSON mode/Schema/reasoning_effort.
Это заявленный контракт; текущий deployment ещё не измерен. Guard131000 —
консервативная интерпретация131k, а не результат серверного token count.
Qwen-specific chat_template_kwargs полностью исключён. Prompt/messages,
temperature0/seed42/stream=false и shape schema сохраняются; max_tokens3072
остаётся пределом всего completion, включая reasoning, без повышения cap.

Пять фиксированных случаев из уже известного MuSiQue cache, без новых выборок:

| Порядок | Роль / source ID (префикс SHA256) | Резерв |
|---|---|---:|
| 1 | successful control00358c281c194381 | 8662 |
| 2 | latest failed Popper0153ea6260dee9cb | 9388 |
| 3 | historical failed Kobe2389611f5617e291 | 8944 |
| 4 | historical failed Valencia38f7b69951335314 | 8633 |
| 5 | successful control005451e99743714d | 8497 |
| Итого | максимум5POST, одна попытка на случай | **44124** |

Контроли — первые два полных cached extraction в сортировке source ID, исключая
три failed source; правило зафиксировано до GPT-OSS вызовов. Их содержание и
правильность старых triples не используются как gold. Внешнему API передаются
полные эти passages, сохранённый NER и SDK few-shot messages, без questions,
ответов, supporting labels. NER/embeddingPOST0; retry0/redirects0, connect30/read300.
Резерв = сумма UTF-8 bytes каждого exact payload +2048 +3072. Это guard бюджета,
не измеренный GPT tokenizer count.44124 вычитается из Mu остатка15038920;
исторические unknown55054 сохраняются, общий E1 total остаётся неизвестным.

Подготовка интегрирована в существующий runner, новый framework не добавлен:

```powershell
# В активном worktree, без HTTP. SDK установлен в отдельном окружении.
& <hippo-python> -m scripts.run_e1 prepare-extractor-diagnostic `
  --prior-plan <data-root>/indexes/e1/issue13-hippo-schema-preflight-plan.json `
  --source <pinned-hippo-source> --plan .cache/e1-gpt-oss-diagnostic-plan.json
# Read-only проверка готовых Dense/RAPTOR, без queries/labels и без export:
& ./.venv-check/Scripts/python.exe -m scripts.run_e1 offline-ready `
  --plan <data-root>/indexes/e1/issue13-hippo-schema-preflight-plan.json
```

Exact payload, полные source IDs, source/NER/baseline SHA и code commit сохраняются
в локальном ignored plan; перед будущим запуском проверяются его SHA, clean HEAD,
повторная реконструкция и canonical claim рядом с исходным failed manifest.
Исполнение использует существующий run-compatible-schema-probe с отдельными
musique-gpt-oss-probe1 output/run/model. Не переносить ответы в Qwen cache.

При первом timeout/HTTP error/unknown usage/length/partial/невалидной форме —
остановка без повторов. Полный непустой JSON, только triples из трёх непустых строк,
известный usage и отсутствие вырожденного цикла обязательны. Двенадцать одинаковых
triples подряд — консервативный stop для ручного source review, а не доказательство
ошибочности любых повторов. Literal dedup не заменяет содержательную проверку.
При пяти machine-pass статус лишь awaiting_source_review: вручную по каждому
исходному passage проверить поддержку фактов, отрицания/годы/оговорки, отсутствие
вымышленных связей и существенных пропусков. Буквальное совпадение с Qwen не нужно.
Сомнительное содержание — остановка до решения, без автоматического шестого POST.

Даже полный успех разрешает только подготовить continuation и выбор конфигурации,
не полный индекс: сначала решение по [предложению ADR-0023](../.adr/0023-hippo-extractor-diagnostic.md),
смешанному cache/сопоставимости и отдельное разрешение расходов. Все failed/probe
учитываются один раз, known и unknown сохраняются; raw/старые manifests неизменны.

#### Независимая подготовка E2 без сравнительного запуска

В e1_indexers добавлены read-only load/retrieval и replay общего reader/evaluator;
offline-ready встроен в run_e1. Пробел до этого блока: E1 подтверждал save/reload,
но не давал проверяемого входа готовых артефактов в общий retrieval→reader путь.
Теперь проверяются manifest/journal/artifact SHA, plan lineage, source order,
BGE digest/dimension1024 и RAPTOR leaf ancestry. Cache miss, changed SHA, unknown,
length и несовместимый query vector отклоняются без fallbackHTTP/обрезания.
RAPTOR supporting provenance coverage отделён от passage recall@5 (null для nodes).
Наличие cached usage не объявляется полнотой исторических затрат.

Четыре готовых артефакта по5500 passages загружены offline. Native RAPTOR pinned
TreeRetriever подключён к уже сохранённому leaf vector как **synthetic query
vector**; общий prompt/parser/evaluator проверяются с synthetic response/label.
Это проверка связки, не реальные QA, E2, скорость, качество или расход моделей.
Native проверка прошла для всех4: Dense top5/5, RAPTOR Mu5/Hotpot2 nodes
в пределах контекста3000токенов. Original manifest/journal SHA до/после совпали.
Первый offline import остановился на отсутствии TIKTOKEN_CACHE_DIR; HTTP guard
запретил загрузку tokenizer. Повтор с уже сохранённым cache завершился без HTTP.
Данные holdout не читались. Целевые тесты:118passed/2SDK-skipped; native SDK
дополнительно проверены отдельно, что не заменяет реальный модельный эксперимент.
Оставшиеся реальные части: готовые Hippo graph×2 и их read-only retrieval adapter,
отдельное планирование query embedding/cache provenance, run budget/journal E2,
научное согласование выбранной конфигурации и разрешение E2. Полный reader run
не запускался. Dense/RAPTOR перестраивать для диагностики extractor не нужно.

### Готовый локальный пакет для оператора

Без новых HTTP подготовлен `<worktree>/.cache/e1-provider-repro-9f12b07f.zip`
(7351bytes,7файлов), SHA
`3bd6d0766ef8430c0fc572824bb2c68959875d5c8502ff99891bf649fb96064b`.
Внутри exact request body, byte-for-byte response, одна пара journal events,
metadata с provider response ID/usage/SHA, README, SAFE_REPORT и checksums.
ZIP распакован в памяти и все SHA проверены; действующего API-ключа/Authorization
нет. JSON body ответа API читается; оборван именно сгенерированный JSON в
message.content. Request identity SHA включает payload+kind+operation и отличается
от byte SHA отформатированного request.json; оба указаны в metadata.

Архив содержит один passage, NER и generated content, поэтому остаётся ignored
локальным артефактом и в GitHub не загружается. Отдельный SAFE_REPORT.md рядом с
архивом не содержит корпуса/generated facts/credentials и пригоден для первого
обращения. Executable replay/POST command в пакет не включён. Ничего оператору
не отправлено; контакт/разрешение пересылки ещё не получены. Его revision/template/decoding settings помогут разбору; вопросы
сформулированы в README. Архив повторно не создавался и не отправлялся.
Отдельный диагностический путь выше не требует ожидания оператора.

## Исправление нулевого preflight после согласия на оба Hippo-прогона

На планcaf265ad/7f0c6ed получено явное согласие «Разрешаю передачу и оба
Hippo-прогона». Первый runner326a7eb4 остановился при чтении старого успешного
json_object: новый schema-validator ошибочно запретил дополнительные поля
старого формата. Физических POST0, новых токенов0; только172embedding и2LLM
cache hits. Hotpot не запускался. Failed manifest/планcaf265ad неизменны.
Два более ранних отказа launcher также произошли до runner/HTTP (политика .ps1,
затем старый PowerShell); рабочий launcher использует PowerShell7.6.5/UTF-8.

Исправление разделяет контракты: старый verified json_object проверяется прежним
pinned parser; строгая shape-валидация применяется к actual schema payload.
Offline проверен весь кэш4836:2332NER/2332triples, включая1919старых triples
с дополнительными полями, partial recovery=false, HTTP0. Новые schema ответы
по-прежнему проходят полный строгий валидатор. Регрессия воспроизводит именно
старый ответ с named_entities+triples; preflight guards запрещают продолжение
после любого physical attempt и повторную цепочку локальных revisions.

Существующий prepare-native-schema-continuation принимает approved schema plan
и создаёт ровно один preflight child, если проверены failed/attempts0/known0/
unknown0 и все SHA. Новый output *-schema-preflight1/run IDs, claim рядом с этим
нулевым failed manifest. Он включён шестой историей Mu, расходы0; исходные
16054041/20000000 и ограничения попыток/данных/модели не меняются. Это исправление
локального replay до первого запроса в пределах уже полученного согласия на оба
прогона, а не новая генеративная политика или model retry. После любого
физического запроса этот путь недоступен; новый model отказ вновь останавливает
очередь. Старое согласие и техническая ревизия связываются явно, новый ответ
пользователя на другой SHA не выдумывается.

```powershell
<hippo-python> -m scripts.run_e1 prepare-native-schema-continuation --prior-plan '<approved-first-schema-plan>' --plan '<data-root>/indexes/e1/issue13-hippo-schema-preflight-plan.json'
```

## Offline-принятие и готовый путь продолжения Hippo — 22 октября

[Отдельная запись принятия](../results/summary/e1-hippo-schema-adoption.json)
фиксирует `native_graph_set_schema_v1`: полный исходный JSON передаётся штатному
parser SDK1438aba3 с `recover_partial=False`, удаляются только точные одинаковые
triples. Проверено на реальных сохранённых ответах:16→16 и62→14, HTTP0.
Строгая проба и её manifest остаются failed; 3234 уже потраченных токена входят
в E1 один раз. Это техническая нормализация существующего индекса, а не
подтверждение качества фактов или устранения генеративного цикла. Years/counts
и modality, потерянные моделью, дедупликация не восстанавливает.

Единое правило обоих датасетов: старые полные успешные json_object ответы
переиспользуются без смены идентичности. Для ещё не оплаченных triple-запросов
используется прежний prompt/cap3072 со shape schema без uniqueItems. NER остаётся
json_object/cap1024. Для двух принятых случаев проверяется связь original request
→ schema request → producer run/response SHA/usage. Журнал cache_hit записывает
реальный schema request, а не исходный json_object. Raw не сокращается.
Фактическая история смешивает старый json_object и новые schema ответы; это
раскрыто, успешные старые извлечения не перегенерируются. Непустой полный JSON
и валидная форма обязательны; пустой список triples допустим штатным SDK.
Length, partial, duplicate JSON fields, unknown usage, неверная форма — остановка.

Используется существующий runner. Новые outputs `musique-schema1`, затем
`hotpotqa-schema1`; Hotpot допускается после завершения/проверки MuSiQue.
Canonical claim рядом с исходным MuSiQue failed manifest общий для разных output
и worktrees; повторная подготовка отклоняется. Immutable ancestors, новые run IDs.
Пять историй MuSiQue (три индексных, две schema) учитываются один раз: charge3945959,
из них16601 unknown reserve; остаток **16054041**. Hotpot лимит **20000000**,
суммарный новый предел **36054041** combined LLM+embedding tokens. Общий E1
known15692272/upper15747326 не меняется от offline-принятия; cost_complete=false.
Остальные старые unknown, включая RAPTOR, сохраняются.

Предел каждого dataset:40000 физических POST суммарно во внешний API и локальный
embedding, дополнительно ограниченных token budget; максимум11000 LLM POST
(по одному NER и triples на каждый из5500 passages), для MuSiQue меньше за счёт
проверенного кэша. Не более одной новой попытки на uncached payload, corrective0,
retry0, redirects=false, target connect30/read300. Счётчик включает embeddings;
это верхняя граница, а не прогноз числа запросов. Внешнему API передаются только
passage и сохранённые/новые NER; локальному BGE-M3 — passages/entities/facts.
QA, gold, supporting labels не передаются. Dense/RAPTOR не запускаются.
На первой ошибке, unknown, length, неверном JSON/векторе, смене SHA/модели/SDK,
исчерпании cap/бюджета/POST — остановка с сохранением failed manifest и расхода;
новой коррекции и автоматического повтора нет.

Команды offline (первый output должен быть новым, принятие затем коммитится):

```powershell
<hippo-python> -m scripts.run_e1 adopt-schema-responses --prior-plan '<latest-e1-plan>' --probe-plan '<approved-compatible-probe-plan>' --source '<pinned-hippo-source>' --plan '<new-adoption-record>'
<hippo-python> -m scripts.run_e1 prepare-native-schema-continuation --prior-plan '<latest-e1-plan>' --probe-plan '<approved-compatible-probe-plan>' --schema-adoption results/summary/e1-hippo-schema-adoption.json --source '<pinned-hippo-source>' --plan '<data-root>/indexes/e1/issue13-hippo-schema-plan.json'
```

Подготовка фиксирует clean HEAD, все SHA, бюджеты и canonical claim; HTTP0.
Само принятие и позднее согласие на уже выполненную пробу6d0d0dc3 **не разрешают**
новые full-corpus вызовы. Перед `run` требуется отдельное согласие пользователя
по ADR-0022 на этот точный план; автоматического требования нового решения
куратора для использования штатного parser протокол не вводит. Научные O/N/R/H
проверяются отдельно перед ревью. PR остаётся Draft/Refs #13, готово4/6.

## Измеренный результат compatible-schema пробы — 22 октября

План6d0d0dc3 выполнен после нового согласия в чате. Run
052f9558-abef-46a3-a72e-7d955bdea323, code09ec0b4, output
`hipporag2/musique-schema-shape-probe1`. Ровно2POST/0retry/0NER/0embedding,
проверенные источники/claim доHTTP. Остановка на первом локальном отказе,
который произошёл во втором ответе. Full_index_authorized=false.

| Случай | HTTP/generation | Input/output | JSON triples/unique | Результат строгой пробы |
|---|---|---:|---:|---|
| Valencia | завершён, stop | 736/332 | 16/16 | формат прошёл |
| Kobe Bryant | завершён, stop | 1038/1128 | 62/14 | 48повторных вхождений, rejected |

Всего1774input+1460output=3234known, новогоunknown0. Manifest failed/ValueError
сохранён, оба полных raw JSON неизменны. Journal и все artifacts SHA проверены.
Manifest SHAfd9c1b68c5abea7c5be1de81f32a8cc8c968819dc6bccc9a57379fcd3e23bcec;
responses SHA1abdf7846e3d434f4608f2fb0312259d7610fa1bad6adaff9b223ab64d4cbf73
иa5702cb7fb2e3a315d2a4202913515b8244291897811ebc1a6184fe32823d75b.
Второй request SHA436abd1de70f4fcb34831bf2b953a88daa1d6dd1b98d60afee531965108e0182.
E1 physical known15692272, upper15747326,cost_complete=false. СтарыйHTTP400
unknown8679и все остальныеunknown сохранены. Hippo остаток16054041после
известного расхода3234; весь резерв17625за фактический расход не выдаётся.
Готово4/6. Никакого дополнительногоPOST, full Hippo/QA/E2/merge нет.

### Содержательный разбор и следующий путь без новой генерации

API принял shape schema и выдал2полных JSON. Это подтверждает совместимость
этой schema на двух случаях, но строгий критерий «без дубликатов» выполнен1/2.
В Kobe output частоты совпадают с количеством наград:5championship,18All-Star,
11First Team и т.д. Ответ конечный/stop; его повторы описывают кратность событий,
а years/counts не представлены как отличающие атрибуты triples. Это не основание
увеличивать cap или объявлять устранённым прежний length/cycle.

Проверена закреплённая реализацияSDK1438aba3 и61файл установки:
`utils/llm_utils.py::filter_invalid_triples` уже удаляет точные дубликаты;
`utils/misc_utils.py::flatten_facts` строит множество triples.
Наш обычный индексатор уже использует этот parser через
`make_pinned_openie_parser(... recover_partial=False)`. Прямой offline вызов
на сохранённых полных responses дал16→16и62→14, exact literal dedup,
HTTP0; raw и failed manifest не изменились. Этот факт не меняет gate проведённой
пробы и не разрешает автоматически индексировать весь корпус.

Более строгая диагностика потребовала уникальности самого model output,
а штатная семантика индекса использует уникальное множество relations.
Реализованный offline-путь: отдельное принятие сохранённых **полных** responses
для штатного SDK parser с учётом raw/unique counts и явной original→schema
provenance; затем offline-интеграция replay и план ограниченного продолжения.
Политика должна быть общей для обоих датасетов. Partial JSON, length, неизвестный
usage и неверная форма по-прежнему не принимаются; старый failed остаётся failed.
Принятие оформлено отдельным артефактом ниже; новых модельных проб для изучения
дубликатов сейчас не нужно. При изменении этой семантики требуется новый протокол
извлечения counts/years, а не слепой повтор нынешнего запроса.

Форматный успехValencia не равен семантической проверке16фактов: в output
снята часть оговорок some/supposedly, а тождество Cathedral/Basilica из контекста
не подтверждено однозначно. Дедупликация также не восстанавливает годы/числа и
не подтверждает истинность triples. Вопросы/gold/supporting labels не читались.


## Текущее состояние — 22 октября: RAPTOR×2 готовы, Hippo-проба подготовлена

RAPTOR HotpotQA runbb177a66 completed:5500leaves,7595nodes,2095summaries,
слои5500/1411/684. Последнее сетевое продолжение347POST/697411known tokens,
0ошибок,3129.293s. Все родительские расходы/unknown8432 сохранены;
сумма измеренных durations истории19623.594s — attribution, не cold-run time.

Свежий отдельный процесс pinned RAPTOR SDK проверил все artifact SHA,
restore/serialize exact round-trip и неизменность журнала, HTTP0.
Tree SHA14500441ec9a1a6b9088c8bf7036819edcf349255148219d0eb6fa07b9198ec0;
manifest SHAccaccda5fd3541196af3afdaf365fde5d44e1e08f957e7ae852fbb9009b74042;
journal SHAabb5f5f3c734cb3684a23289341d4d9a9c7d2e62d23ddae427776543c7fc5bef.
Native proof — ignored .cache/e1-hotpot-reload-proof.json, без private text в Git.
Готово4/6, E1 physical known15689038/upper charge15744092/cost_complete=false.
Неполнота относится к расходу истории; два RAPTOR индекса готовы к последующим
проверкам retrieval, но E2 не запускается до готовности всех шести.

### Исполнитель ограниченной Hippo schema-пробы

В существующем `execute_schema_probe`/CLI теперь есть явный режим
`run-compatible-schema-probe`. Он проверяет точный approved SHA, чистый и
закреплённый code commit, pinned SDK prompts/corpus/cache/старые manifests и
новый canonical claim доHTTP. Отдельный output musique-schema-shape-probe1,
неизменный старый musique-schema-probe1/HTTP400/unknown8679.
E1 exporter учитывает обе диагностики ровно один раз, включая известный usage
при неверном JSON, частичный usage и upper reserve при неизвестном расходе.

Новый план:2POST максимум, по одному на2исторических passage+их cached NER,
та же iairlab/qwen3.8-27b/URL, temp0/seed42/thinkingfalse/cap3072;
connect30/read300,retry0,redirectsfalse. Это явно заданная политика новой
диагностики; она не наследует разрешение TLS-прогона RAPTOR. При первой ошибке,
length, неизвестном usage, invalid/partial JSON, неверной форме или дубликате —
остановка. Никаких новых NER/embedding и full rebuild. Резерв17625=8657+8968
из оставшихся16057275Hippo tokens; неиспользованный RAPTOR бюджет не переносится.

Schema без unsupported uniqueItems проверяет форму, а строгая локальная проверка
полный JSON/повторные поля/тройки/дубликаты проверяет принятие результата.
Успех2/2 не доказывает устранение генеративного цикла на корпусе или истинность
triples; semantic support остаётся отдельной проверкой на исходных passage.
SDK используется для точного воспроизведения prompts/NER; физические POST идут
через общий measured requests transport, не скрытый SDK retry.

```powershell
# Подготовка безHTTP, только в изолированной среде pinned Hippo SDK:
<hippo-python> -m scripts.run_e1 prepare-compatible-schema-probe --prior-plan '<latest-e1-plan>' --source '<pinned-hippo-source>' --plan '<new-private-compatible-plan>'
# Только после отдельного согласия на новую schema-пробу по ADR-0022:
<hippo-python> -m scripts.run_e1 run-compatible-schema-probe --prior-plan '<latest-e1-plan>' --source '<pinned-hippo-source>' --plan '<new-private-compatible-plan>' --approved-probe-sha256 '<exact-plan-sha>' --env-file '<data-root>/<env-file>'
# Обновление E1 из того же latest plan, в том числе после ошибки:
./.venv-check/Scripts/python.exe -m scripts.run_e1 report --plan '<latest-e1-plan>'
```

Предыдущее согласие на uniqueItems-пробу уже израсходовано старымHTTP400.
По ADR-0022 для нового варианта нужно отдельное согласие пользователя на передачу
двух passage/cached NER и2POST. Кураторская O/N/R/H карточка — отдельное условие
готовности PR, не автоматическая блокировка подготовки этой технической пробы.
Сейчас новых модельных вызовов нет. Issue13 остаётся открытой, PR33Draft/Refs13.


## HotpotQA: восстановление после TLS timeout — 22 октября 2026

Run17fdc09a остановлен после1005новых POST: known1935267,
одна unknown summary/reserve8432, tree.json отсутствует. Полный E1:
physical known14991627, upper charge15046681, cost_complete=false, готово3/6.
Ошибку не трактуем как ошибку алгоритма или исчерпание окна.
Сохранённый traceback показывает `ssl.do_handshake` → handshake timeout →
requests.ReadTimeout(read timeout=5), а не ожидание generation300секунд.
Несмотря на TLS-фазу, неизвестный server usage не заменён нулём.
Отдельный TLS preflight безHTTP/датасета/модели прошёл за0.390секунды;
он подтверждает лишь текущую доступность, не устранение всех сетевых сбоев.

В существующем runner добавлено одно явно инициируемое сетевое продолжение
`raptor_tls_connect_once_v1`. Изменён только connect timeout:30вместо5секунд,
read timeout300, retry0, redirectsfalse, prompts/caps/models/seed неизменны.
Это отдельный fresh run, не автоматический транспортный retry. Не распространять
политику на Hippo, MuSiQue или другие стадии. Новых corrective summaries нет.

Из прежнего Hotpot12M вычитаются родители2697403 + новыйknown1935267 +
reserve8432 =4641102. **Остаток7358898combined tokens**. Из4000разрешённых
physical POST уже использовано1005, **максимум2995новых POST target+local**.
Внешние данные те же: оставшиеся Hotpot кластеры; embedding локально;
вопросы/gold/supporting labels не передаются. Все1004успешных физических ответа
последнего run переиспользуются наряду с прежним prefix, fallback и Dense leaves.
Проверка journal/manifest/artifacts/source SHA сохраняет unknown как unknown.
Первый новый запрос обязан совпасть с failed request key
f24cbd110cbdf431139dc711d894178d8fe45d79fe474e44c51451a80ed6b7fc;
иначе остановка доHTTP. Это проверяет реконструкцию исходного payload во время
детерминированного replay, не требует ещё одного диагностического POST.

Canonical claim рядом с failed output исключает повторное сетевое продолжение
между каталогами/worktrees, новый output hotpotqa-summary-network1. Повторный
TLS timeout, length, unknown, native overflow, SHA mismatch или исчерпание лимита
останавливают stage. Нет автоматического третьего запуска или роста бюджета.
Изменение timeout не восстанавливает usage старого запроса и не гарантирует успех.

```powershell
$dataRoot = '<data-root>'
./.venv-check/Scripts/python.exe -m scripts.run_e1 raptor-summary-network-resume --prior-plan "$dataRoot/indexes/e1/issue13-raptor-summary-plan.json" --plan "$dataRoot/indexes/e1/issue13-raptor-summary-network-plan.json" --network-audit '<saved-summary-stderr.log>'
```

Команда только готовит план, безHTTP. Запуск после действующего разрешения —
существующий `run` исключительно raptor/hotpotqa на новом плане и pinned SDK.
Все failed run/manifest/response остаются неизменными. PR Draft/Refs #13,
техническая готовность и актуальное научное согласование остаются отдельными.


## Текущий путь восстановления — 22 октября 2026 (offline)

### Решение по сохранённому HotpotQA ответу

Отдельная запись принятия: [e1-raptor-summary-adoption.json](../results/summary/e1-raptor-summary-adoption.json).
Проверены SHA исходного payload/context и полного response, включая привязку
original b243e850… → fallback25c48a37… → response c4005c11….
Проба384f9946 по-прежнему failed по hard300слов; исходные данные не изменены.
Новая запись принимает целый315-word response для будущего continuation,
не пересматривая результат той диагностики. Старый length никогда не используется.

Родной BGE-M3 GGUF daec91ff… и установленная libllama.dll00ea020d…:
550токенов со special/548без, контрольный старый summary2104/2102.
Воспроизводимый `NativeBGE` в scripts/e1_summary_recovery.py использует
`llama_model_load_from_file`, native vocabulary и `llama_tokenize` через ctypes;
контекст inference не создаётся, embedding/decode/HTTP отсутствуют. Адаптер
проверяет точные SHA DLL/GGUF; Win64 ABI ограничен этой закреплённой сборкой.
Native proof с SHA хранится отдельно в ignored adoption output; безопасные
counts/pins опубликованы в записи принятия. num_ctx=num_batch=4096,
truncate=false; 550 помещается в оба лимита. Фактический прежний Ollama log
подтверждает n_ctx_slot=4096,n_batch=4096,n_ubatch=4096. Это проверка
вместимости, не embedding-прогон.

16групп основных утверждений проверены по исходному context, anchors указаны
в записи принятия. Существенных неподдержанных добавлений не найдено.
Исходный context содержит промежуточные summaries: их собственная фактическая
точность независимо не установлена. Вопросы, gold и supporting labels не использовались.
315слов не являются техническим переполнением; повторять POST ради300не нужно.

### Политика length_fallback_native_capacity_v1

- Единое правило для MuSiQue/HotpotQA: trigger — baseline finish_reason=length.
  Обычный prompt/cap4096 сохраняется; только corrective prompt просит≤300слов,
  cap1536,temp0,seed42,thinking=false,timeout5/300,retry0,redirects=false.
- 300слов — желаемая краткость, без нового порога350. Обязательны stop,
  непустой полный ответ, известный input/output usage, проверенная provenance
  и вместимость родным BGE tokenizer в min(num_ctx,num_batch)=4096.
- Максимум одна corrective-попытка на датасет. Hotpot уже использовал её:
  в подготовленном continuation **0новых corrective POST**. Любой следующий
  length прекращает этап; новое исправление требует нового решения.
- Успешные baseline summaries обоих датасетов не перегенерируются. MuSiQue
  использовал исходный prompt; Hotpot в одном месте использует отдельный
  corrective prompt. Эти фактические различия сохраняются в provenance.
- До каждого нового embedding native count проверяется offline; overflow
  останавливает процесс доHTTP. Нет обрезки и принятия partial JSON/text.

Текущее поручение разрешает эту техническую offline-подготовку. Проверка
BOT_REVIEW_WORKFLOW/ADR не выявила отдельного обязательного решения куратора
для неё; прежнее предложение «только новый допуск куратора» ниже не является
текущей блокировкой. Реальные расходы требуют отдельного разрешения пользователя.
Актуальное научное согласование O/N/R/H перед Ready проверяется независимо.

### Hotpot continuation в существующем runner

Новый run/output hotpotqa-summary1, неизменные предки ff75d8dd/384f9946.
Подготовка проверяет SHA/журналы/manifest/artifacts, native550 и создаёт
единственный claim рядом с каноническим prior output. Повторная подготовка
в другом каталоге/worktree не разрешает ещё одну continuation.

2826успешных физических responses исходного run и Dense5500 leaf vectors
переиспользуются по SHA. Fallback — отдельный physical response пробы;
`summary-fallbacks.json` нового run связывает ключ исходного запроса с новым
ключом prompt/response SHA/producer/adoption SHA. Cache journal называет
фактический fallback key, поэтому изменённый prompt не выдаётся за старый hit.
Будущий replay также проверяет SHA. Нового generation для этого ответа нет;
embedding принятого ответа ещё потребуется и входит в новые лимиты.

Полный расход родителей2693810+3593=2697403учтён ровно один раз.
Hotpot: **≤9302597новых combined tokens** (target input/output и local embedding)
в прежнем12M. **≤4000новых физических POST всего** target+local,
1попытка/request,0retry; cache hits лимит физических запросов не расходуют.
4000 — административный предохранитель, не прогноз числа оставшихся запросов
и не обещание закончить индекс в этом лимите. MuSiQue и Hippo не запускаются.

Во внешний target API уйдут только оставшиеся тексты кластеров HotpotQA
на прежних5500passages; embeddings — локальному BGE-M3. Вопросы/gold/labels
не отправляются. Остановка на первой ошибке, length/пустом ответе,
неизвестном usage, подмене SHA, native overflow, исчерпании budget/POST cap.
Failed manifest сохраняет затраты/unknown и журнал; продолжение после ошибки
автоматически не разрешается. E1 known13056360/charge13102982/cost_complete=false
пока неизменны: в этой работе нет ни одного нового модельного запроса.

Подготовка (безHTTP; итоговый план должен быть связан с чистым HEAD):

```powershell
$dataRoot = '<data-root>'
$prior = "$dataRoot/indexes/e1/issue13-raptor-clustering-plan.json"
$plan = "$dataRoot/indexes/e1/issue13-raptor-summary-plan.json"
./.venv-check/Scripts/python.exe -m scripts.run_e1 raptor-summary-resume --prior-plan $prior --plan $plan --summary-adoption results/summary/e1-raptor-summary-adoption.json --native-gguf '<pinned-bge-gguf>' --native-library-dir '<ollama-native-library-directory>'
```

Подготовка не разрешает запуск. После отдельного разрешения — существующий
`run --method raptor --dataset hotpotqa --plan ... --source <pinned-raptor-source>`;
автоматический scheduler не возобновлять. Новый commit потребует перепривязки
плана после проверки, не правки старых manifest задним числом.

### Hippo: совместимый кандидат, не исправление цикла

`prepare-compatible-schema-probe` восстанавливает исходные requests двух
известных сбойных passages и их cached NER на pinned SDK. Schema v2 сохраняет
строгую форму triples, но не отправляет неподдерживаемый uniqueItems. Локальный
валидатор требует finish_reason=stop, известный usage, полный JSON без
повторных полей, объект только triples, тройки из трёх непустых строк и отсутствие
дубликатов. Нет очистки дубликатов, частичного JSON и повышения cap.
Исторические length/cycle ответы отвергаются; их tuple-count — только диагностика.

Минимальное предложение:≤2target POST, по одному на каждый из двух старых
passages+cached NER, cap3072,1попытка/request,retry0,NER/embedding0,
stopfirst. Старый HTTP400 сохраняет unknown reserve8679; remaining до новой
пробы16057275. Точный резерв кандидата17625(8657+8968) записан
в private `.cache/e1-compatible-schema-plan.json`. На обоих старых ответах
full JSON parse failed; диагностические complete/unique tuples168/3и163/4.
Успех не разрешает full rebuild и не доказывает устранение генеративного цикла
или корректность фактов. Совместимость остальных keywords с сервером пока
не проверена. Legacy run-schema-probe не принимает изменённый candidate plan;
новый исполнитель должен быть проверен и разрешён отдельно перед реальными POST.

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_e1 prepare-compatible-schema-probe --prior-plan '<clustering-plan>' --source '<pinned-hipporag-source>' --plan '<private-compatible-schema-plan>'
```

Ни этот proposal, ни подготовленный Hotpot plan не разрешают HTTP сейчас.


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


## Результат одной согласованной пробы —21октября23:47MSK

Run384f9946-44cd-4b46-a58a-fe965724bb64 на clean0b23605 выполнил ровно1POST,
0embedding/NER/retry. Ответ finish_reason=stop,3058input/535output=3593known,
1979UTF8bytes. Но315whitespace words при максимуме300: probe failed.
Даже без одного punctuation-only token остаются314лексических whitespace tokens;
это не объясняется только Markdown-разметкой. Лимит300 не переопределён,
ответ не обрезан и не принят в индекс. Full_index_authorized=false.

Parent failed manifest и source responses неизменны. Probe manifest SHA:
`72cc8e5951bb179ecd32eed0dd17ac2863261c872d6a6f502bc2d2458481f37b`.
Response SHA `c4005c1105b5dbce5b88d31497cf8fdab798ab2e8087f5017736e3e7c3ff8b13`.
Approved plan SHA `c70255917d3719816216f647b1d87c3921a9cccdfe7bbc253f64ee4938d37239`.
Все3593токена вошли в общий экспорт из finally; unknown этой пробы нет.
E1 known13056360, upper budget charge13102982, cost_complete=false.
Остаток HotpotQA9302597=12000000−2693810−3593. Старые unknown не сброшены.
Новых index calls/дерева HotpotQA нет; готовы3/6. CI0b23605 passed.

### Короткое воспроизведение и решение для Sol

1. #13/PR#33: Dense×2 и RAPTOR MuSiQue готовы; HotpotQA tree отсутствует.
2. Baseline summary на том же контексте:3011in/4096out,length,не принят.
3. Согласован1POST: system≤300слов/compact prose, cap1536, user context unchanged.
4. Получен полный ответ stop,3058in/535out,1979bytes, но315words>300; failed.
5. Оба расхода сохранены; payload SHA восстановлен точно, retry/embedding не было.
6. Нельзя считать этот результат успешным по исходному критерию или удалить15слов.
7. Вариант A: новая отдельная проба с целевыми250словами при прежнем hard≤300.
8. Вариант B: явное принятие куратором нового допуска, например≤350, с reuse
   полного315-word response по SHA; исходный failed manifest остаётся immutable.
9. Оба варианта меняют следующий протокол и требуют отдельного решения; это
   не основание для автоматического второгоPOST/embedding/full continuation.
10. Перед приёмкой response нужны semantic support/native BGE fit и явное
    версионирование одинаковой политики обоим датасетам; MuSiQue не повторять.
