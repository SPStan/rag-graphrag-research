# ADR-0025: pilot200 с закреплённым общим answer-only reader

Дата:26 октября2026. Reader принят для экспериментальной конфигурации прямым
поручением пользователя. План подготовлен offline; реальный pilot **не разрешён**.
Refs #14. Зависимая ветка codex/e2-pilot200 от PR35/b708aa5, base
codex/e2-shared-evaluation. PR35 остаётся Draft и не меняется. Предшествующее
решение/диагностика: [ADR0024](0024-shared-evaluation-ready-indexes.md).

## Выбор и основания

Закрепляется shared-answer-only-v1, уже проверенный на12методических случаях
из4tuning-вопросов:12полных ответов/28232known tokens/unknown0; source review
7supported/2observed_error/3needs_review. Это проверка формата, не общей точности
и не независимый аудит. Старый reader требовал Thought и дал17length из60.
Основание выбора — устранение требования длинного text reasoning и проверка
контракта ответа. Выбор не сделан по лучшему F1; новых prompt/cap/model проб нет.

Для Dense/HippoRAG2/RAPTOR и обоих наборов одинаковы Qwen
iairlab/qwen3.8-27b, temp0/seed42/cap512, thinking=false, stream=false,
четырёхсообщенческий one-shot и единственная строка Answer. Прежние demo context/
question сохранены, reasoning в demo удалён. Точные prompt/options/template SHA,
base Answer parser и single-line/cycle gate закреплены планом и code SHA.
Неверный по смыслу технически корректный ответ оценивается как обычный результат.

Новая версия выбирается в общем question_result, до фактического transport.
Transport запрещает старый Thought-template, незапланированный ID/метод и POST
для случая с проверенным reuse. Старые reader_payload/результаты остаются доступны
для проверки source checkpoints и не получают задним числом новую версию.

## Данные и границы

Берутся ровно200существующих views.pilot200 IDs каждого датасета: порядок совпадает
с S500[:200] и comparison_split.pilot200_ids; уникальность/принадлежность tuning
проверены. Signal-check/reserve и остальные S500 не входят в план/оценку.
200×2×3=1200case keys (dataset,method,question). Одинаковый question ID другого
метода — другой случай. Hash queries/corpus/labels/evaluator/порядка/SDK/индексов
закреплён. Labels/supporting читает только post-generation evaluator;
подготовка лишь хэширует файл labels, в генерацию передаются title/text/question.

Шесть E1 индексов переиспользуются целиком и не строятся заново. Native retrieval/
filter/PPR, top5, RAPTOR node order/provenance, input byte/overflow gates прежние.
Hippo mixed Qwen/GPT extraction и semantic_verified=false раскрываются как часть
конкретной конфигурации; это не чистый эффект архитектуры.

## Ограниченный reuse вместо общего кэш-движка

Переиспользуются60проверенных contexts из source+continuation smoke и все12
совместимых answer-only ответов (включая source-review errors/needs_review).
Source корпуса/индексов/моделей/native retrieval/filter/embedding кода, параметров,
текстов вопросов, parser/evaluator и payload проверяются. Каждый checkpoint/body
связан с известным terminal usage в producer journal;374file SHA заморожены.
Ошибки SHA/неизвестный исход не превращаются в cache miss с новым POST.

Для60случаев готовый context заменяет весь старый retrieval/query-embedding/filter
этап. Его source operations/cost/timing сохраняются отдельно в per-case provenance.
12reader responses принимаются только при полном совпадении actual answer-only
payload/options и известном usage. Старые60Thought answers не используются как
новые ответы. Никакого отбора по правильности/gold/F1/source-review outcome нет.
Валидация источников обязательна до HTTP и при resume. Однотипный ledger встроен
в existing runner; отдельного runner и универсальной системы stage cache нет.

Чистое продолжение после границы метода/сохранённого terminal checkpoint пропускает
все уже учтённые случаи, включая known reader failures, без оплаты. Failed run/
незавершённый claim/unknown usage не перезапускаются автоматически. Другой output
не обходит canonical plan claim. Новые child/recovery/budget требуют отдельного
решения после разбора; текущее согласование не подразумевает их заранее.

## Новый бюджет и учёт

