# Передача контекста Sol / Luna

**E1 status:** 4/6 indexes completed; physical known tokens=16707393; cost_complete=False. Last stage=hipporag2 native schema continuation. Raw/indexes remain local. PR Draft; E2 requires all six verified indexes.

## Текущая очередь — 22 октября: GPT-OSS план и offline E2 preparation

- E1 остаётся4/6; known16707393/upper16762447,cost_complete=false. Старый unknown55054
  сохранён. Mu остаток15038920, Hotpot20M; новых model/embedding запросов0.
- Последний Hippo cycle/length подтверждён; причина неизвестна. Exact payload
  восстановлен pinned SDK; новой клиентской ошибки не найдено. Ответ оператора
  полезен, но не блокирует независимую offline-подготовку/ограниченную диагностику.
- Подготовлен один GPT-OSS вариант: low reasoning, без enable_thinking, та же shape
  schema/cap3072/temp0/seed42. Куратор заявил context131k/JSONSchema/reasoning,
  deployment ещё не проверен.5фиксированных случаев:3failed+2cached controls.
- Максимум5POST, резерв44124 из15038920, NER/embedding0, retry0, timeout30/300.
  Первая ошибка/unknown/length/partial/cycle → stop. Затем обязательный source review
  всех5 без gold/точного совпадения. Успех не разрешает full continuation.
- Предложение ADR-0023 отделяет диагностику от смены benchmark и mixed cache.
 3102полных Qwen пары сохраняются под своей моделью; решение об их reuse отдельно.
- Четыре готовых Dense/RAPTOR загружены read-only; native retrieval и общий reader/
  evaluator проверены synthetic/cache без HTTP; SHA старых manifest/journal
  неизменны.118targeted passed/2SDK-skipped, native SDK проверены отдельно.
  Это подготовка, не QA/E2.
- Следующий шаг: завершить gate/commit/push, зафиксировать exact private plan SHA и
  получить одно согласие на эти5POST. Полный E2/корпус/merge не разрешены.
- Архив оператора уже существует, не пересоздавать/не отправлять без адресата и
  явного разрешения. PR33Draft/Refs #13. Детали и критерии — E1_INDEXING.

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
