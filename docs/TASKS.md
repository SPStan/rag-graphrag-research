# Текущая работа и критерии завершения

**E1 status:** 6/6 indexes completed under the structural protocol; physical known tokens=32601955; cost_complete=False; unknown reserve61588 preserved. Final audit/verify completed; monitoring paused.

## Текущая очередь — issue15: техническая подготовка, решение HotpotQA отдельно

- PR37 остаётся Draft/Refs #15. Научные формулировки согласованы по сообщению
  пользователя; это не опубликованное bot/GitHub review.
- Frozen full-experiment.json не изменён: шесть конфигураций,3000IDs,
 1199compatible answers+1sealed failure,1800missing; forecast5841708.693,
 static worst-case114669441 — снимок до исполнения Mu, не актуальный missing-count.
- MuSiQue имеет отдельные budget/continuation разрешения PR38:
 cap5990220tokens/2100POST, unknown не повторяется. Согласие повторно не нужно.
- Для HotpotQA нужен отдельный scoped budget/execution-plan, повторный audit,
 exact reservation и stop до превышения; Mu-согласие не переносится.
- Критерии1/2/4 выполнены; общий бюджетный критерий3 частичен до Hot-решения.
 Запись решения — ADR0028/E2. Манифест/runtime/raw не переписываются.
- Следующий шаг — ревью PR37, затем зависимого PR38; новых запросов здесь нет.

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

**21октября — #13:** исправить Gitleaks false positive SHA, проверить offline;
затем независимый RAPTOR musique/hotpotqa по `issue13-raptor-plan.json`.
Hippo Mu failed2329/5500: второй cycle сохранился после коррекции, третьего POST нет.
Для продолжения Hippo нужен новый проверяемый протокол, не повтор прежней инструкции.
Сохранить все known/unknown, Draft/Refs #13; E2 запрещён до6/6. [Детали](E1_INDEXING.md).

**E1 status:** 2/6 indexes completed; physical known tokens=5386821; cost_complete=False. Last stage=hipporag2/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

**20октября: #13 продолжение после цикла.** Cap3072 прежний, сначала строгая
проба без дубликатов на оборванном payload. Затем bounded fallback≤20/dataset,
все расходы/unknown сохраняются. Кэш обоих run, новый cycle plan; [E1_INDEXING](E1_INDEXING.md).
До реальных шести проверенных индексов E2 заблокирован, #13 открыта/PR Draft.

**E1 status:** 2/6 indexes completed; physical known tokens=4429311; cost_complete=False. Last stage=hipporag2/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

**20октября: продолжение #13 после remote disconnect.** Сохранены1560 passages,
3293 verified responses; расход оборванного POST неизвестен, резерв7922.
Один дочерний Hippo Mu run с replay/новой папкой; прежний20M за вычетом known и
резерва, остаток17150781. Остальные pending строки — из network plan, готовый
Dense не повторяется. [Протокол](E1_INDEXING.md). Никаких E2/merge автоматически.

**E1 status:** 2/6 indexes completed; physical known tokens=4301994; cost_complete=False. Last stage=hipporag2/musique. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

## Исторический блок20октября — #13: шесть индексов и E1

#10/#11/#12 закрыты. Ветка codex/e1-indexing от eab5606; scope до10файлов.
Построить Dense/HippoRAG2/RAPTOR × MuSiQue/HotpotQA по5500 passages,
проверить coverage/load, опубликовать измерения/статусы по [E1_INDEXING](E1_INDEXING.md).
Предел68M новых combined tokens; старые failed/unknown не удаляются.
До реального завершения критериев — Draft/Refs #13, E2 не запускать.
Ниже — история предыдущих блоков.

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

**14 октября: замечание о доступности operator.py выполнено.** Обезличенный
[скрипт](operators/operator.py), [команда и сравнение SHA](RAPTOR_SMOKE.md)
опубликованы; guards проверяются тестом с fake HTTP, без новых модельных вызовов.
Далее актуальное согласие куратора на продолжение с неизвестным историческим
usage; до него tree/reader автоматически не запускать. #12 открыта, PR Draft.

**14 октября: один диагностический summary #12 по прямой просьбе пользователя.**
Run `3525d53a-8a93-4e17-a784-6337feb520a7`: completed, 350 input + 375 output,
read timeout 300 s, retry=0, один POST с исходным payload. [Сводка](../results/summary/raptor-summary-diagnostic.json).
Общий расход по-прежнему неполон: прежний unknown не восстановлен, 52 attempts,
aggregate total=null. Tree/save/reload/три reader-вопроса ещё не выполнены.
Дальнейшие модельные запросы автоматически не запускать; PR Draft, #12 открыта,
согласование куратора и принятие отклонения отдельно. Статусы ниже — история.

