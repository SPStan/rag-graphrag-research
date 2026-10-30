# Передача контекста Sol / Luna

**E1 status:** 6/6 indexes completed under the structural protocol; physical known tokens=32601955; cost_complete=False; unknown reserve61588 preserved. Final audit/verify completed; monitoring paused.

## Текущая очередь — технический итог issues17/18, ревью Draft PR39/40

- Hot issue17:1500unique=1497completed+3failed,0not_attempted; Dense500/0,
  Hippo498/2,RAPTOR499/1. Проверенный источник —
  [PR39](https://github.com/SPStan/rag-graphrag-research/pull/39).
  Executionf23bb59/child9e7efc49; старый failed root91f59cf6/runtime7a67791,
  raw/plans/claims неизменны. FreshHot2763839known/2099POST,0newunknown/retry,
  общийcounter2/2, дальнейшие restarts запрещены.
- [E3](../results/summary/e3.md):3000accounted=2996completed+4failed,
  общий evaluator/frozen500IDjoin/датасет,1000paired seed42/95%percentile,
  два identical real offline rebuilds. Hot Hippo−Dense F1+5.67п.п.[3.37;8.28],
  RAPTOR+0.90[-1.14;3.04]; Mu Hippo+8.61[5.24;11.98],RAPTOR−2.47[-5.24;0.57].
  Descriptive development S500; CI с0 не эквивалентность/<2п.п.
- Cumulative E2:9856273known/7059POST,2historicalunknown/reserve38277,
  cost_complete=false. E1 отдельно32601955known/reserve61588,cost_complete=false.
  Source/reuse не добавлены повторно; ошибки/mixed Hippo/semantic_verified=false
  сохраняются. RAPTORprovenance отдельно от passage recall@5.
- Оба Draft/Refs17/18; научные O/N/R/H pending перед merge. Следующий шаг —
  ревью39,затем40/актуальное научное согласование, без Ready/merge/issueclosure.
  Монитор удаляется после публикации. Следующие эксперименты не запускать.

## Сохранённый результат MuSiQue S500 — issue16

- Итоговый PR38, `codex/musique-s500-comparison`, PR37/issue15 уже слит обычным merge.
  [Единая таблица](../results/summary/e2-musique-s500.md),
  [safe JSON/audit/receipt](../results/summary/e2-musique-s500.json).
  1500uniqueexpected:1499completed+1historical transport failure,0not_attempted.
  Dense500/0, HippoRAG2 500/0, RAPTOR499/1. Не1500ответов.
- Дополнительные evidence сохранены в e2-musique-s500-evidence.json с run/plan/
  manifest/artifact SHA; две offline CLI-пересборки в temp равны полному public JSON,
  5137immutable files unchanged. Команда/точные per-case/manifest/usage/error paths
  для задач12/14 — в единой таблице. Следующие задачи/signal-check не выполнялись.
- PR37/issue15: все4критерия выполнены; отдельный HotpotQA бюджет согласован:
  4982220новых combined tokens/2100POST (reader900/filter300/localBGE900), retry0.
  Mu budget/continuation уже разрешены; frozen manifest/исторические unknown неизменны.
  Согласие на бюджет не запускает Hot: нужны verified missing-only plan, актуальный
  audit/strict admission и отдельная команда запуска. Запись решения — ADR0028.
- EM/F1(%): Dense34.80/44.93, Hippo43.40/53.55, RAPTOR32.40/42.47.
  R@5passages60.33/70.72; RAPTORprovenance62.12неpassageR@5.
  Pipeline0 для sealed infrastructure failure раскрыт, unknownusage=null.
- Child ba393849-c977-4c8f-97d7-303fc12955c8/runtimea0a52cf завершил199new,
  398POST/802989known, newunknown0. Parent7936654d/runtimee144ad9 сохранён
  failed неизменным, unknowncase3hop1__90327_83076_319330 не повторён.
  Exact reader identity/absent response/started checkpoint/reserve15732 сохранены.
- S500 newphysical parent+child3055781known/2100POST; initial600reuse не оплачены
  повторно. E2csource/development7092434known/4960POST,2unknown/reserve38277,
  cost_complete=false; E1known32601955/reserve61588 отдельно. Cap5990220/2100
  не расширен; model/prompt/cap512/top5/retrieval/index/split/SDK прежние.
- Terminal audit1500cases:1301parents+199child, SHA source/index/data/code/
  response/checkpoint/journal,0newunknown/unfinished/duplicate attempts.
  Privatepercase `results/raw/e2-musique-s500-unattempted-v1/evaluation.json`;
  sourcefailedraw/results/claims не переписывались, новые recovery не запускались.
- Localtracking3MLflow/3Langfuse views по500; fullretrieval/generation text/order/
  answers и usage проверены,36artifact/linkedJSONL roundtripSHA. ОдинMu reader
  unknown остался null. Posthoc — modelcalls0; IDs и safe proof вJSON.
- Послеterminal исправлен только posthoc Langfuse reader(meta.cursor/next_cursor):
 3targeted regressions+native2001obs/view passed. Denseexistingtrace дочитан без
  reexport. Executiona0 отдельно отpostprocessorcommit; generator/evaluatorне менялись.
- S500development/mixedHippoerrors/E1incomplete/replaylatency раскрыты.
  Per-case артефакты доступны задачам12/14; сами новые задачи
  не запускать. Остальные scientific settings не менять. Closes #16,
  интеграция разрешена пользователем после проверок. Монитор уже удалён; новые прогоны не разрешены.

## Сохранённый результат pilot200 — 1199ответов+1transport failure

- Все1200unique method/dataset/question cases учтены:1199completed,
  1infrastructure attempted_failed,0not_attempted. [Единая таблица](../results/summary/e2-pilot200.md)
  и[JSON](../results/summary/e2-pilot200.json). Это complete pipeline comparison,
  не1200ответов и не независимое подтверждение качества/преимущества архитектуры.
- Runtime4bd1d25, final run20a6360f-24f4-4151-a70c-76632d0a81aa:138newcompleted,
  276POST,456469known tokens (LLM452100input/941output,BGE3428),newunknown0.
  Сохранённый historical reader unknown не повторён; reserve22545,usage=null.
- Pilot physical3799313known/2708POST. E2сdevelopment4036653known/2860POST,
  cost_complete=false. Source91871 — часть development237340, безdouble count.
  E1known32601955/reserve61588/cost_complete=false отдельно. Index rebuild0.
- EM/F1(%): Mu Dense33.00/43.60,Hippo42.50/52.61,RAPTOR32.50/43.49;
  Hotpot Dense59.00/70.81,Hippo69.00/79.29,RAPTOR57.00/70.51.
  RAPTOR Hotpot199completed+1transport failure(0.5%), pipeline EM/F1=0длянего;
  это не неверный ответ reader. Paired bootstrap2000seed42,n200,12comparisons.
- HTTP0terminal audit проверил1200unique,1062parents/138new, все data/index/
  result/response/checkpoint/journal SHA, одну sealed unknown identity; sourcefailed/
  claims неизменны. Первоначальная ошибка окружения audit(PYTHONPATH) исправлена
  без нового run/POST. Execution pins4bd1d25 отделены от postprocessing correction.
- Local tracking:6MLflow/6Langfuse views по200cases,66artifact roundtripSHA;
  в обоих сервисах6000retrieval+6000generation documents совпали с source по
  title/text/order, вMLflow также answers. Reader usage/unknown проверены.
- Reporting-only correction:33BGE tokens reuse внутриpilot отнесены кpilotphysical,
  не кdevelopment cache; global cost/answers/payloads не менялись. Regression3passed.
  Langfuse содержит явную cost-attribution-correction annotation без trace reexport.
- Latency instrumented/cross-run, включает guards/persistence; validation lineage
  послеcontinuation больше. Source/replay не freshE2E; RAPTORprovenance не passage
  recall@5. Tuning/mixedHippo/errors/E1incomplete раскрыты. Сравнение не causal.
- CI cleanup: восстановлены conventional title prefixes(PR36 exp,PR35 feat).
  19history findings проверены:9code SHA,6HF tokenizer SHA,2case IDs,2usage formulas.
  Добавлены только точные commit/path/rule/line fingerprints; blanket exclusions нет.
  Local full-history scan201commits:0findings; отдельный synthetic stdin canary
  обнаружен generic-api-key. Ответы/планы/расходы/модельные вызовы не менялись.
- Рабочий выбор по tuning pilot — HippoRAG2 против Dense на тех же двух датасетах,
  без 2Wiki. Обоснование F1/EM и более высокой стоимости с fact filter добавлено
  в итоговый отчёт и ADR0025; параметры/результаты/JSON/расходы не менялись.
  Это не независимое подтверждение и не допуск задачи9.
- Offline error review: SHA1200results и прежние EM/F1 подтверждены; выбранные
  по фиксированным outcome strata6вопросов/18случаев сверены с top5/source.
  Показаны missing evidence, неверное событие/организация, paraphrase/краткость
  и reference ambiguity. Это иллюстрации, не частоты причин; labels/метрики/JSON
  неизменны, HTTP0. Научные формулировки подтверждены по сообщению пользователя;
  это не опубликованное одобрение бота или GitHub review.
- Реализация и результаты issue14 собраны в PR36; фактический diff относительно
  master проверяется после merge33. При успешном CI разрешены Ready/merge36 и
  закрытие issue14/Done существующей карточки. Следующая очередь — issue15,
  только протокол/reuse в отдельном блоке; новых экспериментов здесь нет.

## Предыдущая transport-остановка (история)

- Runtime3914d70, child fadc0797-34e3-4468-8f0d-bc9ef1289f3a terminal failed
  в2026-10-26T02:11:11Z. Worker завершён, retry/recovery0; исходные manifests/claims
  не менялись. Мониторинг завершает работу; повтор POST не разрешён.
- Reader target API оборвал соединение без ответа (RemoteDisconnected), HotpotQA
  question5adbe75455429944faac23af. Один physical reader POST имеет unknown usage.
  Reserve22545tokens сохранён как консервативная граница, не расход/ноль.
- [Текущая неполная таблица](../results/summary/e2-pilot200.md):1061completed,
  1attempted_failed,138not_attempted. Dense/Hippo×2 и RAPTOR Mu по200готовых;
  RAPTOR Hotpot61completed+1transport failure+138not attempted. Paired inference нет.
- Child487POST=248reader+239BGE,937346known tokens;1unknown reader. Pilot parent+child
  2432POST/3342844known; E2сdevelopment2584POST/3580184known,cost_complete=false.
  E1known32601955/reserve61588/cost_complete=false отдельно. Unknown не засчитан нулём.
- Бывший byte overflow пройден полным неизменённым payload:37608bytes,
  native9860/server9860input tokens,5output; embedding/retrieval reused. Byte gate
  не вызвал новую остановку. Все новые результаты и стоимость сохраняются.
- Existing report-only сформировал6строк без новых HTTP. Live reader подтвердил
  finished487,unknown1,inflight0,corrupt-tail0. Partial tracking не экспортирован;
  полное1200-case/audit/paired сравнение не объявляется выполненным.
- Единственный следующий шаг: уточнить у владельца API исход запроса по сохранённым
  метаданным/времени, не повторяя его. Сообщения оператору не отправлялись. До решения
  о пропущенном unknown case нового continuation нет; бюджет/протокол не ослаблять.

## Предыдущая остановка pilot200 (история)

- Отдельный зависимый Draft PR36, codex/e2-pilot200; PR35 и основной checkout
  не изменены. Runtime `41ee909c14ffca5dff552fa65d46f33f39d9ed8d`.
- После прямого допуска exact plan284af290…5b4f01 выполнен run
  `84454233-8d21-4731-922a-5a31184610e0`. Terminal failed; без retry/recovery.
- 812completed,1attempted_failed,387not_attempted из1200уникальных случаев.
  Dense/Hippo×2 завершили по200, RAPTOR Mu12completed+1overflow, Hotpot0.
  [Неполная таблица](../results/summary/e2-pilot200-incomplete.md): парные выводы
  не публикуются; незапущенные случаи не засчитаны как неверные ответы.
- RAPTOR Mu question `4hop1__802394_153080_159767_81096`: actual answer-only
  messages37608UTF8bytes >32000. Это реальный overflow без truncation;
  reader POST не было, только33known BGE tokens. Не ошибка ответа reader.
- 1945новых POST=802reader+380Hippo filter+763BGE; все finished/known,
  unknown0/unfinished0. LLM2356693input/29066output, BGE19739input:
  2405498новых combined tokens. Все813saved cases,374source pins,
  полные data/index/code pins и immutable terminal journal проверены offline.
- Used source80504tokens/80operations — часть development237340/152POST,
  не дополнительный расход. E2physical cumulative2642838tokens/2097POST.
  E1known32601955/reserve61588/cost_complete=false остаётся отдельно.
  Исторические времена не превращены в freshE2E. Старые результаты неизменны.
- Единственный следующий шаг: предложить общую политику ограничения входного
  контекста для всех методов через ADR до continuation. Нельзя молча поднять
  limit/обрезать контекст/перезапустить failed plan. Остаток54784356tokens/763POST
  не является разрешением. S500/check/holdout/7B/rebuild/новые пробы не запущены.
- Partial pilot не экспортирован в MLflow/Langfuse: публичная таблица и строгие
  raw artifacts — источник этого результата; прежние tracking views не менялись.

## Подготовка pilot200 (история)

- Ветка codex/e2-pilot200 от b708aa5, отдельный зависимый Draft к PR35;
  PR35 остаётся Draft/20files, основной checkout с правками не изменяется.
- shared-answer-only-v1 закреплён прямым поручением пользователя: основание
  format/length, не F1. Общий основной runner/transport всех3методов использует
  этот payload, cap512/temp0/seed42/thinkingfalse/parser/byte gates неизменны.
-1200cases =200ordered published tuning IDs×2×3. Gold/supporting только evaluator.
  [ADR0025](../.adr/0025-pilot200-shared-reader.md) фиксирует scope, reuse и cost.
- Проверенный reuse:60contexts и все12совместимых answer-only responses, включая
  ошибки содержания. СтарыеThought ответы не переносятся;374sourcefile SHA pinned.
- Новый предел1188reader/≤380filter/1140localBGE=2708POST,≤1568externalLLM.
  Reserve57189854tokens — верхняя граница payload, не прогноз. Retry0/redirect0,
  timeout30/300. Первый fatal/unknown/pin/budget/overflow stop, без recovery;
  known reader failures продолжают очередь без повторов. Filter strict отдельно.
- Source91871known — часть development237340, не дополнительный расход;
  новые physical, used source и development отдельно. E1known32601955/reserve61588/
  cost_complete=false неизменны. Cache timing не freshE2E, исторические времена
  не суммируются с новыми; JSON хранит source run/stage timing.
- Frozen plan results/summary/e2-pilot200-plan.json SHA
  `284af290878ef53f9a486d1df956a8e02d72f147d3a6f1e2aa0b072efc5b4f01`.
  Native indexes/source artifacts проверены offline; real model calls0.
  Следующее — один допуск exact плана для всех3методов/двух датасетов; на момент подготовки pilot ещё
  не запускался. После допуска whole script до fatal, без новых prompt/cap проб.

## Предыдущий законченный блок E2

### Answer-only diagnostic завершён (история)

- Пользователь разрешил exact plan1b816118…71cf8b ответом «Продолжай».
  Execution22e4553; run `eb9668ff-ef12-45c5-ac4e-4c52f868a84c` завершил12/12POST:
  все finish=stop, одиночный Answer, reported reasoning_tokens0, без цикла/ошибок.
- Новые LLM28132input/100output=28232known tokens, unknown0/unfinished0,
  embedding/filter/retrieval/indexing POST0.12POST из12; token reserve152350 соблюдён.
  Все347source pins неизменны, старые smoke results/manifests/стоимость сохранены.
- Source-only audit12method cases (4unique tuning questions), без gold/F1:
  7supported/2observed_error/3needs_review. Два former-length случая теперь дают
  полный ответ, но подставляют неподходящий факт из distractor/другого исследования.
  Три direct Roncalli answers поддержаны, но painter/death-place bridge отсутствует.
  Для RAPTOR проверены answer-relevant original descendants, не только provenance.
- Это technical pass с раскрытыми source findings, не подтверждение качества
  или статистическая оценка error rate. Audit выполнен Codex, не независимым человеком.
  Reader автоматически не принят; исходная общая таблица43/17 не пересчитывалась.
- Raw immutable manifest остаётся responses_pending_source_audit; завершённая
  assessment в raw/e2-answer-only-diagnostic-v1/source-audit.json и отдельном
  original-source-proof.json с SHA. Отдельный diagnostic tracking без EM/F1.
- Diagnostic tracking подтверждён: MLflow `b7fad1509ffa409e895761f68eeffbea`,
  Langfuse `bdb7418a6537553f33942e2c9c6806b8`;12question/generation spans,
  60cached context passages/nodes (не новые retrieval),0embedding POST.
  Reader usage28132/100 сверено обратным чтением;8artifact round-trip SHA совпали.
- Совокупный E2 query known237340=209108old+28232diagnostic, физически152POST;
  E1known32601955/reserve61588/cost_complete=false отдельно, incomplete не снят.
- Единственный следующий шаг — предложить фиксацию shared-answer-only-v1 как
  общего output contract для отдельно согласуемого pilot200 с раскрытыми ошибками.
  Новой цепочки prompt/cap/model проб на этих4вопросах не предлагать.
  Pilot200/S500/check/holdout/rebuild/merge и новые model calls не разрешены.

## Предыдущий законченный блок E2

### Диагностический E2 smoke10 завершён

- Пользователь отдельно разрешил exact continuation v2 SHA
  `723a9993cfd710c8e958cc5ae422ca26dfce27b448acb6538b89f28b3990ffe6`.
  Execution code537fa023; child `3bee5af5-13f9-43ad-b9d9-dee3dfd11171` completed.
- Все60уникальных method/dataset/question случаев учтены:43completed,
  17attempted_failed (reader length cap512),0not_attempted. Ответы partial не приняты,
  retry0. Parent2completed+1failed неизменны, выполнены только57оставшихся случаев.
- Новых childPOST134, вместе с parent140:60reader/20Hippo filter/60localBGE.
  LLM188118input/19535output, embedding1455; всего209108known tokens,
  child203421+parent5687 ровно один раз. Unknown0/unfinished0; token/post cap соблюдён.
  Остаток original3067692tokens/0POST не является разрешением новых запросов.
- Шесть E1 индексов не перестраивались; query journal содержит только embedding,
  filter и reader. E1known32601955/reserve61588/cost_complete=false отдельны.
- Единая [таблица](../results/summary/e2-smoke10-continuation.md) содержит EM/F1,
  completed/failed/failure rate, measured mean query latency и LLM/BGE usage.
  Failed даёт0, RAPTOR provenance не passage recall@5. Это tuning smoke10,
  не pilot200/полный E2 и не доказательство преимущества архитектуры.
- Local tracking:6MLflow/6Langfuse views по10cases;50retrieved nodes/passages
  на trace, reader usage совпал;48artifact round-trip SHA совпали. Parent+child
  это представление прежних140POST, не дополнительная стоимость. Экспорт
  выполняется по одной конфигурации на процесс (Langfuse SDK resource lifecycle).
- Единственный следующий шаг: общий пересмотр reader для всех методов перед
  pilot200 по техническому признаку17/60length (28.3%), без подбора по F1.
  Новая версия требует отдельного плана/допуска; эти результаты с ней не смешивать.
  Pilot200/S500/check/holdout/новые модели/rebuild/merge не запускать.

## Предыдущий законченный блок E1 (справка)

## Текущая очередь — 25 октября: E1 завершён, 6/6

- Dense×2, RAPTOR×2 и HippoRAG2×2 имеют completed; строгая штатная
  offline verify проверила все6 manifest/journal/artifact SHA без HTTP.
- Hotpot run822bed2d:5500passages,50711entities,75021facts,
  graph56211nodes/183473edges. Save/reload0modelcalls; граф независимо
  перечитан,5500source IDs присутствуют, parquet5500/50711/75021rows.
- Последний child:5798local embeddingPOST,1094840known tokens, freshLLM0,
  ошибок/unfinished/новых unknown0;21607cache hits. Ни один готовый индекс
  или завершённый extraction повторно не вычислялся.
- Source audit:54источника, все38warnings +8на каждый extractor stratum;
  проверены769raw triples с точными multiplicities.8supported/40observed_error/
  6needs_review. Это warning-enriched выборка, не оценка error rate/эффективности.
  Review выполнен Codex offline, не независимым человеком/куратором.
- Оба Hippo имеют structurally_verified_with_observed_extraction_errors,
  semantic_verified=false. Ошибки (включая unsupported facts, reversed relation,
  meta-output и пропуски/потерю оговорок) раскрыты; graph/triples не исправлялись.
- E1 physical known32601955; reserve61588; budget upper32663543;
  cost_complete=false. Hotpot known10674027 +unknown2567 =charge10676594,
  POST27437. Исторические failed/claims/расходы сохранены, двойного учёта нет.
- Recovery counter2/2; worker завершён, e1-hotpotqa PAUSED; новых restart нет.
  Terminal proof: .cache/e1-six-index-final-verification.json; current plan
  .cache/e1-hotpot-local-recovery2-plan.json SHA dafe33064f78…fb61f37.
- Таблица и безопасная JSON: results/summary/e1-indexing.md и .json.
  Следующее — техническое ревью Draft PR33 и актуальное O/N/R/H отдельно.
  Refs #13; без автоматического Ready/merge/закрытия issue, QA/E2/holdout.
  Для E2 потребуется отдельный план и Hippo read-only adapter; его здесь нет.

## История — не текущие инструкции запуска


**E1 status:** 2/6 indexes completed; physical known tokens=6403763; cost_complete=False. Last stage=raptor/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

**21октября: Hippo Mu остановлен на2329/5500.** Исходный и corrective ответы
снова повторяют4 triples до length3072; обе попытки известны (8273 tokens).
Третьего запроса нет. Планируется независимый RAPTOR ×2 с прежними Dense/cache,
лимитами и immutable lineage; Hippo failed/unknown сохраняются. [Протокол](E1_INDEXING.md).
Gitleaks: точный false positive SHA payload; экспорт переименован, точный fingerprint.
E1 пока2/6; #13/PR #33 открыты, Draft, E2 не запускать.

**E1 status:** 2/6 indexes completed; physical known tokens=5386821; cost_complete=False. Last stage=hipporag2/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

**20октября: cycle repair E1.** Network child остановлен на length3072:
3 уникальных triples повторены56раз. Кап не повышается. Новый cycle plan:
probe того же payload с запретом дубликатов, затем≤20 условных коррекций/dataset,
по1 на циклический request. Кэш обоих предыдущих run, сохранение всей стоимости,
остаток17023464, старый unknown7922 не снят. [Протокол](E1_INDEXING.md).
Готовых индексов пока2/6; #13/PR #33 открыты, Draft. E2/merge не запускать.

**E1 status:** 2/6 indexes completed; physical known tokens=4429311; cost_complete=False. Last stage=hipporag2/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

**20октября: ограниченное продолжение HippoRAG MuSiQue после RemoteDisconnected.**
Первый run failed,1560 passages/3293 verified responses сохранены. Новая папка,
replay по SHA и физическому usage; unknown7922 reserved, known2841297, остаток
17150781 из прежних20M. Connection:close/retry0, один canonical claim; при новой
ошибке стоп. [Протокол/команда](E1_INDEXING.md#продолжение-после-remotedisconnected).
Готовые Dense не повторять; после Hippo Mu идут оставшиеся3конфигурации. Пока
реальных шести готовых индексов нет — #13 открыта, PR #33 Draft, E2 блокирован.

**E1 status:** 2/6 indexes completed; physical known tokens=4301994; cost_complete=False. Last stage=hipporag2/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

**20 октября: активна #13, E1 на полном корпусе.** #31 слит eab5606, #12
закрыта; полного независимого технического ревью перед merge не было из-за
недоступного diff шлюза. Новый блок: [протокол E1](E1_INDEXING.md), шесть
индексов5500, только индексация. Новый предел68M; результаты smoke не переносятся
в качество метода, historical unknown сохраняется. До фактических шести индексов
#13 открыта/PR Draft. Более ранние запреты автоматического full run описывают
состояние до прямого поручения выполнить #13.

E1 batch edff74df-c567-49de-a834-f9f1fc6f7f74 на aa1e4f4: Dense MuSiQue
готов5500/172POST/684560embedding/113.705s. Dense HotpotQA failed на третьем
batch: известны9333, ещё один usage unknown, HTTP400 внутреннего /tokenize
из-за Windows socket allocation. Проверены TIME_WAIT/port range, после паузы
сокеты освободились. Протокол однократного продолжения/пейсинга и резервирования
unknown в E1_INDEXING; старые папки не менять. Полного E1 пока нет, E2 блокирован.

**Текущее состояние после интеграции master:** #12 smoke завершён, ниже результат.
PR #30/#11 слиты/закрыты; обзор #32 также в master. Старые статусы ниже — история.
Полные выборки/новые расходы/merge #31 автоматически не запускать.

**20 октября: реальный RAPTOR smoke завершён.**
Run c311fd7a-9b0a-45f3-8c14-862bf3a42d2e на clean6c2c483: дерево80 узлов
(50 leaves/30 summary), слои50/21/9; save/reload без вызовов, отдельно проверен
reload новым процессом с неизменными raw/journal SHA. Общий reader3/3.
Новых44POST/42874tokens (embedding11818, LLM18748+12308); cache72 с producer SHA.
Continuation+remediation60330 из100000; весь history169 attempts, known67454,
aggregate complete=false/total=null из-за первого timeout. [Сводка](../results/summary/raptor-smoke-completed.json).
Три support-preserving вопроса — функциональный smoke, не эффективность.
31 targeted/26 official SDK fake HTTP прошли, gate/hooks/CI6c2c483 прошли.
Согласие на historical unknown передано пользователем20октября; O/N/R/H прежние.
#12 остаётся открытой до полного ревью/отдельного merge. Старые блокеры ниже — история.

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

**20 октября: согласованное продолжение остановлено на cap512.**
Run `3a48630b-72fe-46a9-99eb-309035ed1a0c` (`00f3e8a`, clean): 11 summary
stop, 12-й length (897 input/512 output); 73 POST, новый полный расход
embedding9739 / LLM3983+3734. Общий учёт125 attempts неполон, total=null из-за
первого timeout. [Результат/артефакты](../results/summary/raptor-continuation.json),
[детали](RAPTOR_SMOKE.md). Дерево/reload/reader0/3 не завершены. Повторов нет,
claim сохраняется. Согласие преподавателя передано пользователем и принято;
следующий блокер технический: политика truncated summary. PR Draft, #12 открыта.

**20 октября: преподаватель согласовал продолжение с historical unknown.**
Пользователь передал: «Ну, я точно не против»; внешний URL не предоставлен.
Один новый bounded smoke, guards 100000 новых tokens / 100 POST / 20 summary,
timeout5/300, retry0. Старые failed + diagnostic остаются в aggregate с
complete=false/total=null; hashes проверяются, shared claim запрещает повтор.
[Протокол/команда](RAPTOR_SMOKE.md). O/N/R/H не меняются. PR Draft, #12 открыта.

**14 октября: опубликован обезличенный оператор диагностики по ревью 41b64eee.**
[operator.py](operators/operator.py), [команда/SHA/ограничения](RAPTOR_SMOKE.md).
Только две механические замены: env-file через переменную, ROOT по новой папке;
исторические SHA/manifest не менялись. Offline-тесты исполняют этот файл с fake
HTTP, проверяют один POST, запрет повтора и ошибки. Новых реальных запросов нет.
Приёмка #12 не завершена; продолжение с prior unknown требует согласования
куратора, PR Draft/Refs #12. research-команды инструментами не предоставлены.

**14 октября: пользователь разрешил один повтор summary #12.** Диагностика
`3525d53a-8a93-4e17-a784-6337feb520a7` завершена: тот же payload, read timeout
300 s, retry=0, 350 input / 375 output, stop/nonempty. Server input = native350.
[Сводка](../results/summary/raptor-summary-diagnostic.json): суммарно 52 attempts
(50 embedding + 2 summaries), prior usage по-прежнему unknown, aggregate
complete=false / total=null. Исходные raw не менялись. Дерево/reader не запускались,
новый запуск не разрешён этой одной диагностикой; curator approval не заявляется.
PR Draft/Refs #12. Более ранние «повторов нет» ниже — состояние до этого решения.

**14 октября: пользователь уточнил API contract.** Context 262144 input+output,
output до остатка окна, native Qwen/Qwen3.8-27B HF tokenizer/template,
vLLM 0.29.0, без server count endpoint. Первый failed summary локально
посчитан по закреплённому native tokenizer: 350 input + cap 512 = 862, fit есть.
Серверный usage неизвестен и timeout не выяснен; это не разрешает слепой повтор.
[Подробности](RAPTOR_SMOKE.md). Старые raw/summary не перезаписывались, новых
модельных попыток нет. PR #31 Draft/Refs #12; куратор и техническая готовность
проверяются отдельно. Статусы ниже описывают более ранние состояния.

**13 октября: активна #12, RAPTOR на малом корпусе.** По команде пользователя
#29 слит (`5e617fa`), #10 закрыта. #11 отдельно в Draft PR #30: target context
contract неизвестен, генерация OpenIE не разрешена протоколом repair.
#12 независима от этого блокера; ветка `codex/raptor-small-corpus` от master,
официальный upstream закреплён, callbacks и reload проверены offline.
Реальный run `bb0b97d2-b0ca-4d09-926c-76d2309b0853` на `2b699a2` остановился:
50 leaf embeddings (6399 локальных tokens), первый target summary — ReadTimeout
120 s, usage неизвестен. Реальное дерево и reader не завершены. Журнал целостен,
затраты неполны; [сводка](../results/summary/raptor-smoke.json), raw в worktree
`dense-target-smoke/results/raw/raptor-smoke/<run-id>/`. Draft [PR #31](https://github.com/SPStan/rag-graphrag-research/pull/31), Refs #12, Projects In Progress.
Протокол и команды — [RAPTOR_SMOKE](RAPTOR_SMOKE.md). Перед новым расходующим
протоколом разобраться с timeout/usage; сохранить failed run в суммарном учёте.
Только 50 passages / три development-вопроса, не full corpus. Следующие задачи,
повторные запросы и merge автоматически не начинать. Статусы ниже — история.

**14 октября: обзор опубликованных методов #25.** Подготовлены [полная таблица](related-work-comparison.md#full-comparison) и [слайдовый вариант](related-work-comparison.md#slide-version) Dense RAG / HippoRAG 2 / RAPTOR с версиями первоисточников и ограничениями. Журнал чтения студента сохранён; новых модельных вызовов нет, реализация RAPTOR не менялась. 15 октября первоисточники повторно сверены; по поручению пользователя PR #32 передаётся в Ready for review. Научное согласование O1/N1/R1/H1 ещё не зарегистрировано; нужно отправить `/research_submit https://github.com/SPStan/rag-graphrag-research/pull/32 25` через бота и получить явное согласие куратора. Эта команда недоступна инструментам агента. До согласования issue/PR не закрывать, merge отдельно. Настройка доски #23 завершена [итогом в issue](https://github.com/SPStan/rag-graphrag-research/issues/23#issuecomment-6170587264), issue оставлена открытой. Текущая экспериментальная работа #12 продолжается отдельно; строки ниже описывают предшествующие этапы.

**14 октября: исправлена проверка task до измерительного запроса.** Общая
валидация attempt/remedial/retry_of_attempt/passage_id/dependency/stage вызывается
до request_fn в measure_then_execute_openie_task и сохраняется в прямом
execute_openie_task. Регрессия некорректных задач подтверждает ноль callback;
целевые executor/offline runner: 16 passed. Новых модельных запросов нет.
PR #30 передан на полное ревью, научные формулировки согласованы карточкой
`e818864b878ccf61af85ef16:1`; ready_for_indexing=false, issue открыта.

**14 октября: исправлено should ревью dc7ae635.** SDK source и installed
проверяются независимо по immutable Git tree/blobs `1438aba3`, до импорта
prompt-кода; одинаковые dirty изменения отвергаются до HTTP. Регрессии и
повторная проверка реальных 61 файлов прошли. Новых модельных запросов нет,
raw фактического run не менялись. [Команда и детали](OPENIE_TARGET_CHECK.md).

**14 октября: пять реальных target OpenIE cases завершены.** Run
`b1549680-6917-47e4-a614-3540fcda01a6` на чистом `2e46d0a`: 5/5
valid_nonempty/stop, native input count совпал с server usage у каждого.
2535 input + 784 output, 5 POST, без retry/коррекций; durable journal verified,
complete=true только для этого run. Исходные manifest/corpus/state/cache SHA
не изменились, 61 SDK Python-файл проверен. [Результаты/SHA](../results/summary/openie-target-live-check.json),
[таблица до/после](OPENIE_TARGET_CHECK.md). ready_for_indexing=false: весь старый
индекс не чинился; точность извлечения и эффективность не измерены. PR #30 Draft,
научное согласование/полное ревью отдельно, merge только по команде. Общая claim
по snapshot блокирует повтор через другую worktree/output; не удалять для retry.
Более ранние утверждения о нуле новых запросов ниже — исторические.

**14 октября: получен контракт API.** Пользователь сообщил 262144 общий context,
output до остатка окна, native Qwen/Qwen3.8-27B HF tokenizer/template,
vLLM 0.29.0; отдельного count endpoint нет. Закреплён HF tokenizer revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`; все пять OpenIE prompts проверены
локально: input+cap 1302–3793, fit проходит. Таблица/SHA и ограничения —
[OPENIE_TARGET_CHECK](OPENIE_TARGET_CHECK.md). Серверные counts ещё не сверены,
команда native count/SHA воспроизведена; безопасные counts/rendered SHA теперь
в [публикуемом артефакте](../results/summary/openie-target-context-counts.json).
Точный HF revision deployment отдельно не сообщён. Новых модельных запросов 0,
ready_for_indexing=false. Исторический preflight не перезаписан. Для #12 отдельно
остаётся невыясненный timeout/usage; эти параметры его не разрешают.

**13 октября: обработано предварительное ревью PR #30 на `0038c096`.** Новых
дефектов кода бот не сообщил; обязательны подтверждённый context/output contract,
точный input token count, до пяти реальных OpenIE cases и согласие куратора.
Дополнительные metadata GET `/openapi.json`, `/v1/openapi.json`, `/docs` — 404;
документированный счётчик не найден. Генерацию не начинать при неизвестном fit.
Карточка `eb27b8fa5654329712648d28:0` зарегистрирована, все четыре пункта пока
не утверждены. Точный запрос провайдеру и порядок завершения встроены в
[OPENIE_TARGET_CHECK](OPENIE_TARGET_CHECK.md). PR остаётся Draft/Refs #11;
ready_for_indexing=false, issue открыта. Решение куратора агент не подменяет.

**13 октября: пользователь поручил issue #11 — ошибки OpenIE HippoRAG.** PR #29 слит (`5e617fa`), #10 закрыта/Projects Done, научное согласование #10 подтверждено пользователем ответом research_status. Текущий блок — до пяти сохранённых development-примеров #11, без возобновления старого repair и без пересборки корпуса. Ветка `codex/openie-target-check` использует существующий SDK-worktree. Read-only target preflight интегрируется в `preflight_hipporag_repair_prompts`; старые артефакты сохраняются. Пользователь подтвердил неизвестные context/output limits и tokenizer/backend revision; API metadata их не сообщает. Генерация OpenIE и индекс не запускаются до проверенного context-fit контракта. Итог и команды — [OPENIE_TARGET_CHECK](OPENIE_TARGET_CHECK.md). Научное согласование #11 отдельно; merge только отдельно. Предыдущие статусы ниже — история.

**13 октября: зависимость #28 разрешена, актуальное согласование #29 ожидается.** PR #28 слит в master (`edc5d28`), issue #9 закрыта, Projects Done. Master интегрирован в ветку #29 обычным merge, чтобы сохранить исходные commit ID фактических запусков и SHA provenance; модельные запросы и raw не повторяются/не изменяются. Итоговый diff относительно master содержит только блок #10. Последнее ревью бота пометило согласование карточки `1d9e259796f6f4e1f28694a8:1` устаревшим: текущие O1/N1/R1/H1 нужно повторно отправить `/research_submit https://github.com/SPStan/rag-graphrag-research/pull/29 10`, затем проверить `/research_status https://github.com/SPStan/rag-graphrag-research/pull/29`. Эти команды недоступны через текущие инструменты агента; согласие куратора не подменять. PR #29 сохранять Draft/Refs #10, issue #10 открытой до актуального согласования и полного технического ревью. Следующие #11/#12 и merge отдельно. Статусы ниже — история.

**8 октября: технический smoke #10 завершён.** После одной remote диагностики исправлен ложный ambiguous marker через версию `standalone-answer-line-v1`, legacy parser сохранён. На `4a60f2d` завершены пять MuSiQue и пять HotpotQA ID; raw/metrics/manifests/journals в `dense-target-smoke/results/raw`, [сводка](../results/summary/dense-target-smoke.json) включает исходную ошибку, диагностику, финальные метрики и весь расход. PR #29 остаётся Draft/Refs #10 до разрешения зависимости #28 и актуального научного согласования. Следующие #11/#12 не начинать автоматически; merge только отдельно. Историческая остановка ниже сохраняется.

**8 октября: начата issue #10 — Dense target smoke.** Пять development-вопросов на каждый набор, малый корпус, Qwen3.8-27b и локальный BGE-M3; фиксированный план и ограничения — [TARGET_API](TARGET_API.md). Работа в `codex/dense-target-smoke` поверх проверенного `51f9794` PR #28, который ещё открыт и ожидает научного согласования. Никаких утверждений о слиянии #9; после его merge перебазировать новый Draft. Полные выборки и отложенные вопросы не запускать.

**Остановка #10:** MuSiQue `0b41ddc1-9e9f-4243-8679-e91d86b085ee` на коде `afd60ab`: один ответ принят, второй не прошёл reader validation. Учтено 4264 embedding / 3226 LLM input / 505 output tokens. HotpotQA не запускался, итоговые метрики не рассчитаны. [Сводка](../results/summary/dense-target-smoke.json); PR #29 Draft, дальнейшие модельные вызовы остановлены по протоколу.

**8 октября: проверка SDK для PR #28 выполнена.** Восстановлено отдельное окружение HippoRAG `1438aba3`; OpenAI `3.26.1` и HTTPX `0.28.1` проверены на подставном HTTP через реальные CacheOpenAI и batch_openie: **9 passed**, 77 пакетов совместимы. Общий offline gate: 207 passed, 13 skipped (девять SDK-тестов выполнены отдельно). Retry=0 даёт одну попытку при ошибке; положительный контроль retry=1 — две. Фазы и passage ID сохраняются в рабочих потоках; кэш не повторяет физический запрос, missing usage отмечает неполноту. Команды — [TARGET_API](TARGET_API.md). O1/N1/R1/H1 согласованы куратором по карточке `54ed244c46d451135bcf444b:1`. PR #28 и issue #9 остаются открытыми; merge только отдельно. Следующий существующий блок — PR #29/issue #10, зависящий от #28; новых модельных запусков в этой проверке нет. Статусы ниже — история.

**7 октября: активная issue #9 — пофазный учёт токенов.** #7 и #8 закрыты; PR #26 и #27 слиты. Куратор принял отклонение #8, но два неизвестных usage остались неизвестными. Работа #9 ведётся в отдельной ветке `codex/phase-token-accounting` без модельных вызовов. Проверять журнал попыток, offline-тесты и ограничения по [TARGET_API](TARGET_API.md); следующую расходующую задачу автоматически не начинать. Исторические статусы ниже сохранены для контекста.

**7 октября: issue #8, целевой API.** PR #24 слит в `master` (`0cb0416`). Работа issue #8 идёт в `codex/target-api-check`; PR #26 переведён в Ready for review. Куратор подтвердил `iairlab/qwen3.8-27b` и локальный BGE-M3; лимит 90M снят. Итоговый smoke с cap 32 проверил вместе BGE-M3 (2 вектора, 1024 измерения, 19 локальных tokens) и Qwen через `chat_template_kwargs` (ответ «Четыре», 23 input / 4 output, 0 reasoning tokens). Исходный Qwen-запрос не вернул текст и не сохранил usage; отдельная диагностика top-level `enable_thinking=false` показала 65 reasoning tokens. Один промежуточный запрос не сохранил отчёт из-за файловых прав, usage неизвестен. Минимальный интерфейс генерации проверен, JSON/OpenIE нет. Научные формулировки O1/N1/R1/H1 согласованы; [куратор принял отклонение от лимита запросов в PR #26](https://github.com/SPStan/rag-graphrag-research/pull/26). Два случая неизвестного usage остаются неизвестными. Подробности — [TARGET_API](TARGET_API.md) и [ADR-0016](../.adr/0016-target-api-smoke-configuration.md). Следующий блок после ревью #8 — ограниченная структурированная проверка по отдельному протоколу.

**Ревью PR #24:** история MuSiQue и неизменность исходных S500 подтверждены. Исправлены неявная перезапись аудита и принятие отсутствующего raw-каталога за пустую историю; проверка опубликованных ID теперь включена в CI. Исходный аудит до проверки остаётся неизменным, последующие runs учитываются отдельно через `--refresh-audit`. SPEC уточняет неприменимость passage recall@5 к пяти summary-узлам RAPTOR. Разбиение 300/100/100 сохранено; статус API по #8 ещё не подтверждён. Следующий шаг — ревью PR #24, затем отдельная задача #8; настройка доски #23 остаётся отдельной задачей.

**2 октября: issue #7 — протокол и ID.** PR #6 с адаптацией шаблона слит в `master` 1 октября. Текущая работа в отдельной ветке `codex/comparison-protocol`: сохраняем прежние S500 и pilot200, публикуем проверяемое разбиение и аудит ID, без вызовов моделей. Старый MuSiQue holdout100 содержит вопрос с раскрытым в DATA эталоном (позиция 482); назначение нового signal-check диапазона 300–399 и границы вывода — [ADR-0015](../.adr/0015-pinned-comparison-and-signal-split.md). После завершения issue #7 следующая зависимость — проверка целевого API по issue #8. Состояние ниже — история, не новая очередь.

**1 октября: адаптация к шаблону лаборатории.** PR #1 с локальным результатом
слит руководителем в `master` 30 сентября. Студент сохраняет
`SPStan/rag-graphrag-research` и не создаёт второй репозиторий. Новый отдельный
блок — привести offline-проверку, issue/PR формы и CI к применимым требованиям
`nir-project-template`, не затрагивая эксперименты. Решение — [ADR-0014](../.adr/0014-adapt-lab-repository-template.md).
Активная очередь — первый блок [TASKS](TASKS.md). GitHub Project и
`nir-agent-overlay` пока не подключены. Индекс преподавателя называет шаблоном
проекта **репозиторий**; отдельной ссылки на шаблон доски там нет. Для регистрации
в боте нужен URL [собственного пустого GitHub Project](https://github.com/users/SPStan/projects/1),
уже привязанного к репозиторию. Преподаватель сам добавит
две двухнедельные вехи и задачи примерно на день работы. `Resurrectiontent`
назначен Admin на приватной доске; регистрация у бота ещё не подтверждена.
Ниже — история прежних этапов.

**29 сентября: подготовка к ревью.** Сначала читать
первый блок [TASKS](TASKS.md). Подготовлены единая offline-проверка и CI по
[ADR-0013](../.adr/0013-offline-review-checks.md); фактические результаты проверки
смотреть в [VERIFICATION](VERIFICATION.md). CI на Windows/Linux прошёл для
`8b795df` с полными Ruff lint/format, offline pytest и Gitleaks. Локальный
pre-commit установлен и проверен; фактическое доверие к Codex project hook пока
не подтверждено. Не начинать новые прогоны и repair.
Следующая предметная работа — ревью сравнения и затем ограниченный пилот целевого
API после согласования параметров/бюджета. Шаблон доски и агентские артефакты
преподавателя ещё ожидаются. Библиотеку статей вести вместе со студентом.
Сохранять вне автоматического коммита WORK_PLAN.md, scripts/resume_dense.py,
LUNA_REVIEW_HANDOFF.md и пользовательские TEACHER_REPORT_2026-09-28.md/.html.

**26 сентября: активная задача изменена.** Пользователь поручил самостоятельно
получить сравнение Dense / HippoRAG. См. начало [TASKS](TASKS.md) и
[ADR-0012](../.adr/0012-as-built-diagnostic-comparison.md). Завершён отдельный
диагностический QA на копии существующего графа без repair, rebuild и 7B.
Ранние запреты на этот конкретный QA заменены новым поручением; остальные
границы сохранены. Не начинать новую цепочку R1–R3 или probe 7B.
Результат: [парное сравнение](COMPARISON_2026-09-26.md), 100 вопросов, F1 Dense
18,58% / HippoRAG 29,97%. Новый run 5e1bdc68-1803-416f-b80b-e5cc5b7b8dcf.
Ниже сохранена история до этого результата; не считать её текущей очередью.

Дата: 25 сентября 2026. Отправная точка ревью — `e7a0367`; перед работой проверить HEAD и git status.
Прочитать AGENTS.md, этот файл и только активный блок [TASKS](TASKS.md). Другие файлы — по ссылкам активного блока.

## Что мы делаем

Это учебная НИР: сравнить dense RAG, HippoRAG 2, RAPTOR по качеству и стоимости; затем проверить маршрутизацию. LightRAG необязателен.
Локальный MVP использует Windows, RTX 3070 8 ГБ, 32 ГБ RAM, Ollama Qwen2.5 3B Q4_K_M и BGE-M3. Основной целевой API/T4 ещё не проверен.
Пользователь учится и устал от повторяющихся подготовительных шагов. Объясняй коротко; измеряй продвижение завершённой возможностью, не количеством скриптов/тестов.

## Где остановились

- Ветка `codex/local-rag-mvp`, [PR #1](https://github.com/SPStan/rag-graphrag-research/pull/1) открыт для ревью; `Resurrectiontent` назначен reviewer 30 сентября.
- Dense candidate S500[200:300] уже завершён: `98d8b412-cec6-45e4-9c14-0e4ad85855bb`; EM 0,110, F1 0,1858, recall@5 0,6058. Его не надо повторять ради HippoRAG.
- HippoRAG source `e78eff08-532a-40b3-a359-49a6b08b32a7`: 5500 passages, индекс диагностический; 160 unresolved OpenIE stage outcomes, QA нет.
- План первого repair-прохода: 38 NER + 158 triples = 196 задач, включая 38 зависимых triple refresh и две attempt-3. Это не полный бюджет с будущими повторными попытками.
- HippoRAG 2.0.0a5: upstream commit `1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff`, отдельное окружение. Не ставить его в основную .venv.
- Planner, single-task executor, journal, copy/vector helpers написаны, но рабочего связанного repair-runner пока нет.
- Последняя записанная полная проверка: 131 unittest, pip check основной .venv. Это не доказательство работы repair на реальном индексе.
- Read-only ревью выявило gaps: журнал не хранит extraction values; два writer могут открыть одну задачу; task может пронести произвольный текст; frozen config не проверяется на фактическом запросе; clone ещё содержит старый граф.
- Context fit не подтверждён. 158 prompts отрендерены, 38 зависимых prompts появятся только после исправления NER. UTF-8 bytes — не token count.
- Исторические debug10 использовались при разработке, baseline100 включает их; полный index cost неизвестен. `holdout100` не использован.

## Обновление 25 сентября 2026 после R1/R2 offline

R1: checkpoint/resume, сохранение values/SHA, один writer, зависимые triples проверены; коммит `58bbc25` отправлен в Draft PR. R2: синтетический `repair → vectors → pinned graph → gate` и захват payload прошли в отдельном HippoRAG environment. Основной набор: 142 unittest, 2 pinned-only пропуска; pinned-only 2 теста прошли отдельно. Старые записи ниже — история состояния до R1.

Текущая очередь: R3 в [TASKS](TASKS.md), предложение и результат пилота в [R3_RUN_PROPOSAL](R3_RUN_PROPOSAL.md). По явному разрешению выполнены только два локальных измерительных запроса: 691 input token для NER, 1003 для triples; triple с cap 3072 занимает 4075 из 4096. Реального extraction repair/rebuild или QA не было, текущий context guard закрыт. Сохранить локальные WORK_PLAN.md, scripts/resume_dense.py, docs/LUNA_REVIEW_HANDOFF.md вне коммита.

## Действие следующей модели (историческое)

**Активный блок: R1 в TASKS.** Закончить offline-маршрут repair/resume с сохранением успешных extraction values и зависимыми triples.
Использовать существующий код. Не начинать второй транспорт, универсальный scheduler, plugin или новый цикл только-документальных preflight-коммитов.
Для R1 читать `scripts/hipporag_repair_journal.py`, `scripts/hipporag_repair_executor.py`, нужные helpers `scripts/hipporag_repair.py`, их tests и ADR-0008.
При работе Luna интеграционные решения согласованы в TASKS; если контракт остаётся неоднозначным, передать один конкретный вопрос Sol с воспроизведением, не расширять систему самостоятельно.
Проверка завершения: новый процесс подхватил сохранённый NER output, не вызвал его повторно, выполнил зависимый triple с правильными entities; unknown in-flight и повреждённый output блокируют продолжение.
Сохранённые values — private артефакт в игнорируемом storage/results/raw; public report содержит только агрегаты и хэши.

## Границы и Git

Никаких новых LLM/embedding-запросов, реального index repair/rebuild, 100 QA, 7B, holdout100 без отдельного разрешения.
Не удалять старые outputs, индексы, volumes и базы. Не передавать gold labels в генерацию.
Не запускать подагентов автоматически; вопрос пользователя об их полезности не является поручением запустить их.
При новом запуске проверить сервисы только тогда, когда они действительно нужны; offline-тестам они не нужны.
На момент ревью локально изменены WORK_PLAN.md и scripts/resume_dense.py; docs/LUNA_REVIEW_HANDOFF.md untracked. Сохранить их байты, не добавлять автоматически.
Старый LUNA_REVIEW_HANDOFF от 23 сентября — исторический аудит, не новая очередь; уже исправленный reader и evaluator не переделывать.
Явно выбирать файлы для коммита; push в текущую ветку после завершённого блока. PR не сливать автоматически.

## Экономия и формат отчёта

Рекомендуемый процесс: Sol отвечает за интеграцию/протокол и короткое ревью, Luna — за ограниченные реализации; Astra — при спорной методологии или повторном тупике.
Не запускать постоянных взаимопроверяющих агентов. Один read-only reviewer на готовый существенный блок — только после явного разрешения; ему передавать diff, контракт и результаты, а не всю переписку.
После двух неудачных исправлений одной причины остановить цикл: 5–10 строк воспроизведения для Sol.
Финал шага: что теперь работает; чем проверено; commit; оставшийся конкретный блокер. Не обещать «повторов больше не будет».

Источники: [TASKS](TASKS.md), [техническое ревью](REVIEW_2026-09-25.md), [SPEC](SPEC.md), [ADR-0008](../.adr/0008-openie-truncation-retry-policy.md), [candidate summary](../results/summary/musique-independent-candidate-s500-200-299.json).
