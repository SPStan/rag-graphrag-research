# ADR-0027: завершение только незапущенных cases при сохранённом unknown

Дата:26 октября2026. После уведомления о RemoteDisconnected/unknown пользователь
повторно прямо разрешил продолжать работу. Это отдельное ручное согласование
нового bounded run, не автоматическое восстановление failed run. Refs #14.

## Решение и основание

Не повторять запрос с неизвестным исходом и не ждать его повторной генерации.
Сохранить исходные unknown, failed manifest/claim/intent checkpoint и расход.
Выполнить только138не запущенных RAPTOR/HotpotQA cases по прежним ID/индексам,
модели, reader, полным top5 и порядку, temp0/seed42/thinkingfalse/cap512, byte gate65536.
Никаких новых Dense/Hippo/filter, embeddings старых cases или новых проб.

Неизвестный reader POST закрепляется как sealed terminal infrastructure failure:
HotpotQA5adbe75455429944faac23af, producer fadc0797-34e3-4468-8f0d-bc9ef1289f3a.
Отсутствие ответа наблюдаемо, фактический расход неизвестен. Ключ/actual payload,
единственный error/unknown journal event, once checkpoint со status=started,
отсутствующий response, известный embedding и все остальные attempts проверены.
Unknown не превращается в cache miss, новый claim не разрешает retry.

Прежняя fatal policy сработала: очередь была остановлена. Новый explicit child
не отменяет её задним числом. Любая новая transport/unknown/infra/SHA/budget/overflow
ошибка снова останавливает очередь; automatic recovery0. Known reader failures
по прежней политике сохраняются без повторов, последующие cases продолжаются.

## Учёт и метрики

Из предшествующего выделенного лимита27530699 вычитаются937346known и22545unknown
reservation; остаётся26570808. POST763−487=276. Новые bounds:138reader+138localBGE,
filter0; reserve138×69120+310557exact embedding bytes/allowance=9849117tokens.
Unknown reservation не actual usage и не денежная цена. Суммарные исходные
лимиты pilot57189854tokens/2708POST не расширяются.

1062terminal cases наследуются:1061completed и1transport failed, а не1062ответа.
Оставшиеся138получают собственный новыйrun/output. Явный перечень трёх physical
journals и flattened per-case producer paths сохраняет разные runtime/config SHA.
Parent-stage reuse и development source считаются один раз; E1incomplete отдельно.
Новое usage проверяется строго; сохранённый единственный unknown в lineage остаётся
null с22545reserve. Cost_complete=false сохраняется даже при1200accounted cases.

Для финальной200-ID таблицы измеряется полный pipeline: terminal infrastructure
failure имеет EM/F1=0 и отдельный transport failure marker, не называется неверным
ответом модели. Это дополнение до новых API-вызовов; старые raw/metrics не меняются.
Оно не даёт выбрасывать технический case из denominator или выбирать удачные ID.
Дополнительно указывается, что один transport case меняет среднее максимум на0.5pp.
Paired bootstrap остаётся2000resamples/seed42 на всех200общих IDs; эти tuning
сравнения учитывают observed pipeline failure, не доказывают преимущество reader
или архитектуры. Mixed Hippo extraction/errors и неполнота E1 раскрываются.

## Проверки и границы

Existing runner/CLI synthetic tests проверяют три-run lineage, исключение unknown
из новых вызовов, сохранение reserve/null, запрет подмены checkpoint/SHA/лимитов,
immutable source, уникальный merge и отсутствие двойного расхода. Tracking сверяет
known subtotal даже при unknown и отвергает подстановку нуля/estimate вместо null.
Для200-case traces ждёт все batches локально; это не дополнительная inference.
Реальный offline snapshot проверяет1062cases, единственный unknown и весь source
lineage. ДоfirstPOST проверяются frozen plan/code/data/index pins и отсутствие
worker. Source parser/evaluator/model/retrieval/prompt не меняются.

После run — строгий1200-case audit с единственным разрешённым historical unknown,
единая существующая таблица/paired comparison, local tracking без model calls,
обновлённая очередь и Draft PR. No S500/check/holdout/7B/rebuild/merge. Исходные
failed runs не перезапускаются и не переписываются. Ещё один sealed-unknown child
этот механизм не создаёт: потребуется отдельное решение, не цепочка recoveries.