**14 октября: #12, контракт уточнён.** Пользователь сообщил context 262144,
output до остатка окна, native Qwen HF tokenizer/template, vLLM 0.29.0.
Первый summary по локальному native tokenizer занимает 350 input + 512 cap,
помещается в окно. Точный server usage не восстановлен; по-прежнему выяснить
исход ReadTimeout до нового расходующего протокола. [RAPTOR_SMOKE](RAPTOR_SMOKE.md).
Не путать локальный подсчёт с измерением расхода; failed run остаётся в учёте.
Новых запросов нет, issue открыта, PR Draft.

## Исторический блок 13 октября — #12: малый RAPTOR

#29 слит (`5e617fa`), #10 закрыта по команде пользователя. #11 отдельно в
Draft PR #30: target context contract неизвестен, OpenIE generation не запускалась.
#12 независима от #11; ветка `codex/raptor-small-corpus` от master. Протокол:
[RAPTOR_SMOKE](RAPTOR_SMOKE.md), решение [ADR-0020](../.adr/0020-raptor-small-corpus-adapter.md).

- Официальный RAPTOR закреплён; 50 synthetic leaves → tree → reload → retrieval
  проверены в изолированном SDK без сети (11 passed).
- Общий offline gate: 235 passed, 14 skipped; SDK test выполняется отдельно.
- Реальный run `bb0b97d2-b0ca-4d09-926c-76d2309b0853` на `2b699a2` failed:
  50 embeddings / 6399 локальных tokens; первый summary ReadTimeout 120 s,
  удалённый usage неизвестен. Дерево/reload/три reader запроса реально не завершены.
