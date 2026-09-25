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

## OpenIE protocol и candidate view, 25 сентября 2026

Новые HippoRAG run пишут в локальный manifest attempt-level OpenIE ledger отдельно для NER и triples. Он классифицирует валидные пустые/непустые extraction, parse errors, truncation, отсутствующий response, request errors и неизвестное завершение; хранит ID/fingerprints, model/prompt hashes, finish/cache status, response hash/bytes, retry linkage, usage и время, не сохраняя passage, prompt или response text. Acceptance gate требует валидного terminal outcome для обеих стадий каждого passage, наблюдаемого LLM-layer provenance и ноль unresolved failures; higher-level OpenIE-cache результата без attempt provenance недостаточно. Исторические manifests не обновлялись и gate для них не проходили ретроспективно.

Синтетические тесты protocol helper и заморозки выборки проверяют перечисленные статусы, gate, retry linkage, стабильность ordered IDs и отказ при пересечении. Полный набор: 87 unittest passed; основная `.venv` — `No broken requirements found`. Candidate `S500[200:300]` закреплён в `data/ids/musique_independent100_candidate.json`; read-only audit проверил 29 MuSiQue manifests и 4 raw JSONL без manifests, пересечений нет. Candidate не запускался. Проверки не создавали новых MLflow/Langfuse записей, LLM-вызовов или индексов.
