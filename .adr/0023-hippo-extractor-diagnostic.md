# ADR-0023: диагностика другого extractor отдельно от benchmark

Дата:22 октября2026. Статус: **протокол принят по сообщению пользователя**
«Куратор не против» для предложения на17e7045; независимый статус карточки
O/N/R/H не проверен. Новые расходы требуют отдельного допуска. Связь: ADR-0022, issue#13, Draft PR#33/Refs #13.

## Конкретное предложение для согласования: Qwen primary / GPT-OSS fallback

Принят путь C ниже: смешанный extractor и source-only аудит observed errors.
Источник согласия — сообщение пользователя, без отдельной ссылки на решение
куратора. Прежние strict semantic gates остаются failed. SPEC содержит явное
исключение для этой конфигурации; новые HTTP этим согласованием не разрешены.

### Основание: одинаковая приёмка обеих моделей

В issue#13 требуются проверяемые шесть индексов, coverage/load, учёт ошибок и затрат.
Отдельное требование безошибочности всех triples там не записано. В текущем SPEC
закреплена одна плановая Qwen LLM для всех методов: GPT fallback меняет это условие.
Строгий source-fidelity gate был зафиксирован до GPT-проб и обе пробы его не прошли;
это не отменяется задним числом и не означает ошибку проверки.

Сейчас offline перепроверены четыре полных Qwen ответа на тех же известных sources,
не новая выборка и не оценка precision. Journal/producer/response SHA сверены:

| Source | Qwen response SHA (префикс) | Наблюдение по исходному тексту |
|---|---|---|
| Cubs | acd9d738f1ca612d | standalone wins2015 World Series без film qualifier |
| Northwest | 2b56e5f89eaef749 | Passage поставлен субъектом prevented shipping |
| Valencia | 1abdf7846e3d434f | утрачены some/supposedly |
| Kobe | a5702cb7fb2e3a31 | 62triples→14unique; counts/years не сохранены в graph-set |

Private evidence b011725e6a702319c36635dcf2697a9a7385265f261f2a350c0dd6259b685e39
хранит source/request/producer/response pins. Старый adoption record прямо говорил
semantic_support=not_established. Его принятие касалось native graph-set, не истины
всех фактов. Следовательно нельзя переносить уверенность в3102старых Qwen pairs
на source fidelity, а GPT оценивать как будто baseline уже безошибочен. Это основание
обсудить единый протокол, не доказательство равной точности или превосходства GPT.

### Предлагаемая конфигурация и границы fallback

- Обоим датасетам одна именованная конфигурация
  `hipporag2_qwen_primary_gptoss_length_fallback_source_v1`.
- Qwen NER1024 и triples3072: прежние messages/options/schema, temp0/seed42,
  enable_thinking=false. Reader остаётся общим Qwen; BGE-M3 и данные прежние.
- GPT-OSS120b только triples после Qwen `finish_reason=length` и существующего
  diagnostic triple_cycle=true:≥12tuple fragments и unique×4≤fragments.
  Он использует полный исходный passage/cached NER, source_faithfulness_v1,
  shape schema без uniqueItems, low reasoning, cap3072, без Qwen-specific options.
- Не применять fallback для произвольной semantic ошибки, HTTP/timeout, unknown,
  invalid NER или обычного length без подтверждённого цикла. Эти случаи stop.
- Один GPT fallback на original Qwen request identity, максимум20разных original
  failures/dataset, без corrective retry/нового NER. Точное replay полного совпавшего
  policy response занимает один fallback slot, но не новый физический POST.
- Полный stop JSON с literal duplicates не равен незавершённому циклу: штатный
  SDK ordered_unique сохраняется, raw/counts/dedup публикуются. Повторяющийся хвост
  отмечается для source audit; legitimate multiplicity (Kobe) не считается циклом
  только из-за числа одинаковых полных triples. Partial/length не дописывать.

### Технические блокеры и обязательный аудит — разные статусы

Останавливают запуск: неверная provenance/SHA/модель/корпус, исчерпание reservation,
незавершённый/повреждённый журнал, неизвестный новый usage, HTTP/transport error,
невалидные NER/triples, неподходящий length, неудачный или пустой GPT fallback,
исчерпание20fallback slots, несовместимые embeddings/coverage или reload failure.
Старые historical unknown сохраняются в aggregate и уже зарезервированном бюджете;
их наличие не переименовывается в новый неизвестный ответ.

Статус Qwen valid_empty, поддержанный pinned SDK, не объявлять автоматически
ошибкой JSON: отдельно проверить source/coverage, записать отсутствие entities/facts
и результат разбора. Нерешённый empty/warning блокирует приёмку; законный empty
не заменяется придуманными triples. Для GPT fallback непустой ответ по-прежнему обязателен.

