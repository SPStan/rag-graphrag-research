# R3 — предложение следующего ограниченного запуска

25 сентября 2026. Статус: предложение; **никаких модельных вызовов этим документом не разрешено**.

## Сначала: два измерительных запроса

После отдельного разрешения выполнить только эту команду из корня проекта в PowerShell:

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
| Protocol | `seed=42`, `temperature=0`, `num_ctx=4096`, JSON mode, uncached, SDK retries `0` |
| Extraction caps | NER `1024`, triples `3072` generated tokens |
| Proposed fresh namespace | `storage/hipporag2-independent-s500-200-299-repair-f6ea0928` (currently absent) |

Остальные SHA-256 source artifacts закреплены в [repair preflight](../results/summary/hipporag-repair-preflight.json): OpenIE state `728b93a078a28eee94267a9da0522c6460d535a66aa8cf55527ab69f12754f85`, graph `cc7d53101cd7fc53e95beaece956ed5ec6cc9e19cdb30b1ecf84221567d0fbe6`, chunk metadata `7e8b519b809923a54483ec5377077332068f36d0e57c4206fc4cf886ffbd05d0`, chunk/entity/fact vectors `b9435c1b72271555cd1da3c91ad082f6b5ca167514e38d626c71bf6765260f84` / `90ebde2437bed03a487aa95625025aaeb897fd32448e99d17c13b15a691ebf2c` / `7fe8f81c07ce51aa915b6ae25333a6dd5ec9eb1c1e58114d3407c5bc2cbe85b6`, pinned index manifest `696eca0444d8818c9c62c1ab9c6855de8ecd86130431d3730eb4cd95ede2c79d`.

Первый замороженный проход: 38 NER и 158 triples, всего 196 extraction tasks, включая две attempt 3. Это размер очереди, не обещание успешного окончания и не бюджет для дополнительных повторов. После пилота для каждой задачи нужен полный token count до extraction; 38 зависимых triple prompts измеряются только после сохранения соответствующего NER. Поэтому потенциальный потолок первого прохода — ещё до 196 измерительных запросов и до 196 extraction запросов; пилотные два запроса считаются отдельно. Время такого прохода пока неизвестно и должно быть ограничено перед отдельным разрешением. Локальные затраты токенов измеряются по фактическому usage; отсутствующий usage остаётся неизвестным. Расход внутреннего API к этому не относится.

Пилот **не запускает repair, graph rebuild или QA**. После него сравнить полученные token counts с `num_ctx` и caps и проверить совпадение native измерения с фактическим OpenAI-compatible transport на отдельном ограниченном запросе. Если это не доказано, текущий `context_fit_verified` guard остаётся закрытым. Для реального repair ещё нужен отдельный разрешённый запуск с новым namespace и проверкой source SHA. Любой unresolved extraction, превышение контекста, неизвестный in-flight, ошибка записи, изменение конфигурации или digest останавливают очередь; сохранённый checkpoint остаётся private. Graph строится только после zero-unresolved extraction gate и exact vector IDs, QA — после `graph_ready` и отдельного разрешения.
