# R3 — предложение следующего ограниченного запуска

25 сентября 2026. Статус: двухзапросный пилот выполнен по разрешению пользователя; полный repair остаётся предложением. Этот документ не разрешает дополнительные вызовы.

## Сначала: два измерительных запроса

**Выполнено один раз 25 сентября. Команду повторно не запускать:** private output `results/raw/hipporag-repair-context-pilot.json` уже существует; SHA-256 `385b3538b48fdb1acf6c09b5ae32ee78723449e2d594b5248b7c5fa5c2db659c`.

| Известный prompt, выбранный по максимальной длине в байтах | Измерено входных токенов | С cap extraction | Запас до `num_ctx=4096` |
|---|---:|---:|---:|
| NER | 691 | 1715 | 2381 |
| Triples | 1003 | 4075 | 21 |

Счётчик completion этих двух измерений не был сохранён; он неизвестен, а не равен нулю. Пилот не доказывает токены остальных prompts. Проверка исходников Ollama 0.34.4 показала, что OpenAI-compatible endpoint отбрасывает `extra_body.options.num_ctx`; этот adapter отказывает до вызова модели. Измерение и extraction теперь собирают один native `/api/chat` payload с `num_ctx` и `truncate=false`; его параметры проверены offline. Текущий context guard остаётся закрытым до измерения каждого нужного prompt.

Историческая команда уже выполненного пилота (повторно не запускать):

```powershell
$hippoPython = Join-Path $env:TEMP 'hipporag2-1438aba3-venv\Scripts\python.exe'
& $hippoPython -m scripts.measure_hipporag_repair_context --execute --output results/raw/hipporag-repair-context-pilot.json
```

Команда выбирает по одному самому длинному из уже известных NER и triple prompts, сверяет локальный digest модели и делает не более **двух** `/api/chat` запросов (`num_predict=1`, `stream=false`, `truncate=false`, JSON mode). Время одного запроса ограничено 300 секундами; общий верхний предел ожидания HTTP — 10 минут плюс загрузка исходных файлов. Ответы и prompts не публикуются; private файл содержит SHA prompt, счётчик входных токенов и in-flight marker. При ошибке, неизвестном исходе, смене digest или отсутствии счётчика — остановка без автоматического повтора. До запуска проверить поддержку `truncate=false` установленным Ollama; если она не подтверждена, пилот не начинать.

## Закреплённые входы и предел будущего repair

