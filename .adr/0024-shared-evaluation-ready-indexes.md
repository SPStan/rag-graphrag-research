# ADR-0024: общий reader на готовых E1 индексах

Дата:25 октября2026. Статус: offline реализация; exact smoke10 разрешён пользователем
и остановлен на первом reader length (2completed/1failed). Continuation не разрешён.
Refs #14; зависит от PR33/f8b9bb8. Протокол smoke — [E2_EVALUATION](../docs/E2_EVALUATION.md).

## Контекст и выбор

Шесть E1 индексов completed, но shared loader не загружал Hippo. SDK constructor
создаёт mutable stores/locks/OpenIE; использовать его для query-only чтения нельзя.
Выбран тонкий QueryOnly adapter: проверенные artifacts → родной read-only Parquet
loader/graph → native prepare_retrieval_objects в RAM → native fact scoring,
DSPyFilter и PPR. Constructor/index/OpenIE/store writes исключены. Rebuild/копия
всех индексов не нужны; реализация собственного поиска/PPR исказила бы SDK.
Native valid-empty filter сохраняет DPR fallback; transport/parser failure fatal,
поскольку SDK иначе маскирует их под empty. Содержательные ошибки retrieval не
лечатся prompt retries. Reader/parser/evaluator едины и уже существуют.

## Последствия

Общий reader использует существующий MuSiQue one-shot на обоих наборах; это
раскрытая неоптимизированная Hotpot конфигурация. Top5 RAPTOR nodes возвращаются
без дополнительного прежнего 3000-token отсечения; после retrieval общий предел
messages32000UTF8 bytes, overflow=stop. RAPTOR passage recall не сопоставим с
Dense/Hippo: только provenance coverage отдельно. Byte gate не native tokenizer.

Query LLM только Qwen, filter512/reader512/temp0/seed42/thinkingfalse. Existing
Qwen/GPT extraction E1 не переименовывается и не пересчитывается; выводы относятся
к конкретным конфигурациям с observed extraction errors. Native query embedding
instruction_mode=ignored совпадает с E1 BGE; один normalized vector для facts и
passages внутри Hippo. Отдельные query embeddings на каждом method/question
позволяют измерять actual query latency/cost без cross-method cache ускорения.

Canonical plan claim, exact payload checkpoints и durable journal исключают
повтор при неизвестном исходе. Успешный replay физически бесплатен; логическая
стоимость и исходная latency сохраняются отдельно. Failed/not-attempted не
исключаются из знаменателя. Verification read-only, export отдельный.

## Проверка и пересмотр

Synthetic tests: gold isolation, common prompt, incompatible pins до HTTP,
reported usage/time на errors, безопасный replay и запрет uncertain resume.
На обоих real Hippo графах проверены PPR/DPR и исходный PermissionError; index/
constructor/HTTP запрещены, SHA artifacts до/после совпали. Dense/RAPTOR на обоих
наборах возвращают top5, для nodes проверены levels/provenance, HTTP запрещён.
Ни одна из этих проверок не является QA benchmark. Изменение reader/top-k/options/
SDK/evaluator/index pins делает результаты несовместимыми; отдельный план до
новых запросов. Критерии не меняются из-за неверных ответов smoke.


## 25октября: continuation v2 — reader outcomes отдельно от fatal execution

По прямому поручению после исходного stop принимается offline policy
`reader_known_response_failure_continue_v2`. Исполнение требует отдельного допуска
нового exact plan, прежнее разрешение этого изменения не покрывает.

Known-usage завершённый HTTP reader response с length/empty/непригодной формой/
неприменимым parser — attempted_failed, answer не принимается, повторного POST нет.
Другие случаи продолжаются с теми же cap512/prompt/temp0/seed42/thinkingfalse.
Отсутствующий usage, HTTP/transport/infra error, изменённые pins/config или бюджет —
fatal stop. Эта политика не переносится на Hippo filter: length, malformed и error
там fatal; valid empty facts сохраняет native DPR. Semantic correctness не определяет
retry; gold читает только evaluator после generation.

Original failed manifest/claims/журналы/ответы остаются у parent. Child pin-ит19файлов,
сверяет scientific contract и AST неизменённых reader/embedding payload functions
с5dea658; immutable retrieval/evaluator/SDK/data pins прежние. Старые три случая
(2completed+1knownlength) пропускаются целиком, не выдаются за новый cache hit под
изменённым prompt. Фактические source options/run/code/response SHA сохраняются.
Допускается один child из этого parent, новый output/journal/run, без снятия общего
запрета повторного запуска failed. При успешной технической паузе одного child
повторный вызов пропускает terminal cases; unknown/failed не ретраится.

Остаются57cases:57query embeddings+57reader+≤20filter=134POST. Conservative reserve
77×(32000+1024+2048+512)+57×(4096+1024+2048)=3148544tokens≤3271113остатка.
С учётом parent:≤140POST, known5687+новыйreserve≤3154231≤3276800.
Bound не actual usage и не денежная цена; local embedding/LLM input/output отдельны.

Completed, attempted_failed и not_attempted различаются. Только attempted failures
имеют EM/F1=0; not_attempted получает null и делает сравнение неполным. На завершённом
smoke denominator=10/cfg, failures входят; публикуются failure rate, mean attempted
latency и usage by model. Parent+child journals суммируются один раз по physical
identity,60case keys включают dataset/method/question. E1 historical cost_complete=false
и reserve61588 остаются отдельной атрибуцией. RAPTOR provenance не passage recall@5.

Проверки: actual parent/all6source manifests/artifacts offline, synthetic existing
runner/CLI на60cases, success+reader outcomes+resume; parent SHA/config/model/unknown/
budget/transport rejection, filter fatal, no duplicate expense. Новых real calls нет.
После реального smoke — одно решение: freeze reader для pilot200 либо единый пересмотр
для всех методов при технической проблеме; не выбирать конфигурацию по лучшему F1.
