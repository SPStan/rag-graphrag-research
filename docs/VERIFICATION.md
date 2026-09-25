# Проверки начального стенда

Дата наблюдений: 17 сентября 2026. Это журнал фактически показанных выводов команд и просмотра интерфейсов пользователем, а не исследовательский benchmark. Он не подтверждает воспроизведение на другой машине.

| Проверка | Результат | Основание |
|---|---|---|
| Docker Compose | 6 контейнеров запущены; 4 зависимости healthy | Вывод `docker compose up -d` после перезагрузки Windows |
| Langfuse HTTP | HTTP 200, status OK, версия 4.37.0 | `/api/public/health` |
| Langfuse SDK | 4.15.4; root и child прочитаны через API | [JSON smoke-теста](../results/smoke/smoke-3da7dab24d67.json) |
| Langfuse UI | `smoke-test-no-llm` и `local-python-step` видны | Пользователь открыл trace и подтвердил оба события |
| MLflow | 3.16.1; experiment `rag-graphrag-smoke` | Установка и выполненный smoke-скрипт |
| MLflow run | `65a88db5af534c5cba909ce5dd965000` | Пользователь открыл run, скопировал параметры и метрику |
| MLflow параметры | mode=mock, llm_calls=0, retrieval_method=none | Просмотр интерфейса |
| MLflow метрика | toy_score=1 | Демонстрационное значение, заданное скриптом |
| Совместимость пакетов | `No broken requirements found` | `python -m pip check` при подготовке репозитория |

У mock-проверок `llm_calls=0`. Токены внешней LLM не расходовались. Повторный запуск MLflow создал отдельный run `4d5854e02cf64779b0793c7ffedb7c83`; это не независимый научный эксперимент.

`smoke_mlflow.py` печатает `verified` после записи, но пока сам не читает метрики обратно. Подтверждение чтения здесь основано на просмотре пользователем интерфейса. Автоматическое чтение, запись файла-артефакта и проверка после перезапуска — следующие задачи.

## Ограничения текущей проверки

- Langfuse находится в Docker Compose, MLflow — отдельный процесс Windows.
- Сохранность уже созданных trace/run после следующего перезапуска ещё не проверена.
- Нет общего run_id между двумя инструментами и результатов реальной LLM.
- Восстановление окружения с нуля на другом компьютере не проверено.
- Пять Docker-образов закреплены по digest; для MinIO используется изменяемый тег с описанным в README исключением.
- localhost-ссылки и ID из журнала предназначены для локального стенда; они не дают руководителю удалённый доступ к интерфейсам.

## Дополнение: локальные RAG run и сохранность артефактов, 25 сентября 2026

Это дополнение не меняет статус mock-проверок выше. Dense baseline100 и HippoRAG debug10 прошли post-hoc экспорт в локальные MLflow и Langfuse с общими run ID. Для HippoRAG run `9cac28e5-2885-4510-b227-ecba06f1b3de` MLflow artifacts JSONL, metrics и manifest были скачаны обратно и побайтно совпали с локальными файлами. Langfuse подтвердил 50 retrieved passages и generation usage 15 891/1 330. Это локальный учёт Ollama, не расход внутреннего API и не удалённый доступ для руководителя.

Compose Langfuse и отдельный Windows MLflow server также были проверены после перезагрузки. Подробности экспериментального ограниченного run, в том числе неизвестная стоимость исходного graph build, состоят в [LOCAL_MVP](LOCAL_MVP.md) и [ADR-0006](../.adr/0006-hipporag-common-reader-debug10.md).

Экспорт новых run в MLflow дополнительно проверяет хэш JSONL, полный упорядоченный список question ID и конфигурацию manifest/metrics. После записи trace выбирается только по точному атрибуту `rag.run_id`; совпадение одного имени span недостаточно. Новые HippoRAG run также сохраняют отдельно wall time query embedding, retrieval, generation и end-to-end вопроса. Эти поля не добавлялись задним числом в уже записанные raw-артефакты.

## Candidate evaluation S500[200:300], 25 сентября 2026

Ordered IDs SHA-256: `a026de236266ceb4ee7faa4cde5d031996ecfd74f4e6edd806a8b08cc493d42b`; файл view и labels/corpus hashes указаны в [компактной сводке](../results/summary/musique-independent-candidate-s500-200-299.json). Dense 3B run `98d8b412-cec6-45e4-9c14-0e4ad85855bb` завершён на всех 100 IDs, результаты сверены по порядку и SHA-256: EM 0,110; token F1 0,1858; recall@5 0,6058. Известное QA usage: 154 400 prompt и 12 222 completion tokens; query embedding — 2 592 prompt tokens. Векторы были переиспользованы из прежнего cache, полная стоимость их исходного построения остаётся неизвестной.