- [Сводка](../results/summary/raptor-smoke.json), [Draft PR #31](https://github.com/SPStan/rag-graphrag-research/pull/31), Refs #12.
  Issue остаётся открытой/In Progress. Offline проверки не заменяют реальные
  критерии приёмки; перед новым протоколом устранить timeout и разобраться с usage.
- Далее техническое ревью и согласование O1/N1/R1/H1. Не сливать, не повторять
  расходующие запросы и не запускать full corpus/следующую задачу автоматически.

Статусы ниже — история.

**14 октября: обзор опубликованных методов #25.** Подготовлены [полная таблица](related-work-comparison.md#full-comparison) и [слайдовый вариант](related-work-comparison.md#slide-version) Dense RAG / HippoRAG 2 / RAPTOR с версиями первоисточников и ограничениями. Журнал чтения студента сохранён; новых модельных вызовов нет, реализация RAPTOR не менялась. 15 октября первоисточники повторно сверены; по поручению пользователя PR #32 передаётся в Ready for review. Научное согласование O1/N1/R1/H1 ещё не зарегистрировано; нужно отправить `/research_submit https://github.com/SPStan/rag-graphrag-research/pull/32 25` через бота и получить явное согласие куратора. Эта команда недоступна инструментам агента. До согласования issue/PR не закрывать, merge отдельно. Настройка доски #23 завершена [итогом в issue](https://github.com/SPStan/rag-graphrag-research/issues/23#issuecomment-6170587264), issue оставлена открытой. Текущая экспериментальная работа #12 продолжается отдельно; строки ниже описывают предшествующие этапы.

**14 октября: исправлена проверка task до измерительного запроса.** Общая
валидация attempt/remedial/retry_of_attempt/passage_id/dependency/stage вызывается
до request_fn в measure_then_execute_openie_task и сохраняется в прямом
execute_openie_task. Регрессия некорректных задач подтверждает ноль callback;
целевые executor/offline runner: 16 passed. Новых модельных запросов нет.
PR #30 передан на полное ревью, научные формулировки согласованы карточкой
`e818864b878ccf61af85ef16:1`; ready_for_indexing=false, issue открыта.

**14 октября: should ревью dc7ae635 закрыт.** Эталон SDK берётся из Git blobs
закреплённого коммита, не рабочего дерева; одинаковые dirty source/installed
регрессионно отвергаются до HTTP. Все 61 реальных SDK Python-файлов повторно
подтверждены без API-вызовов. [Проверка](OPENIE_TARGET_CHECK.md). Draft,
ready_for_indexing=false, актуальное согласование/полное ревью отдельно.

**14 октября: технический saved-case OpenIE smoke #11 выполнен.** На `2e46d0a`
run `b1549680-6917-47e4-a614-3540fcda01a6` завершил 5/5 cases: valid_nonempty,
stop, все server prompt_tokens совпали с native. Расход нового run 2535 input /
784 output; 5 POST, без retry/коррекций. Исторический cache/state не изменён.
[Сводка/SHA](../results/summary/openie-target-live-check.json), [до/после](OPENIE_TARGET_CHECK.md).
Далее полное техническое ревью PR #30 и актуальное согласие куратора; PR пока
Draft, #11 открыта. ready_for_indexing=false сохраняется: это не repair всей
очереди/индекса и не оценка эффективности. Не возобновлять старый repair, не
повторять cases/failed RAPTOR автоматически. Блоки ниже — история этапов.

**14 октября: контракт #11 уточнён пользователем.** Общий context 262144,
output до остатка окна, native Qwen HF tokenizer/template, vLLM 0.29.0;
отдельного server count endpoint нет. Пять исходных prompts проверены локально
на закреплённом tokenizer (input+cap 1302–3793):
[таблица/SHA](OPENIE_TARGET_CHECK.md). Старый blocked preflight сохраняется.
Замечание ревью a80e104 выполнено: команда воспроизведения проверена на пяти
prompts; counts/rendered SHA опубликованы в
[безопасном JSON](../results/summary/openie-target-context-counts.json), без текстов.
Далее отдельный ограниченный OpenIE протокол со сверкой server usage и
фактическим до/после; новых модельных вызовов в проверке counts нет.
ready_for_indexing=false, PR Draft, согласование куратора отдельно. Для #12
по-прежнему нужны исход timeout и usage неудачного summary.

**13 октября: следующий шаг #11 по предварительному ревью PR #30.** Получить
deployment context/output limits и точный tokenizer/chat-template либо серверный
счётчик полного messages payload; проверить fit пяти выбранных cases. Публичные
docs/OpenAPI GET — 404, генерация не запускалась. Текст запроса провайдеру и
последовательность проверки — [OPENIE_TARGET_CHECK](OPENIE_TARGET_CHECK.md).
Карточка `eb27b8fa5654329712648d28:0`: H1/N1/O1/R1 не утверждены;
`/research_status https://github.com/SPStan/rag-graphrag-research/pull/30`
выполняется через бота, текущие инструменты этой команды не предоставляют.
Draft/Refs #11 и ready_for_indexing=false сохраняются. Нельзя закрывать issue
или считать offline проверки реальной целевой генерацией.

**13 октября: пользователь поручил issue #11 — ошибки OpenIE HippoRAG.** PR #29 слит (`5e617fa`), #10 закрыта/Projects Done, научное согласование #10 подтверждено пользователем ответом research_status. Текущий блок — до пяти сохранённых development-примеров #11, без возобновления старого repair и без пересборки корпуса. Ветка `codex/openie-target-check` использует существующий SDK-worktree. Read-only target preflight интегрируется в `preflight_hipporag_repair_prompts`; старые артефакты сохраняются. Пользователь подтвердил неизвестные context/output limits и tokenizer/backend revision; API metadata их не сообщает. Генерация OpenIE и индекс не запускаются до проверенного context-fit контракта. Итог и команды — [OPENIE_TARGET_CHECK](OPENIE_TARGET_CHECK.md). Научное согласование #11 отдельно; merge только отдельно. Предыдущие статусы ниже — история.

**13 октября: зависимость #28 разрешена, актуальное согласование #29 ожидается.** PR #28 слит в master (`edc5d28`), issue #9 закрыта, Projects Done. Master интегрирован в ветку #29 обычным merge, чтобы сохранить исходные commit ID фактических запусков и SHA provenance; модельные запросы и raw не повторяются/не изменяются. Итоговый diff относительно master содержит только блок #10. Последнее ревью бота пометило согласование карточки `1d9e259796f6f4e1f28694a8:1` устаревшим: текущие O1/N1/R1/H1 нужно повторно отправить `/research_submit https://github.com/SPStan/rag-graphrag-research/pull/29 10`, затем проверить `/research_status https://github.com/SPStan/rag-graphrag-research/pull/29`. Эти команды недоступны через текущие инструменты агента; согласие куратора не подменять. PR #29 сохранять Draft/Refs #10, issue #10 открытой до актуального согласования и полного технического ревью. Следующие #11/#12 и merge отдельно. Статусы ниже — история.

## Текущий статус 8 октября — issue #10: технический smoke завершён

Одна диагностика установила ложный второй Answer-маркер внутри reasoning; target parser version исправляет его без изменения legacy результатов. Финальные run `2ef2397b-2ec2-4696-a5bd-d55542998b6a` / `291f34e6-6c03-4a66-a0a7-e9e6519ee875` на `4a60f2d` завершили по пять ID и существующую оценку. SHA и полный пофазный расход проверены, исходная ошибка не скрыта: [сводка](../results/summary/dense-target-smoke.json), [команды](TARGET_API.md). Остаются зависимость открытого PR #28, актуальное согласование и ревью PR #29; сохранять Draft/Refs #10 до подтверждения. Следующие #11/#12 и merge отдельно. Исторический блок остановки ниже не является текущим состоянием.

## Исторический блок 8 октября — issue #10: Dense в целевой конфигурации

По поручению пользователя начать следующий PR: проверить цепочку на пяти development ID MuSiQue и HotpotQA, зафиксировать малые корпуса, параметры, usage и ошибки, оценить завершённые результаты существующим оценщиком. План — [dense-target-smoke-plan.json](../results/summary/dense-target-smoke-plan.json), команды и пределы — [TARGET_API](TARGET_API.md). Открытая #9/PR #28 остаётся зависимостью; научное согласование куратора не подтверждено, merge отдельно. Результаты малого запуска не являются научным сравнением. Последующие #11/#12 автоматически не начинать.

Выполнение остановлено на втором MuSiQue reader-ответе; исходные manifest/journal и [сводка](../results/summary/dense-target-smoke.json) сохраняют весь известный расход. PR #29 Draft, `Refs #10`; законченные ответы обоих наборов ещё не получены. До следующего модельного запроса нужно отдельное решение о диагностике reader, а не повтор всего smoke без разбора.

**8 октября: проверка SDK для PR #28 выполнена.** Восстановлено отдельное окружение HippoRAG `1438aba3`; OpenAI `3.26.1` и HTTPX `0.28.1` проверены на подставном HTTP через реальные CacheOpenAI и batch_openie: **9 passed**, 77 пакетов совместимы. Общий offline gate: 207 passed, 13 skipped (девять SDK-тестов выполнены отдельно). Retry=0 даёт одну попытку при ошибке; положительный контроль retry=1 — две. Фазы и passage ID сохраняются в рабочих потоках; кэш не повторяет физический запрос, missing usage отмечает неполноту. Команды — [TARGET_API](TARGET_API.md). O1/N1/R1/H1 согласованы куратором по карточке `54ed244c46d451135bcf444b:1`. PR #28 и issue #9 остаются открытыми; merge только отдельно. Следующий существующий блок — PR #29/issue #10, зависящий от #28; новых модельных запусков в этой проверке нет. Статусы ниже — история.

## Исторический блок 7 октября — issue #9: пофазный учёт токенов

#7/#8 закрыты, PR #26/#27 слиты; куратор принял отклонение #8 без восстановления неизвестного usage. Для #9 подключить устойчивый журнал к существующим Dense/HippoRAG/API smoke, проверить агрегаты, ошибки, retry и кэш без реальных вызовов. Результат — небольшой PR в master с offline-проверками и `Closes #9`; merge только по отдельной команде. Следующие расходующие задачи не запускать автоматически. История ниже не является текущей очередью.

## Исторический блок 6 октября — issue #8: проверка целевого API

После слитого PR #24 проверены локальный BGE-M3 и короткая генерация `iairlab/qwen3.8-27b` по [issue #8](https://github.com/SPStan/rag-graphrag-research/issues/8). Исходный smoke не вернул текст, но отдельная ограниченная диагностика нашла рабочий `chat_template_kwargs` и per-response usage. Результаты и команды — [TARGET_API](TARGET_API.md). PR #26 находится в Ready for review: технических блокеров в ревью нет, научные формулировки согласованы; [куратор принял отклонение от лимита запросов](https://github.com/SPStan/rag-graphrag-research/pull/26). Два случая неизвестного usage не восстанавливаются. После слияния отдельно спланировать проверку JSON/OpenIE перед E1/E2. Не начинать E1/E2 из одного короткого ответа.

## Завершённый блок 2 октября — issue #7: протокол сравнения и ID

Зафиксировать для MuSiQue/HotpotQA исходные S500 и pilot200, таблицу общих условий трёх методов, историю planned/observed ID и отдельные части для сигнала задачи #21. Не выполнять LLM-вызовы и эксперименты. Проверка — `python scripts/freeze_comparison_protocol.py --verify-only --splits-only` в чистом checkout и `--verify-only` там, где есть локальные raw; затем offline check и CI. Критерии и границы — [issue #7](https://github.com/SPStan/rag-graphrag-research/issues/7), [ADR-0015](../.adr/0015-pinned-comparison-and-signal-split.md), [DATA](DATA.md). Прежние задачи ниже — история; после этого блока переход к issue #8 о целевом API.

## Исторический блок 1 октября — лабораторный шаблон в существующем репозитории

Руководитель слил PR #1. Следующий запрос: оставить этот же GitHub-репозиторий,
адаптировать применимые части `nir-project-template` и показать проходящие
проверки. Решение и границы — [ADR-0014](../.adr/0014-adapt-lab-repository-template.md).

1. В тематической ветке добавить `uv`-lock для **отдельной** offline-проверки,
   формы задач/PR, ограниченный mypy и CI-конвенции; не менять исследовательские
   результаты. Завершено, когда чистые Windows/Linux CI и локальный check проходят.
2. Открыть небольшой Draft PR (желательно ≤20 файлов); первоначальное описание
   студент пишет сам. Проверить реальное число файлов, assignee/reviewer/label.
3. Отдельным следующим блоком изучить overlay `v0.1.0`, затем подключить
   применимые инструкции после проверки. Не создавать пустой пакет ради шаблона.
4. [GitHub Project #1](https://github.com/users/SPStan/projects/1) существует,
   переименован в `RAG / GraphRAG Research`, пуст и привязан к репозиторию.
   Преподаватель подтвердил, что сам добавит две двухнедельные вехи и задачи
   примерно на день работы; заранее генерировать их не нужно. Студент отправляет
   боту `/register https://github.com/SPStan/rag-graphrag-research https://github.com/users/SPStan/projects/1`
   и отписывает преподавателю. Доска остаётся приватной; `Resurrectiontent`
   добавлен с ролью Admin, но принятие возможного приглашения, регистрация и
   сообщение ещё не подтверждены.

Сравнение Dense/HippoRAG уже опубликовано как диагностическое; новые модельные
запуски, repair, holdout и целевой API не входят в этот блок. Ниже — история.

## История 29 сентября — подготовка существующего результата к ревью

### Сверка новых памяток преподавателя

| Требование | Фактически | Следующее действие | Готово, когда |
|---|---|---|---|
| Репозиторий, PR и руководитель | Публичный репозиторий, PR #1 переведён в Ready for review 30 сентября; `Resurrectiontent` назначен reviewer, assignee `SPStan`, label `enhancement`; CODEOWNERS пока только в ветке | Получить замечания руководителя и исправлять их в этой ветке | Поля PR проверены, результат и ограничения доступны ревьюеру |
| Проверки кода и секретов | 153 unittest в основной `.venv`; новый gate и Gitleaks прошли [Windows/Linux CI](https://github.com/SPStan/rag-graphrag-research/actions/runs/36628383795); `.venv-check` и локальный pre-commit установлены, `run --all-files` успешен | Поддерживать при изменениях; сохранить подтверждение реального срабатывания на коммите | Одна команда проходит в обоих CI, локальный hook работает в отдельном окружении; найденные секреты не выводятся |
| Агентские инструкции | AGENTS.md и `make check` есть; команда Stop hook прошла ручной запуск без ошибок | Подтвердить доверие и автоматическое срабатывание project hooks в Codex | Не выдаём конфигурацию за работающий hook без фактической проверки |
| Трекинг | TASKS и ADR есть; выполненные эксперименты оформлены в [issues #2–#5](https://github.com/SPStan/rag-graphrag-research/issues) | Подключить обещанный шаблон доски позже, распределить issues по полям/итерациям | Для каждого эксперимента есть итог и безопасный артефакт; поля доски и Admin руководителя подтверждены отдельно |
| Литература | Четыре записи проверены по первичным страницам в [READING](READING.md); студент выбрал Word, чтение не подтверждено | Обсудить Mendeley для Word, затем начать журнал по реально прочитанному | Экспорт BibTeX/RIS с проверенными записями и подтверждённый студентом журнал |
| Целевой API | Доступ и параметры пока неизвестны | Согласовать endpoint, модели, embeddings, лимиты, цены/учёт 90M; подготовить ограниченный пилот | До запуска известны верхний предел расхода, условия остановки и единый протокол сравнения |

Указания о Claude Code и overlay в памятке — примеры/варианты; проект использует
Codex, поэтому формат хуков проверяется по официальной документации Codex.
Контрольная точка для доски и библиотеки уточняется с преподавателем; их отсутствие
не объявляем выполненной работой.

**Завершён:** [CI на чистых Windows/Linux](https://github.com/SPStan/rag-graphrag-research/actions/runs/36628383795)
успешен на `8b795df`: установка, pip check, Ruff lint/format, offline pytest и
отдельный Gitleaks Git-history scan. Следующий
шаг — ревью текущего сравнения; новые model calls не требуются.

Цель: руководитель может проверить код без локальных данных, моделей и ключей.
Решение — [ADR-0013](../.adr/0013-offline-review-checks.md).

- Общая команда `python -m scripts.check`: pip check, Ruff lint/format,
  offline pytest и синтетический путь retrieval → reader → scoring.
- Отдельный lock и Windows/Linux CI; результат чистой копии записывается в
  [VERIFICATION](VERIFICATION.md). Это не воспроизведение модельного эксперимента.
- Исторический provenance опубликован с неизвестными полями, без правки raw.
- Руководитель `Resurrectiontent` имеет write-доступ; CODEOWNERS добавлен в ветку.
  До merge в master правила из этой ветки не считаем действующими в master.

После этого блока: ревью текущего диагностического сравнения. Затем согласовать
параметры целевого API: доступные модели/embeddings, context/output limits,
rate limits и учёт бюджета 90M. До согласования не выполнять новые model calls.
Пилот API: сначала выяснить endpoint, авторизацию, digest моделей, embedding
размерность, context/output caps, rate limits и какие токены входят в лимит.
После согласования — один малый batch из двух embedding inputs и не более трёх
generation requests (короткий factoid, multi-hop с контекстом, ограниченное
завершение). Предлагаемый совокупный предел — **50 000 учтённых токенов**,
включая embedding и выход; если API не отдаёт usage или бюджет нельзя проверить,
пилот останавливается до следующего запроса. Для каждого ответа сохранить
request ID, фактические параметры, usage/ошибку и private raw; в Git — только
безопасную сводку. Это предложение, а не разрешение на запуск.
Dense/HippoRAG
сравнивать на одинаковых вопросах, reader и условиях; holdout не использовать
для отладки. RAPTOR — следующий метод после стабильного API-пилота.

Прочитаны памятки преподавателя papers/tasks/agents/general из
`Industrial-AI-Research-Lab/project-implementation-manual`, ветка
`feat/practice-guides`. Осталось вместе со студентом вести библиотеку статей и
журнал чтения (не выдавать сгенерированные записи за прочитанное). Доску и агентские
артефакты подключить после получения обещанного шаблона. Полная style-проверка
и локальный pre-commit подтверждены; доверие к Codex project hook отдельно.

Разделы ниже — результаты и история, не разрешение возобновлять repair.

## Активное изменение 26 сентября — сравнение вместо дальнейшего repair

Пользователь прямо поручил выполнить Dense RAG против HippoRAG 2 самостоятельно.
По [ADR-0012](../.adr/0012-as-built-diagnostic-comparison.md) завершён QA на
копии уже построенного диагностического графа и тех же 100 candidate ID.
Dense не повторяется, 7B не используется, holdout100 не затрагивается.
Это отдельное диагностическое сравнение; строгий gate остаётся failed.
Получены все 100 ответов: Dense F1 18,58%, HippoRAG F1 29,97%; EM 11% / 20%.
[Отчёт](COMPARISON_2026-09-26.md) и публичная сводка сохранены.
Следующий этап — согласовать целевой API и проверить его малым пилотом;
новые прогоны автоматически не начинаются.
R1–R3 ниже остаются историей ремонтного пути, а не активной очередью.

Актуализировано 25 сентября 2026 после ревью `e7a0367`.
**Это единственная очередь ближайших задач.** Требования исследования — в [SPEC](SPEC.md), история — в [LOCAL_MVP](LOCAL_MVP.md) и [VERIFICATION](VERIFICATION.md).
Начало работы другой модели — [HANDOFF](HANDOFF.md). Причины пересмотра — [ревью](REVIEW_2026-09-25.md).
Предыдущая доска сохранена в [архиве](archive/TASKS_2026-09-25.md); её «следующие шаги» больше не актуальны.
Локальные WORK_PLAN.md и LUNA_REVIEW_HANDOFF.md могут содержать старые очереди; не выполнять их вместо этой.

## Цель и ближайший результат

Исследование: сравнить dense RAG, HippoRAG 2 и RAPTOR по качеству и полной стоимости, затем проверить маршрутизацию. LightRAG — расширение.
Ближайший результат: **сопоставимая таблица Dense / HippoRAG на уже закреплённом candidate S500[200:300]** с ограничениями и доступными затратами.
Новые скрипты, число тестов и коммитов сами по себе не закрывают этот результат.

| Часть | Подтверждённое состояние |
|---|---|
| Локальный стенд, данные, Dense, reader, evaluator | Работают по предыдущим проверкам; повторять установку не нужно |
| Dense candidate100 | Завершён: EM 0,110; F1 0,1858; recall@5 0,6058 |
| HippoRAG candidate100 | Диагностический QA завершён: EM 0,200; F1 0,2997; recall@5 0,6475. Строгий index gate failed |
| Ремонт OpenIE | Первая очередь остановлена после NER attempt 2; отдельная attempt 3 тоже `truncated` на cap 2048. Кандидат остаётся диагностическим |
| Исторический debug10 | Диагностика, использовался при разработке; входит в baseline100 |
| Целевые API/T4, HotpotQA-прогон, RAPTOR, router, cost model, bootstrap | Не завершены; после локального сравнения, по исходному заданию |

Источник чисел и run IDs: [candidate summary](../results/summary/musique-independent-candidate-s500-200-299.json).
Последняя полная проверка кода: 142 unittest (2 pinned-only пропущены в основной .venv); два pinned-only теста прошли в отдельном HippoRAG environment. Это не проверка реального repair.

## Действующие границы

- Ветка `codex/local-rag-mvp`, PR #1 открыт для ревью с 30 сентября. Не сливать автоматически.
- До отдельного разрешения: без LLM/embedding-вызовов, реального repair, пересборки графа и QA; без новых 100-вопросных прогонов, 7B и `holdout100`.
- Можно читать локальные артефакты, менять код и документы, проверять синтетические сценарии без сети.
- Сохранить исходные индексы, raw results, данные сервисов. Не коммитить секреты, базы, корпуса, индексы, веса или private repair outputs.
- Не включать автоматически локальные WORK_PLAN.md, scripts/resume_dense.py и docs/LUNA_REVIEW_HANDOFF.md в коммиты.
- Подагенты только по явному поручению. Общий запрос «продолжай» не отменяет границы выше.

## R1 — Рабочий ремонт и восстановление, без модели

**Статус:** выполнено offline 25 сентября 2026. **Владелец интеграции:** Sol.
**Результат:** один запускаемый offline-сценарий: NER → сохранение extraction → остановка → новый процесс → зависимые triples → итоговый ledger.
Не заканчивать блок на создании очередного неиспользуемого helper.

Использовать существующие planner, executor, journal, merge и state-patch helpers. Исправить замечания F1/F2 из ревью:
- Сохранять успешные extraction values в private checkpoint вместе с идентичностью и SHA; metadata-only журнал не восстанавливает entities/triples.
- Помечать задачу завершённой только после надёжной записи результата. После ошибки записи не продолжать на изменённом состоянии в памяти.
- Восстановление использует сохранённые outputs и не вызывает callback для выполненной задачи; неизвестный исход in-flight не повторяется автоматически.
- Зависимые triples используют новые entities и точную успешную NER attempt. При неуспешном NER останавливаем этап, не подставляем старые entities.
- Зафиксировать один writer. Проверять сохраняемые поля task до записи, а не только metadata после запроса.
- Первый проход — замороженные 196 задач: 38 NER, 158 triples, две из них уже attempt 3. Любая дополнительная очередь — отдельная явная ревизия плана по ADR-0008, без скрытых повторов.

**Готово, когда:** один интеграционный тест с fake transport проходит после настоящего закрытия/повторного открытия checkpoint; доказывает восстановление values, отсутствие повторного callback, правильную зависимость triples, отказ при повреждении результата и неизвестном исходе запроса. Source fixtures не меняются. CLI/dry-run или тестовая команда записана; один содержательный коммит.

Проверка R1: `.\.venv\Scripts\python.exe -m unittest tests.test_run_hipporag_repair_offline tests.test_hipporag_repair_journal -v`. Private checkpoint содержит values и SHA в одной атомарной записи; публичный результат должен содержать только агрегаты и хэши. Сценарий использует fake callback, закрывает и вновь открывает checkpoint; реальные model requests и rebuild не выполнялись. Закрытый процесс освобождает блокировку writer; unknown in-flight и повреждённые values запрещают resume.

## R2 — Проверенные запросы и сборка графа, без реального индекса

**Статус:** синтетический graph path выполнен offline. Совместимый API Ollama отбрасывает `num_ctx` и заблокирован; native `/api/chat` для измерения и extraction использует общий offline-проверенный payload. Реальный транспорт и repair не проверены. **Владелец:** Sol.
**Результат:** offline-интеграция с закреплённым HippoRAG, которая строит маленький синтетический граф на исправленных данных и не обращается к модели.

- Связать preflight с фактическим транспортом: проверять model/digest, seed, temperature, num_ctx, output cap и JSON mode в захваченном исходящем payload. Совпадения двух словарей отчёта недостаточно.
- Убрать выдуманное `transport_attempt_count=1` для ошибок, возникших до отправки; сохранять известное/неизвестное честно.
- Переиспользовать `install_no_truncate_embedding_api` и существующий validate/usage код; не писать второй HTTP-слой. Проверить, что split/retry не теряет usage уже выполненной части.
- Добавлять только недостающие entity/fact embeddings, сохранять совпадающие и исключать устаревшие в копии. Проверять exact IDs и связь checkpoint values с ledger.
- Копия со старым graph.pickle и index_manifest ещё не готова. Явный статус `graph_pending`; новый graph + новый manifest + SHA до допуска к QA.
- Использовать pinned graph path на синтетическом корпусе с fake LLM и готовыми векторами; неожиданный сетевой вызов должен завершить тест ошибкой.

**Готово, когда:** единый синтетический repair → vectors → graph → gate сценарий проходит, старый граф не может быть принят как исправленный, параметры запроса подтверждены transport stub. Это не разрешение на real rebuild.

Проверка R2: `$hippoPython = Join-Path $env:TEMP 'hipporag2-1438aba3-venv\Scripts\python.exe'; & $hippoPython -m unittest tests.test_pinned_repair_graph -v`. Тест восстанавливает NER из checkpoint, проводит зависимый triple, подаёт готовые векторы в закреплённый `HippoRAG.index` и закрывает graph gate. Fake LLM и embedding запрещают неожиданный вызов. Старый тест захвата payload pinned `CacheOpenAI.infer` не подтверждает применение `num_ctx` сервером; он требует пересмотра. Copy helper оставляет проверенный `index_manifest` конфигурации, необходимый pinned constructor для открытия сохранённых векторов, удаляет старый graph и держит `graph_pending`. Новый SHA графа публикуется в repair provenance после проверки exact IDs; копия старого графа отклоняется. Контракт выбора manifest записан в ADR-0009.

## R3 — Контекст и конкретное предложение запуска

**Статус:** native transport и GPU проверены на ограниченном запуске; NER attempt 2 и отдельная attempt 3 обе завершились `truncated`. Полный context fit и repair не завершены; кандидат заблокирован до методологического решения. **Владелец решения:** Sol.
**Результат:** короткий проверяемый протокол вместо очередного общесловесного readiness-отчёта.

- Полный context fit остаётся непроверенным: измерены только два фактических NER prompts. Зависимые triple prompts измеряются после сохранения успешного NER и прямо перед extraction.
- Не ослаблять guard и не повышать caps без решения по ADR-0008/0010.
- Первый bounded run остановлен после первого unresolved результата. Checkpoint не возобновлять и не обходить повтором; сначала согласовать новую политику и путь для truncated attempt.
- Embeddings, graph rebuild и QA остаются отдельными стадиями с отдельным разрешением.

**Результат попытки 25 сентября:** исполняемый runner и команда внесены в [R3_RUN_PROPOSAL](R3_RUN_PROPOSAL.md). Offline dry-run подтвердил 196 задач и SHA семи источников; целевые 24 unittest прошли. По явному запросу пользователя выполнено 4 native chat POST для двух NER задач; Ollama подтвердил выделение GPU VRAM. Первая задача `valid_nonempty`, вторая `truncated` на cap 1024. Checkpoint остановлен, SHA `83f61962940c06c912ff0c595a8617be298698b802151bc50d8136d2ef331d13`. Автовозобновление запрещено. Cap/retry policy требует пересмотра по ADR-0008 перед любым дальнейшим вызовом. Embeddings, graph rebuild и QA не выполнялись.

**Подготовка remedial attempt 3:** по решению пользователя в [ADR-0008](../.adr/0008-openie-truncation-retry-policy.md) закреплён один NER attempt 3 с cap 2048. Новый режим `--remedial-ner` читает остановленный checkpoint по точному SHA, проверяет семь исходных SHA и строит отдельную однозадачную очередь; старый checkpoint не изменяет. Offline dry-run прошёл, 23 целевых теста прошли. GPU-запуск остаётся за Luna; в этом чате новых model requests не было.

**Результат remedial:** Luna выполнила одно измерение и одну extraction; NER attempt 3 снова `truncated` (`finish_reason=length`, 334 input / 2048 completion). Новый checkpoint `stopped/unresolved_extraction`, SHA `1cf000239921f3dc36d4a879e5defe355c8ecbb7afc7e092bc31a193c8c57275`; исходный SHA не изменился. Частичные values не приняты. Повторять этот запуск, добавлять attempt 4, продолжать основную очередь, строить граф или запускать QA нельзя. Следующий блок — решить, фиксировать этот локальный кандидат как заблокированный или описывать новую extraction-стратегию как отдельный вариант исследования; выбор до новых model calls записать в ADR.

**Следующий вариант подготовлен offline:** [ADR-0011](../.adr/0011-local-openie-extraction-variant-proposal.md) предлагает отдельно проверить установленный Qwen2.5 7B на том же NER passage — максимум два native запроса, без принятия результата в старый ledger. Режим `--probe-7b-ner --dry-run` прошёл в pinned environment, fake transport подтвердил два запроса и сохранение только диагностических полей. Это только probe; полный 7B-индекс не разрешён. До отдельного решения пользователя никаких model/embedding вызовов и QA.

Способ, результаты и границы запуска: [R3_RUN_PROPOSAL](R3_RUN_PROPOSAL.md), решение: [ADR-0010](../.adr/0010-context-measurement-proposal.md). Два прежних пилотных prompt имели 691 и 1003 input tokens. Первый repair-run измерил ещё два NER prompt (473 и 334); второй completion занял весь cap 1024 и завершился `truncated`. Для этих запросов native transport и GPU размещение подтверждены, остальные prompts не измерены. Текущий context guard не ослаблен.

## После разрешения, не выполнять сейчас

1. При необходимости — отдельно разрешённая ограниченная проверка контекста.
2. Точечный repair в новом namespace; сохранить каждый результат. При unresolved outcomes — остановка с отчётом, без полного rebuild «на всякий случай».
3. После разрешённой пересборки и успешных extraction/vector/graph gates — отчёт готовности QA.
4. Только после отдельного разрешения на 100 QA: HippoRAG на тех же candidate IDs и общем reader. Сохранённый Dense candidate повторять без причины не нужно.
5. Парная таблица EM/F1/recall, ошибки, времена и известный usage; интервалы по сохранённым ответам. Не восстанавливать отсутствовавшую стоимость задним числом.
6. Вернуться к RAPTOR, целевым API/T4 и HotpotQA, затем cost model, oracle и router по SPEC. Сокращение исходного исследования согласовать с руководителем.

## Как не повторить прежний цикл

Один активный блок. В конце — демонстрируемый результат, проверка, один следующий шаг.
Luna не перепланирует исследование и не читает все архивы; при двух безрезультатных попытках исправить одну ошибку передаёт Sol краткое воспроизведение.
Тесты — целевые для изменения, полный набор на границе блока; не повторять без новых изменений.
Обновлять TASKS и соответствующее доказательство, а не все документы после каждого helper.
