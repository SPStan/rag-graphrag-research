# ADR-0024: общий reader на готовых E1 индексах

Дата:25 октября2026. Статус: offline реализация; smoke и расходы **не разрешены**.
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
