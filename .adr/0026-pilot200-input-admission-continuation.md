# ADR-0026: технический byte admission и продолжение pilot200

Дата: 26 октября 2026. Подготовлено offline; пользователь затем разрешил любой
план продолжения RAPTOR. Этот допуск применяется к точному ограниченному плану
ниже, без повторного запроса согласия. Refs #14; Draft PR36, зависимости #35/#33.

## Причина и выбор

Original run84454233-8d21-4731-922a-5a31184610e0 остановлен на локальном
MESSAGE_BYTES=32000, введённом в E2 как консервативный admission/reservation gate.
Он проверяет serialized UTF-8 bytes, а не native tokens или реальный context модели.
Фактический answer-only запрос37608bytes содержит9860native input tokens по
закреплённому tokenizer. Считать это доказательством переполнения модели нельзя.

Сохраняются top5, полный текст, native порядок, Qwen3.8-27B, shared-answer-only-v1,
temp0/seed42/thinkingfalse/cap512, parser/evaluator, все данные и6готовых индексов.
Меняется только общий для всех методов локальный messages byte gate32000→65536
и резервирование. Retrieval, prompt и научные критерии не меняются. Альтернатива
truncation/drop node меняла бы фактические входы; она не выбрана. Повышение output
cap/модельные пробы не нужны и не выполнялись.

## Обоснование границы

[Закреплённый proof](../results/summary/e2-pilot200-input-bound.json) получен из
готовых5500passages каждого корпуса и всех7438/7595RAPTOR nodes без retrieval,
gold, holdout и новых моделей. Для каждого метода/набора берутся пять максимальных
escaped title+text по байтам и максимальный вопрос из опубликованных200pilot IDs.
Сериализуется тот же reader payload. Верхние границы messages:
Mu RAPTOR63955, Hotpot RAPTOR58961, Mu Dense/Hippo13239, Hotpot Dense/Hippo29753.
65536 покрывает эти границы; byte count не называется token count.

Использован уже сохранённый Qwen2TokenizerFast/HF snapshot1d4bf0f, SHA трёх файлов
закреплены, transformers4.45.2/tokenizers0.20.3, local_files_only/без загрузки весов.
Native counts для size-extreme prompts:16490/15381RAPTOR,2756/7011Dense/Hippo;
это измерения этих конкретных synthetic worst-byte prompts, не верхняя граница
количества токенов любого сочетания. Byte-BPE conservative bound65536+2048chat
allowance+512output=68096 меньше262144 из переданного пользователем deployment
contract14октября. Это консервативная граница, не измеренный backend prompt count;
точная ревизия текущего deployment независимо не подтверждена. Новых HTTP0.

## Совместимость и immutable continuation

Все812completed case SHA, original response/checkpoint/journal pins и фактически
сформированные reader payload SHA проверены: новый admission не меняет ни байта
готовых входов/ответов. Исторический runtime41ee909 проверяется по Git blob,
реконструированному в исходные Windows CRLF bytes; старые SHA не подменяются.
Полная metadata/data/index/reuse конфигурация перестраивается offline и сравнивается.

Parent terminal failed, running.lock отсутствует, весь usage известен, нет лишних
physical attempts. Только один pre-reader overflow с одной успешной query embedding
может открыть child.812готовых случаев наследуются, overflow не засчитывается
как ошибка reader в итоговом сравнении. Его сохранённые embedding/retrieval и33tokens
переиспользуются с точным source key; родительский failed manifest остаётся неизменным.
Parent journal и child journal учитываются один раз; source-stage reuse из parent
не прибавляется ещё раз как внешний historical expense. Диагностические source
расходы по-прежнему входят в development237340, E1unknown61588 остаётся отдельно.

## Точные новые пределы и исполнение

Остаётся388reader outcomes:188MuSiQue и200HotpotQA. Два Hotpot ответа уже совместимы
и берутся из diagnostic cache независимо от качества. Новых reader POST≤386
(188Mu/198Hotpot), embedding≤377(187Mu/190Hotpot), filter0; всего≤763POST.
Резерв:386×(65536+1024envelope+2048+512output)+850379exact BGE bytes+allowance
=27530699combined tokens, не прогноз и не денежная цена. Прежний остаток
54784356tokens/763POST не увеличен. На запрос — одна попытка, retry0/redirect0,
connect30/read300, между новыми cases4s. Transport и execute запрещают новые
Dense/Hippo/filter и любые POST для inherited cases/совместимого кэша.

Новый output results/raw/e2-pilot200-continuation-v1, новый run ID и canonical
plan/parent-lineage claims. Same-output checkpoint reuse допустим только при
чистом завершении; любой failed/unknown/незавершённый claim не перезапускается.
Автоматических recoveries0. Known reader length/empty/unusable — case failure
с сохранённым usage, без retry, очередь продолжается; transport/unknown/infra/
pin/budget/новый overflow — fatal stop. После ошибки сохранение и offline RCA,
без расширения лимита или повторения потенциально оплаченных запросов.

## Проверка и итог

Existing runner/CLI synthetic tests проверяют длинный неизменённый payload,
overflow доreader, бюджет доPOST,812-style inherited no-pay, stage-only replay,
immutable source files, claim/pin/active parent gates, уникальный merge и отсутствие
двойного расхода. В fixture66cases используется тот же механизм, что1200реальных;
реальный offline snapshot подтверждает812+388=1200уникальных case keys.

Autonomous launcher сохраняет startup/terminal status и logs без LLM polling;
живой usage читается только existing shared snapshot reader из run_e1 с Windows
FILE_SHARE_READ|WRITE|DELETE, handle закрывается до JSON parsing. До старта — один
worker и проверенный code/plan SHA; исполняемый код под worker не меняется.
После завершения: строгий1200-case audit, общий report/paired bootstrap2000seed42,
существующий local tracking без model calls, meaningful commit/push. Replay time
не fresh E2E, RAPTOR provenance не passage recall@5, tuning/mixed extractor/E1
неполнота сохраняются. Никаких S500/check/holdout/rebuild/новых моделей/merge.

## Наблюдение исполнения

Child fadc0797 завершил249новых случаев и остановился на250-м: reader
RemoteDisconnected, исход1POST неизвестен, retry0. RAPTOR Mu200complete,
Hotpot61complete/1transport failed/138notattempted. Combined1061/1/138.
Child937346known/487POST; unknown reserve22545 не actual. E2 cumulative
known3580184/2584POST,cost_complete=false; E1 отдельно.

Бывший overflowcase:37608bytes,9860native/server input,5output, embedding reused.
Это подтверждает локальную природу прежнего byte gate, но не завершает pilot.
Новый transport failure не повод поднимать limit или повторять unknown.
[Неполная таблица](../results/summary/e2-pilot200.md) сохраняет готовые группы;
paired inference/полныйtracking не объявляются завершёнными. Следующий шаг —
уточнить исход unknown у владельца API без нового POST; оператору не писали.