В предлагаемом протоколе отдельные semantic ошибки полного структурно пригодного
extraction записываются как **observed errors**, без ручной правки graph edges и
без semantic retry. Это явное изменение критерия. Такой индекс может быть только
`structurally_verified_with_observed_extraction_errors`, не semantic_verified.
Достаточность этого для допуска к будущему E2 — предмет согласования; сам E2
по-прежнему требует отдельного плана и всех шести проверенных индексов.

Source audit обязателен перед приёмкой E1, без gold/QA labels/модельного judge:

1. Разобрать все structural warnings/repetition flags и раскрыть выводы. При
   нерешённой возможности испорченного/незавершённого extraction run не готов.
2. На каждом датасете отдельно выбрать до8Qwen и до8GPT passages. Eligible pool:
   уникальные source IDs, реально представленные этим producer/model в индексе;
   исключить5калибровочных MuSiQue IDs из проб, их результаты публиковать отдельно.
   Ранжирование SHA256 UTF-8 строки `e1-source-audit-v1|42|dataset|producer_model|source_id`,
   взять первые8. Если pool меньше8 — все; если0 — stratum absent, не выдумывать данные.
3. Проверить все triples выбранных passages по полному source: unsupported relation,
   attachment, attribution/negation/uncertainty, dates/counts, существенные omissions.
   Допускается needs_review вместо неподтверждённого verdict. Сохранить source/
   request/response SHA и evidence; counts по категориям, review и stratum sizes.
4.8/stratum — лимит ручного объёма≤16passages/dataset, не требование≥X%accuracy.
   Процент принятия не подбирается по2/5диагностике. Выборка маленькая и стратифицирована:
   не выдавать её за corpus precision/качественный рейтинг моделей или эффективность RAG.
5. Не исправлять и не удалять неудобные triples/пасcажи вручную. Нерешённые semantic
   flags раскрыть; не выдавать наличие аудита за отсутствие ошибок. Отчёт завершён,
   если все выбранные случаи прочитаны/классифицированы, а не если ошибок0.

### Cache, стоимость и сопоставимость

-3102полных compatible Qwen NER+triples сохраняются под исходной моделью/request SHA.
  Они structurally compatible; semantic качество всей совокупности не установлено.
- GPT responses не переименовывать в Qwen и не использовать при наличии полного
  совместимого Qwen primary. Для известного Popper length возможен replay полного
  source-policy response без нового POST, только после отдельного adoption record:
  original Qwen failure→source/NER→GPT payload/response SHA/model/policy.
- Старые strict failed manifests/reviews948ac856/392ff920 immutable. Новый adoption
  означал бы принятие по другому протоколу с observed errors, не пересмотр старого verdict.
  Отдельный structural adoption подготавливается в новом mixed plan;
  это не semantic acceptance и не изменение отрицательного review. Неполный Qwen JSON не становится graph input.
- Cache/graph identity включает policy version и реальные модели. В E1 отдельно
  показать primary/fallback requests/passages, physical/replay, costs по моделям,
  diagnostics/failed/unknown и audit. Запросы не оплачиваются/не начисляются повторно.
- Новый graph и embeddings изменившихся entities/facts строятся отдельно; совместимые
  unchanged chunk vectors reuse только при полном совпадении входа/model/SHA.
  Dense/RAPTOR×4 не пересчитывать. Сравнение смешанной конфигурации не изолирует
  чистый эффект архитектуры HippoRAG; одинаковый reader этого ограничения не снимает.

### Следующий разрешаемый объём — ещё не план запуска

Сохраняются верхние денежные/token allocations: новые combined Mu≤15025625,
Hotpot≤20000000, без восстановления потраченных13295GPT tokens и unknown55054.
После cache при прежнем baseline максимум primary Mu4794POST; до20fallback даёт
консервативный Mu≤4814внешних LLMPOST. Cold Hotpot≤11000primary+20fallback=11020.
Это **предлагаемый** предел с явными20дополнительными POST, а не прежнее разрешение
11000; cache/replay уменьшают actual. Общий новый POST guard≤40000/dataset с embeddings.
Финальный reservation/лимиты стадий и actual remaining пересчитать по всем журналам
до исполнения; если не помещаются — остановиться, не расширять токены автоматически.
Все request connect30/read300, retry0; любая новая ошибка/unknown останавливает очередь.