HippoRAG run `e78eff08-532a-40b3-a359-49a6b08b32a7` использовал новый storage namespace и отдельный manifest. Индексный build завершился, но acceptance gate отклонил индекс до QA: из 11 000 ожидаемых terminal stage outcomes осталось 160 unresolved (122 triples truncation, 37 NER truncation, 1 NER request error); missing outcomes — 0, unexpected attempts — 0, записано 11 025 попыток. В NER было 5 498 кэш-попаданий, 24 miss и 2 request errors без cache outcome; их attempt/error provenance записан, usage неизвестен. В журнале также есть 21 NER parse-error attempt, часть из которых разрешена retry. Суммарный известный local Ollama usage index build: 7 240 351 prompt и 1 522 360 completion tokens; это локальные счётчики, не внутренний API. Полная сборка заняла 14 427,9 секунды. QA results отсутствуют, поэтому парное сравнение и bootstrap не выполнялись.

Read-only [repair readiness report](../results/summary/hipporag-repair-readiness-candidate.json) подтвердил сохранность OpenIE state (5 500 passages), графа и embedding stores: 5 500 passage, 44 614 entity и 47 614 fact vectors. Producer/embedding/OpenIE identity, SHA исходного корпуса и точные vector IDs совпадают с **текущим** OpenIE state. Это не доказывает безопасность будущей копии после исправлений. По журналу 38 NER и 122 triple terminal outcomes неуспешны; два passage затронуты обеими стадиями. Предварительная оценка — 196 точечных generation calls с учётом зависимых triples; повторные неудачи увеличат число вызовов. Исходный индекс не менялся. Для исправленного OpenIE state нужно создать в копии store с **точным новым набором** entity/fact IDs: переиспользовать совпадающие векторы, добавить новые и убрать устаревшие до пересборки графа. Иначе upstream использует все IDs в store при построении synonymy edges ([pinned source](https://github.com/OSU-NLP-Group/HippoRAG/blob/1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff/src/hipporag/HippoRAG.py#L1143-L1182)). Также пока не реализованы правила gate для обновления ранее валидных triples после исправления NER и bounded remedial attempt 3 для двух stages. Ремонт не готов к запуску; см. [ADR-0008](../.adr/0008-openie-truncation-retry-policy.md).

Последующая синтетическая проверка добавила gate-семантику для связанных triple refresh и третьей remedial attempt (не больше трёх попыток на stage), фильтрацию vector table по целевым IDs, merge attempt ledger без изменения исходных записей, patch OpenIE state и копирование whitelisted index artifacts после проверки SHA-256. Журнал теперь сохраняет частичное восстановление при `finish_reason=length` только для распознанных структур без upstream parse error; статус остаётся `truncated`. Реальный index clone и импорт его журнала не запускались; orchestration, добавление новых embeddings и пересборка графа пока не реализованы. Полный набор unit tests: 112 passed; `pip check`: passed. Готовность и оставшиеся блокеры перечислены в [preflight summary](../results/summary/hipporag-repair-preflight.json).

Dense результат — кандидатный локальный результат на замороженном срезе, не оценка репрезентативности полного MuSiQue. Он независим от ранее проверенных QA IDs по предзапусковому аудиту, но исторический baseline100 включает debug10. `holdout100` не использовался. Успешный синтаксический extraction или доля непустых triples сами по себе не доказывают семантическое качество OpenIE.

## OpenIE protocol и candidate view, 25 сентября 2026

Новые HippoRAG run пишут в локальный manifest attempt-level OpenIE ledger отдельно для NER и triples. Он классифицирует валидные пустые/непустые extraction, parse errors, truncation, отсутствующий response, request errors и неизвестное завершение; хранит ID/fingerprints, model/prompt hashes, finish/cache status, response hash/bytes, retry linkage, usage и время, не сохраняя passage, prompt или response text. Acceptance gate требует валидного terminal outcome для обеих стадий каждого passage, наблюдаемого LLM-layer provenance и ноль unresolved failures; higher-level OpenIE-cache результата без attempt provenance недостаточно. После проверки candidate run исправлено условие retry: `finish_reason=length` требует retry даже если repair parser частично разобрал JSON. До нового index build необходимо настроить manifestированные увеличенные per-stage retry caps и проверить вместимость контекстного окна. Исторические manifests не обновлялись и gate для них не проходили ретроспективно.

Синтетические тесты protocol helper и заморозки выборки проверяют статусы, gate, retry linkage, стабильность ordered IDs и отказ при пересечении. После исправления retry и уточнения summary: 97 unittest passed; основная `.venv` проходит `pip check`. До запуска candidate read-only audit проверил 29 MuSiQue manifests и 4 raw JSONL без manifests, пересечений не было. Candidate запуск описан в разделе ниже; последующие изменения не создавали новых MLflow/Langfuse записей, LLM-вызовов или индексов.