После reuse:1188reader (198/config),≤380Hippo filter (190/dataset),1140local query
embedding (190/config). Всего≤2708model POST, из них≤1568external LLM,1140local BGE.
По1попытке на новый request, retry0/redirect0/connect30/read300. POST/operation/
token limits проверяются до запроса; неожиданное превышение reported usage после
ответа сохраняется как известный расход и останавливает run.

Conservative reserve **57189854combined tokens**, не прогноз/actual/денежная цена:

- (1140fresh-context reader+380filter)×35584=54087680;
-48cached-context новых reader: точный UTF8 payload bytes+2048+cap512=530385;
-1140новых BGE: точный UTF8 payload bytes+2048=2571789.

35584=32000messages bytes+1024envelope+2048allowance+512output cap.
Overflow32000bytes — fatal без truncation; бюджет не гарантирует завершения всех
случаев. Неиспользованный резерв не разрешает дополнительные запросы.

Development expense237340known tokens/152POST фиксируется отдельно (old209108 и
answer-only28232), E1known32601955/reserve61588/cost_complete=false отдельно.
Доступная source-attribution для reuse91871tokens: LLM88985input/1431output и
BGE1455; это **часть** development237340. Остальные145469development tokens —
старые reader requests, не используемые как ответы. Не суммировать development
и reused-attribution повторно. Совокупные физические E2 расходы =237340+новые
physical requests; логическая стоимость pilot =фактически использованные source
operations+новые. При early stop отчёт не приписывает неиспользованный reuse.

Reader, Hippo filter и BGE input показаны раздельно, LLM input/output раздельно.
Source+child journals проверены и дедуплицированы по physical identity; source cost
не выдается за новый cache-hit/новый POST. Unknown E1 не становится нулём.

## Latency, failures и итог

Fresh E2E измеряется только на1140новых context cases с явным n, включает failed
попытки, исключает index load/preflight/pacing. Reader client call (HTTP+ответ/
сохранение) измеряется отдельно для1188новых reader, включая cached contexts.
12повторно использованных reader имеют только source timing.60historical context
stage times и старый wall time сохраняются с source run ID; их нельзя складывать
с новой generation и называть свежим E2E. Cache replay wall time — только replay.

Known reader length/empty/parser/format/cycle — attempted_failed без retry,
очередь продолжается. Unknown/transport/HTTP/infra/pin/config/budget/overflow —
fatal с original error, raw, journal и manifest; никакого автоматического recovery.
Hippo filter отдельно: length/malformed/error fatal, valid empty facts→native DPR.
Полный технически корректный, но неверный ответ не останавливает очередь.
Not_attempted имеет null score, не ноль. Для завершённого denominator200 reader
failures=0; при прерывании comparison incomplete, парные выводы не публикуются.

Итоговая таблица содержит6строк: EM/F1, completed/failed/not-attempted/failure rate,
passage recall@5 дляDense/Hippo; RAPTOR node provenance coverage отдельно, fresh
E2E (n), reader call time(n), новые физические и reused source reader/filter/BGE
usage. Для каждой стадии LLM input/output отдельно. E1/development отдельно.
Парные ΔEM/ΔF1 по одинаковым200IDs: bootstrap2000, seed42, shared resamples для
методов/метрик, percentile95% CI. Это заранее выбранная описательная неопределённость
на tuning pilot, не независимое подтверждение преимущества. Никакой настройки
после просмотра пилота, holdout/check/S500/7B/rebuild/merge этим планом не разрешено.

## Проверка и допуск

Existing runner synthetic regression включает fresh/reused contexts/readers у всех
трёх методов, actual outbound template/options, source/question/config mismatch,
zero-POST gates, known reader length continue, семантическую ошибку без stop,
unknown fatal, невозможность повторной оплаты/другой output, точные case keys,
source cost один раз и latency provenance. Pure report из saved records не вызывает
HTTP. Published pilot IDs проверены на обоих датасетах. Общий offline gate —
обязательный hook после законченного блока; real API calls в подготовке0.

Plan [e2-pilot200-plan.json](../results/summary/e2-pilot200-plan.json), file SHA:
`284af290878ef53f9a486d1df956a8e02d72f147d3a6f1e2aa0b072efc5b4f01`.
До отдельного допуска этого exact SHA API-вызовы запрещены. Один допуск покрывает
все3метода/оба набора до fatal stop, без отдельного разрешения на каждый метод.
Команда в [E2 protocol](../docs/E2_EVALUATION.md).