Сейчас model/embeddingPOST0. Existing runner реализует routing/replay/claim,
учёт каждой модели и обязательный audit gate. Новый plan готовится только на
clean HEAD; разрешение исполнения проверяется по точному SHA. После build
статус indexed_pending_audit, после source review — structurally_verified_with_observed_extraction_errors,
semantic_verified=false. До завершения Mu audit Hotpot не запускается.
Сохраняются immutable build snapshot, старые failed/negative reviews и расходы.

### Область согласования

Пользователь передал «Куратор не против» для конкретного предложения на17e7045.
Это принято как сообщённое согласие на mixed cache/конфигурацию/аудит; не как
проверенный статус текущих O/N/R/H в боте и не разрешение будущих расходов.
Отдельный допуск exact plan нужен по ADR-0022. Ожидание оператора не является
блокером offline-реализации. Оценка3часа не подменяет измеренное рабочее время.

## Контекст

Hippo Qwen повторил cycle/length после uniqueness prompt и shape schema.
Причина неизвестна, новой клиентской ошибки при offline-аудите не найдено.
Готовы Dense×2/RAPTOR×2;3102полных Qwen NER+triples сохранены и не являются
готовым Hippo graph. Ожидание оператора не требуется для offline-подготовки.

## Предлагаемое решение