| Поле | Значение |
|---|---|
| Source run | `e78eff08-532a-40b3-a359-49a6b08b32a7` |
| Manifest SHA-256 | `35fbf63508e611366fee129f1ede0994f2c9954242d6e7e89a603aed456159f2` |
| Corpus SHA-256 | `054338e3803fbe69f67037c58d2a49438572ffe2e8c8a047148a2dcdc100e44b` |
| Plan SHA-256 | `f6ea09286136724f67621e24c4efc64913051a5fea1456d808a88ea1a6ec6d7e` |
| Model | `qwen2.5:3b`, digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`, Q4_K_M |
| HippoRAG | `2.0.0a5`, upstream `1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff` |
| Protocol | native `/api/chat`, `seed=42`, `temperature=0`, `num_ctx=4096`, `truncate=false`, JSON mode, без SDK cache/retries |
| Extraction caps | NER `1024`, triples `3072` generated tokens |
| Proposed fresh namespace | `storage/hipporag2-independent-s500-200-299-repair-f6ea0928` (currently absent) |

Остальные SHA-256 source artifacts закреплены в [repair preflight](../results/summary/hipporag-repair-preflight.json): OpenIE state `728b93a078a28eee94267a9da0522c6460d535a66aa8cf55527ab69f12754f85`, graph `cc7d53101cd7fc53e95beaece956ed5ec6cc9e19cdb30b1ecf84221567d0fbe6`, chunk metadata `7e8b519b809923a54483ec5377077332068f36d0e57c4206fc4cf886ffbd05d0`, chunk/entity/fact vectors `b9435c1b72271555cd1da3c91ad082f6b5ca167514e38d626c71bf6765260f84` / `90ebde2437bed03a487aa95625025aaeb897fd32448e99d17c13b15a691ebf2c` / `7fe8f81c07ce51aa915b6ae25333a6dd5ec9eb1c1e58114d3407c5bc2cbe85b6`, pinned index manifest `696eca0444d8818c9c62c1ab9c6855de8ecd86130431d3730eb4cd95ede2c79d`.

Первый замороженный проход: 38 NER и 158 triples, всего 196 extraction tasks, включая две attempt 3. Это размер очереди, не обещание успешного окончания и не бюджет для дополнительных повторов. После пилота для каждой задачи нужен полный token count до extraction; 38 зависимых triple prompts измеряются только после сохранения соответствующего NER. Поэтому потенциальный потолок первого прохода — ещё до 196 измерительных запросов и до 196 extraction запросов; пилотные два запроса считаются отдельно. Время такого прохода пока неизвестно и должно быть ограничено перед отдельным разрешением. Локальные затраты токенов измеряются по фактическому usage; отсутствующий usage остаётся неизвестным. Расход внутреннего API к этому не относится.

Пилот **не запускал repair, graph rebuild или QA**.

## Ограниченный первый repair-проход

Исполняемый runner использует native Ollama `/api/chat`, frozen planner/executor и private `RepairJournal`. Offline-команда сверяет исходные SHA, pinned HippoRAG и ровно 196 упорядоченных задач без сети. Исполнение повторно сверяет digest модели; исходный индекс не меняется. Значения и результаты сохраняются только в checkpoint под новым namespace.

Предельный бюджет: 196 задач (38 NER, 158 triples), максимум 196 измерений плюс 196 extraction-запросов, без повторов. Для каждого prompt измерение предшествует extraction; параметры: `num_ctx=4096`, `truncate=false`, JSON, `seed=42`, `temperature=0`, caps 1024/3072. Таймаут каждого HTTP-запроса — не более 300 секунд; абсолютный предел процесса — 6 часов. Usage, которого Ollama не вернёт, останется неизвестным.

Остановить очередь при несовпадении любого SHA/digest/config, неполном prompt usage, превышении `prompt_eval_count + output_cap <= 4096`, ошибке checkpoint, неизвестном исходе измерительного запроса либо первом unresolved extraction. In-flight задача не повторяется автоматически. Остановленный checkpoint сохраняется; embeddings, graph rebuild и QA не входят в эту команду.

Offline-проверка (без model request):

```powershell
$hippoPython = Join-Path $env:TEMP 'hipporag2-1438aba3-venv\Scripts\python.exe'
& $hippoPython -m scripts.run_hipporag_repair --dry-run
```

Команда ограниченного запуска:

```powershell
$hippoPython = Join-Path $env:TEMP 'hipporag2-1438aba3-venv\Scripts\python.exe'
& $hippoPython -m scripts.run_hipporag_repair --execute
```

Запуск проверяет локальный digest через Ollama API. Команда `ollama` в PATH не требуется. Результат repair остаётся private checkpoint до отдельного решения по следующим стадиям.

## Фактический ограниченный запуск, 25 сентября 2026

После offline-проверки и явного указания пользователя выполнены четыре native `/api/chat` POST: измерение и extraction для двух первых NER задач. Ollama подтвердил GPU размещение (`size_vram=2159374499` байт). Первая задача завершилась `valid_nonempty`; вторая достигла NER cap 1024 и получила `truncated`. По условию остановки очередь немедленно прекращена: оставшиеся 194 задачи не отправлялись, повтора нет.

Счётчики первой пары: measurement 473 input / 1 completion; extraction 473 / 45. Второй пары: measurement 334 / 1; extraction 334 / 1024. Usage получен для всех четырёх ответов. Private checkpoint остановлен с `unresolved_extraction`, содержит 2 задачи; SHA-256 `83f61962940c06c912ff0c595a8617be298698b802151bc50d8136d2ef331d13`. Исходные артефакты не менялись. Embeddings, graph rebuild и QA не запускались.

Продолжение требует отдельного изменения cap/retry policy по ADR-0008 и явного решения; этот checkpoint не возобновляется автоматически и не должен обходиться повтором задачи.

## Отдельная remedial NER attempt 3

Пользователь разрешил только одну ограниченную remedial попытку. Решение и остановки записаны в [ADR-0008](../.adr/0008-openie-truncation-retry-policy.md): cap 2048, `num_ctx=4096`, максимум одно измерение и одна extraction, 300 секунд на HTTP-запрос, 10 минут всего. Исходный checkpoint SHA должен остаться `83f61962940c06c912ff0c595a8617be298698b802151bc50d8136d2ef331d13`. Новая задача — NER attempt 3 с `retry_of_attempt=2`, `remedial_retry=true`, в отдельном namespace. При unresolved результате дальнейшая очередь закрыта; embeddings, graph rebuild и QA не входят в запуск.

Offline-проверка: `& $hippoPython -m scripts.run_hipporag_repair --remedial-ner --dry-run`. Только после неё ограниченный запуск: `& $hippoPython -m scripts.run_hipporag_repair --remedial-ner --execute`.