Один ограниченный source-only diagnostic iairlab/gpt-oss-120b:3известных failed
passages и2фиксированных successful controls, максимум5POST/44124 reserve,
cap3072, temperature0/seed42, reasoning_effort=low, shape schema без uniqueItems,
без Qwen chat_template_kwargs, без retry/нового NER/embedding. Точные identities,
бюджет и stop/semantic gates зафиксированы в E1_INDEXING и private prepared plan.
Заявленные куратором context131k/JSONSchema/reasoning — не измерение deployment.
Параметр low соответствует [vLLM GPT-OSS recipe](https://github.com/vllm-project/recipes/blob/main/OpenAI/GPT-OSS.md);
это источник выбора параметра, не доказательство поддержки на нашем endpoint.
Не создавать Harmony/template вручную: endpoint получает messages.

Перед POST нужны отдельное согласие пользователя, clean pinned HEAD и plan SHA.
Machine success → awaiting_source_review всех5 по исходному тексту; JSON-only
success не принимается. Любой отказ/unknown/length/недостоверное содержание
останавливает план. Скрытого перехода к full corpus/следующей модели нет.

## После разрешённой диагностики: источник и область утверждений

Пять GPT-OSS ответов дали полный JSON/stop/known usage6105, но source review
не прошёл. Это не доказывает качество модели или исправление Qwen cycle.
Диагностика разрешена пользователем отдельно и исполнена; смена benchmark остаётся
предложением. Старые ответы/manifests immutable, GPT cache не принят в Qwen.

Одна offline policy source_faithfulness_v1 добавляет system rules: attribution,
uncertainty/negation/quantifiers, disjoint dates, correct modifier attachment,
no outside repairs. Она не содержит исправленных triples/QA gold или особых правил
для конкретных имён. Применимость к пяти замечаниям проверена source-only;
действие инструкции на генерацию не измерено. Один общий вариант обоим датасетам.

run_e1 prepare-extractor-policy проверяет происхождение отрицательного review и
готовит exact payload candidate; новая request identity сохраняет изменение prompt.
Candidate намеренно не исполняется существующим transport. Следующий вариант
потребует отдельного executable plan/claim, допуска расходов и решения о cache;
подготовка не расходует предложенный reserve48929 и не разрешает новый POST.
После повторного semantic failure — разбор протокола вместо новых prompt retries.

## Техническая готовность одного source-policy follow-up

Отдельный executable proposal hippo_extractor_policy_probe_v1 готовит те же payload,
что проверенный candidate10e82514, и использует existing execute_schema_probe.
Новый output/run, canonical exclusive claim у предыдущего GPT producer и проверка
negative review/parent budget запрещают повторные дочерние попытки между output
folders. Aggregate export включает обе GPT-пробы/старый history ровно один раз;
unknown сохраняется. Transport retry0/timeout30/300/cap3072,5POST/48929reserve.

Это только механизм исполнения после отдельного разрешения точного plan SHA/HEAD.
Old offline candidate не разблокирован. Пока POST0, policy generation не проверена.
После успеха всё ещё необходим source review всех5, решение benchmark/cache и
отдельный continuation plan/расходы. После semantic failure не вводить следующий
prompt retry без разбора причины и принятого изменения протокола.

## Итог разрешённого follow-up: смена benchmark не принята

Plan614b9318/runtime73ab428, run81df270e:5POST/7190known tokens, все stop/full JSON,
новый unknown0. Поправлены fiction attribution и disjoint dates на двух случаях;
неподтверждённый modifier attachment и параллельные qualified/unqualified edges
остались. Strict source review не пройден; private review948ac856, details E1_INDEXING.
Производящие manifests не изменены, GPT ответы не приняты в Qwen cache.

Два содержательных отказа завершают этот prompt-fix путь. Нового sampling/cap/
prompt перебора не предлагаем. Следующий выбор — сохранить строгий gate и4/6
либо отдельно предложить приёмку явно шумного extractor с source audit. Последнее
меняет критерий и конфигурацию SPEC; необходимо upfront решение о допустимых
ошибках, единых правилах обоим датасетам и cache, актуальное O/N/R/H и отдельный
continuation budget/допуск. Текущее отрицательное заключение не заменяется успехом.
Это протокольный выбор, не обязательное ожидание оператора. Ни один вариант
benchmark ниже этим результатом автоматически не принят.

## Решение о benchmark после пробы — ещё не принято

A. Сохранить исходный единый Qwen extractor:3102пары reuse при точных request/SHA,
но подтверждённого исправления Qwen пока нет. Нельзя возобновить его вслепую.

B. Явная конфигурация Qwen NER + GPT-OSS triples (одинаково обоим датасетам).
Это hybrid extractor, а не прежний Qwen benchmark. Нельзя просто подмешать
GPT triples в Qwen identity. Для однородной такой конфигурации потребуется заново
извлечь triples всех passages, включая3102старых; совместимый Qwen NER reuse.

C. Qwen primary + GPT-OSS fallback только после определённого length/cycle.
Это **смешанная** конфигурация. Старые3102Qwen пары можно сохранить лишь при явном
принятии mixed cache и одинаковой fallback policy обоим датасетам. В каждом cache
entry — реальная producer model/request/response SHA и provenance. Диагностика
сама не выбирает C и не доказывает прежнюю сопоставимость с Dense/RAPTOR.

D. Полностью GPT-OSS OpenIE (NER+triples): новые NER и triples всех5500на датасет,
до11000LLMPOST/dataset до любых ошибок. NER этим diagnostic вообще не проверен.
Нужен отдельный проверенный контракт/бюджет. Старый Qwen cache не переименовывать.

После выбора B/C/D граф строится заново из принятых полных extraction; embeddings
изменившихся entities/facts пересчитываются. Exact unchanged chunk/vector inputs
можно reuse только при SHA/model/dimension совместимости; newline→space Hippo
не даёт права автоматически подставить Dense vectors. Готовые Dense/RAPTOR не
пересчитывать без конкретного изменения их собственных входов/параметров.
Failed/probe/unknown сохранять в physical cost, исторический unknown не становится0.

## Альтернативы, последствия и проверка

Поднимать cap/дописывать partial/дедуплицировать незавершённый JSON отвергнуто:
это не исправляет цикл и пропуски. Перебирать sampling параметры без основания
или новую holdout выборку не планируем. Архив оператора уже есть; его отправка
требует адресата/отдельного разрешения и не заменяет source review.

Offline gates проверяют noHTTP, claim once, exact reconstruction/SHA,5POST cap,
first-error stop, actual model journal, unknown reserve, no double physical cost,
read-only load4готовых индексов и synthetic retrieval→common reader→evaluator.
После успешной диагностики сначала отдельное решение конфигурации/согласование
O/N/R/H по BOT_REVIEW_WORKFLOW, затем bounded continuation plan/разрешение.
Полный E2 требует6готовых проверенных индексов и отдельного допуска.
Пересмотр: фактическая несовместимость GPT payload, неполный/неподдержанный source
extraction или принятый другой исследовательский протокол; автоматического перебора нет.

## 23 октября: GPT length после Qwen fallback — новое предложение

Hotpot31005856 остановлен: GPT low/cap3072, input960/output3072, content=null;
причина неизвестна, payload SHA восстановлен без клиентского расхождения.
3предыдущих fallback complete не делают четвёртый пригодным. Не принимать
partial/empty, не читать reasoning как extraction и не повышать cap вслепую.

Предлагается одна диагностическая замена response_format schema→json_object,
без изменения prompt/low/cap/model.1POST/reserve9622, canonical отдельный claim,
stop на первом failure/unknown, строгая local shape+source review. Точные SHA
и интеграция existing runner описаны в docs/E1_INDEXING.md. Сейчас HTTP0.
Это предложение, не принятая поправка benchmark: текущий протокол разрешал
один GPT fallback, он уже израсходован. Успех пробы не разрешает ни второй
fallback в индексе, ни изменение кэша, ни full continuation. Перед переносом
в benchmark нужны отдельное решение об этом исключении для обоих датасетов,
новый child/new output/lineage, все costs/unknown и отдельный допуск расходов.
