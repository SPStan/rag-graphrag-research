# E2: общий путь оценки готовых E1 индексов (#14)

Статус: **диагностический smoke10 завершён** после отдельного разрешения v2:
60случаев=43completed/17reader length/0not_attempted. [Единая таблица](../results/summary/e2-smoke10-continuation.md).
Это не pilot200/полный E2. Draft PR35 зависит от Draft PR33/f8b9bb8, собственный diff20файлов
к `codex/e1-indexing`; после merge33 перенести base на master. PR33 не меняется.

## Текущий блок: reader-outcome policy v2, завершён

[План](../results/summary/e2-smoke10-continuation-plan.json) SHA723a9993…0ffe6
разрешён пользователем и выполнен на execution537fa023, child3bee5af5…1171.
Исходные3case/19parent pins/failed manifest/claims и расходы неизменны.
Новых child запросов134, ровно57оставшихся cases; дальнейший execute запрещён.

- Reader response с полным известным usage и length/empty/unusable/parser failure:
  `attempted_failed`, без повторного запроса, остальные случаи продолжаются.
- Unknown usage/transport/HTTP/infra/budget/data/config/pin mismatch: остановка.
- Hippo fact filter прежний: ошибки/length/malformed — остановка; valid empty→DPR.
- Reader/model/prompt/cap512/top5/evaluator/BGE и корпуса не меняются. AST функций
  формирования reader/embedding payload сверяется с исходным5dea658; metadata/pins
  проверяют все методы и оба датасета до первого HTTP.
- Child сохраняет3terminal parent cases (2completed/1length), вызывает только
  оставшиеся57уникальных method/dataset/question tuples. Same question у другого
  метода — другой case. Нет повторного retrieval/filter/embedding/reader при resume.
- Parent terminal known journal и19file SHA проверяются до запуска/нового запроса;
  canonical parent-child claim запрещает расходовать остаток повторным child.
- Новые bounds134POST=57reader+≤20filter+57localembeddings,≤77LLM/57embedding.
  Reserve3148544tokens≤3271113остатка; совокупно с5687parent≤3154231tokens,
  ≤140POST. Retry0/redirect0, connect30/read300, source unknown0 сохранён.
- Report объединяет60case keys и два physical journals один раз. `completed`,
  `attempted_failed`, `not_attempted` отдельны; последние не считаются неправильными
  ответами. При not_attempted в группе EM/F1=null; общее сравнение неполное,
  comparative table не публикуется.
  На completed smoke attempted_failed=0 в denominator10, failure rate отдельно,
  mean attempted latency включает failures. Hippo filter usage входит в стоимость;
  LLM input/output и local embedding раздельно, E1 остаётся отдельно incomplete.

Подготовка через existing runner, без HTTP:

```powershell
python -m scripts.run_dense_target `
  --shared-plan results/summary/e2-smoke10-continuation-plan.json `
  --continue-shared-plan results/summary/e2-smoke10-plan.json `
  --parent-output-dir results/raw/e2-smoke10-8d9ce08b
```

Для запуска после **отдельного** допуска: `--execute --shared-method dense|hipporag2|raptor`,
один общий output `results/raw/e2-smoke10-continuation-v2`, exact new plan SHA и
соответствующий existing SDK interpreter. Frozen SHA:
`723a9993cfd710c8e958cc5ae422ca26dfce27b448acb6538b89f28b3990ffe6`.
Новых model/embedding calls при подготовке0. Точный запуск всех3методов после допуска:

```powershell
$plan = 'results/summary/e2-smoke10-continuation-plan.json'
$out = 'results/raw/e2-smoke10-continuation-v2'
$sha = '723a9993cfd710c8e958cc5ae422ca26dfce27b448acb6538b89f28b3990ffe6'
$runtime = [ordered]@{
  dense = './.venv-check/Scripts/python.exe'
  hipporag2 = 'C:/Users/Elisei/.codex/worktrees/template-alignment/Rag, GraphRAG/.cache/hipporag-sdk-venv/Scripts/python.exe'
  raptor = 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-venv/Scripts/python.exe'
}
foreach ($method in $runtime.Keys) {
  & $runtime[$method] -m scripts.run_dense_target --shared-plan $plan --execute `
    --shared-method $method --output-dir $out --approved-plan-sha256 $sha `
    --env-file 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG/.env.target-api' `
    --hippo-source 'C:/Users/Elisei/.codex/worktrees/template-alignment/Rag, GraphRAG/.cache/hipporag-sdk-1438aba3' `
    --raptor-source 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-source'
  if ($LASTEXITCODE -ne 0) { throw 'Execution stopped; no retry' }
  $state = (Get-Content -LiteralPath "$out/manifest.json" -Raw | ConvertFrom-Json).status
  if ($state -eq 'failed') { throw 'Fatal stop; do not start another method' }
}
./.venv-check/Scripts/python.exe -m scripts.run_dense_target --shared-plan $plan `
  --output-dir $out --summarize-shared results/summary/e2-smoke10-continuation
```

`Get-Content` выше читает только atomic manifest после завершения процесса,
никогда живой usage.jsonl. Native/transport tests заменяют endpoints synthetic
sessions; реальный parent отдельно проверен с запрещённым HTTP, включая19pins и
все6index artifacts. Новые тесты32+tracking regression=33passed/2SDKskips.
Общая проверка выполняется обязательным commit hook на границе этого блока.
Старые команды/ограничения v1 ниже — исторический протокол source run.

## Законченный блок

- `run_dense_target --shared-plan` использует существующие E1 loaders,
  reader/parser, evaluator, checked_post/Journal и exporters `track_dense`.
- `run_e1 verify` теперь только проверяет; `export` — отдельная команда
  (старый `report` оставлен совместимым alias экспорта).
- Hippo загружает native Parquet через `_load_data` и graph.pickle, минуя
  mutable конструкторы SDK. Native prepare_retrieval_objects создаёт lookup maps
  в RAM из сохранённых triples; не вызывает index/OpenIE/embeddings и не меняет
  graph/store. Native fact scoring → DSPyFilter → PPR сохранены. Один общий
  normalized BGE query vector для facts/passages, query_instruction_mode=ignored.
- Native filter: Qwen, cap512; корректный пустой список ведёт к DPR, статус
  записывается. Ошибка транспорта/парсинга не маскируется под этот fallback.
- Dense возвращает пять passages; RAPTOR collapsed-tree — пять nodes без старого
  дополнительного 3000-token отсечения. Общая проверка reader input действует
  после retrieval: при overflow стоп, без скрытого удаления/обрезки контекста.
- Ключ resume: точные plan/config + dataset/method/question + payload. SHA body,
  terminal journal event и известный usage обязательны. Незавершённый claim,
  error/unknown/length не повторяются. Canonical claim не позволяет перенести тот
  же план в другую output directory для обхода лимитов. Один worker/общий journal.
- Per-question raw/parsed/status, retrieved order/scores, RAPTOR level/provenance,
  operations/request/response hashes, usage, phase и end-to-end duration сохраняются
  локально. Failed/not-attempted остаются в знаменателе. HTTP error с reported usage
  сохраняет эти токены и время, исходная причина исключения не подменяется.

## Замороженный smoke10: допуск получен, выполнено до первого stop

Исполняемый [план](../results/summary/e2-smoke10-plan.json):
SHA `8d9ce08b71255ef619a84299da5001096de8da2186de40988e4507da36d7cb97`.
В нём перечислены все20 ordered IDs, SHA queries/corpus/split/labels (только
оценщик), E1 manifests/artifact sets и кода. Первые10 S500 IDs каждого набора
проверены против tuning; signal-check и прежний reserve исключены. Корпус5500
и все6 существующих индексов переиспользуются целиком, без новой индексации.

| Параметр | Зафиксированное значение |
|---|---|
| Варианты | Dense/HippoRAG2/RAPTOR × MuSiQue/HotpotQA ×10 |
| Reader всех методов | iairlab/qwen3.8-27b, temperature0, seed42, cap512, thinking=false |
| Prompt обоих наборов | существующий MuSiQue one-shot без изменений, версия/SHA в плане |
| Контекст | native descending order, top5; Wikipedia Title + text; RAPTOR title=номер узла |
| Общий input gate | serialized messages ≤32000 UTF-8 bytes; без truncation |
| Query embedding | local bge-m3:latest, E1 digest; truncate=false, num_ctx/num_batch4096 |
| Hippo filter | pinned DSPy prompt, linking_top_k5, cap512; PPR damping0.5/weight0.05 |
| Максимум POST | 140:60reader +≤20filter +60local query embeddings |
| Максимум попыток | 1 на request, retry0, redirect0; connect30/read300 |
| Совокупный резерв | 3276800 combined tokens; не измеренный расход и не денежная сумма |
| Stop | первая ошибка/unknown/length/empty/invalid/overflow/SHA/digest/budget failure |

Резерв:80×(32000+1024envelope+2048reserve+512output) +
60×(4096query+1024envelope+2048reserve)=3276800. Это консервативная
byte-based reservation, **не native token count**. Actual tokens берутся только
из API/Ollama usage, отдельно LLM input/output и local embeddings. `/api/tags`
(GET перед новой method-сессией) проверяет live BGE digest; POST в лимитах выше.
Внешнему API передаются только вопросы, retrieved contexts, native fact candidates
и постоянные SDK demonstrations; gold/aliases/supporting в messages не входят.
Local Ollama получает только вопросы. SDK источники закреплены Hippo1438aba3,
RAPTOR7da1d48; tokenizer берётся из проверенного существующего offline cache.

HotpotQA использует тот же MuSiQue prompt: это заранее выбранная общая
конфигурация, не Hotpot-оптимизация. Реальный smoke должен проверить parser/usage,
не служить поводом менять prompt по F1. В reader Schema/JSON mode не добавляются.

## Воспроизведение исходного runtime5dea658

Команды ниже относятся к исходному5dea658. После запуска original plan и его
code pins неизменны; текущий post-processing исправлен отдельно. Для отчёта
используйте `--summarize-shared` ниже; новый `--execute` требует нового плана.

Подготовка в новом worktree, проверка **всех** source artifacts:

```powershell
python -m scripts.run_dense_target --prepare-shared `
  --shared-plan results/summary/e2-smoke10-plan.json `
  --e1-plan 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/e1-hotpot-local-recovery2-plan.json' `
  --e1-workspace 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG'
python -m scripts.run_dense_target --shared-plan results/summary/e2-smoke10-plan.json
```

Ни одна из этих команд не создаёт model client/HTTP. Подготовленный план не
перезаписывается при несовпадении. `http_authorized=false` означает статус документа;
будущий запуск требует отдельного точного `--approved-plan-sha256`, иначе отказ до
HTTP. Самостоятельно передавать этот флаг до ответа пользователя нельзя.

После согласия: существующий runner `--execute --shared-method METHOD`
с тем же plan SHA/output-dir, по одному методу в соответствующем закреплённом SDK
окружении. Обе dataset-модели загружаются/валидируются до первого HTTP.
SDK окружения не объединяются и не обновляются; Dense — check env, Hippo —
существующий isolated Hippo env, RAPTOR — existing raptor-venv. Все3 вызова
продолжают один run/journal/совокупный бюджет. Paused E1 automation не возобновлять.
Мониторинг живого журнала — только existing `run_e1.journal_snapshot` с Windows
share READ|WRITE|DELETE, не File.ReadLines/Get-Content.

Оценка saved smoke: `e2_evaluation.summary(plan,directory)`; labels доступны только
этой post-generation функции. `tracking_payload(plan,directory,dataset,method)`
готовит payload для существующих `track_dense.export_mlflow/export_langfuse`.
Сначала проверить доступность локальных сервисов; для остановленного Dense MuSiQue export выполнен и проверен (см.сводку).
RAPTOR passage recall=null, provenance coverage отдельно. E1 не начисляется повторно.
Операционные spans и общий physical journal сохраняются даже при остановке;
таблица не прячет failed IDs. Post-hoc tracing не считается новым измерением latency.

## Проверки и ограничения

Целевые synthetic/cache тесты проверяют общность reader, gold isolation,
SHA/index gates, HTTP usage/errors/time, replay/resume без duplicate cost,
unknown/length rejection, active worker и повторный claim. Native offline проверки
обоих Hippo и Dense/RAPTOR используют synthetic vectors/filter, запрещают HTTP и
index/constructor; E1 artifacts остаются неизменными. Это не реальное QA/smoke.

Готовые Hippo имеют Qwen primary/GPT-OSS fallback согласно ADR0023:
`structurally_verified_with_observed_extraction_errors`, semantic_verified=false.
Сравниваем конкретные конфигурации; чистый эффект архитектуры не изолирован.
Warning-enriched source audit не является corpus error-rate. E1 historical physical
known32601955/unknown reserve61588, cost_complete=false; reserve не actual usage,
recovery durations не cold build latency. Тарифы неизвестны, денежной цены нет.

## Следующие отдельные допуски

После успешного smoke — точный бюджет pilot200 ×2×3 и первая сравнительная таблица
F1/EM/completion/usage/latency/retrieval. Issue14 пока не выполнена, только Refs #14.
После пилота freeze конфигурации; совместимые smoke/pilot ответы учитывать один раз
в S500, без rebuild. До просмотра check[300:400] freeze сигнала; reserve[400:500]
не объявлять нетронутым. E3 paired bootstrap≥1000/seed42/shared resamples, CI,
C(N) для100/1k/10k/100k с неполным I; correct-answer cost только через EM.
Сначала offline complementarity/EM-oracle/F1-oracle, затем один signal/cascade;
Dense sunk cost и стоимость сигнала включены. Гипотеза95%F1 графа при≤60%cost
не подбирается по check. Полный E2/E3, holdout, 7B, merge сейчас не запускаются.

Целевые проверки:54 passed/2 SDK tests skipped в check env; оба SDK tests
отдельно passed в соответствующих существующих окружениях (по2датасета).
Общий offline gate выполняется commit hook; собственный diff≤20files.

## Реальная остановка25октября

Пользователь ответил «Разрешаю» на exact plan8d9ce08b…7cb97. Выполнено6POST:
3query embeddings и3reader. Два `stop` ответа, третий `length` при cap512:
1476input/512output, reported reasoning_tokens0. Ответ содержит обычное текстовое
рассуждение/перечитывание контекста и оборван до завершения. Клиентская ошибка
в saved payload не найдена. Это не основание повышать cap вслепую или менять
prompt по правильному ответу. Partial response остаётся failed; других методов нет.

Known query usage4516LLM input/1102output/69localBGE=5687; все6physical attempts
завершены, неизвестного usage нет. Оригинальные failed manifest/claims неизменны.
Два completed ответа и3query embeddings доступны для будущего проверенного reuse.
Остаток original caps3271113tokens/134POST не разрешает обход stop-condition.

После завершения worker исправлена сериализация post-generation отчёта:
`verified_reference.path` теперь строка. Регрессия проверяет JSON serialization и
неизменность failed manifest. В existing runner интегрирован воспроизводимый export:

```powershell
python -m scripts.run_dense_target --shared-plan results/summary/e2-smoke10-plan.json `
  --output-dir results/raw/e2-smoke10-8d9ce08b `
  --summarize-shared results/summary/e2-smoke10
```

Команда сохраняет private evaluation и public техническую таблицу. При failed
comparative_metrics=null: не выдаём остановку за сравнение трёх методов. Gold читает
только evaluator на20согласованных tuning IDs; сами gold в Git не попадают.
Локальный tracking содержит3attempted question spans и явно planned denominator10.
Langfuse подтвердил15passages/4516input/1102output, MLflow4artifacts скачаны и SHA
совпали. Private receipts в raw/tracking; safe IDs/verification — в JSON сводке.
Новых экспериментальных запросов post-processing не выполнял.

Следующий возможный вариант: сохранить reader length как failed outcome без retry,
с тем же reader/cap512 пройти остальные57плановых ответов. Это сохраняет исходные
пределы и denominator; любой другой error/unknown остаётся fatal. Нужен отдельный
точный child-план/проверяемый lineage и допуск изменения stop-policy. Он здесь не
реализован и не запущен; pilot200 не разрешён.

## Фактическое завершение v2 — 25 октября

Child3bee5af5-13f9-43ad-b9d9-dee3dfd11171 completed; все60case keys уникальны.
43completed/17attempted_failed/0not_attempted; все17 — reader length при cap512.
Reader/model/prompt/options не менялись, partial не принимались и не повторялись.
Fatal infrastructure/filter errors не возникли. Parent5,687tokens/6POST включён один раз:
new child203421tokens/134POST; total209108known/140POST=80LLM+60BGE.
LLM188118input/19535output, localBGE1455; Hippo filter60853input/1331output включён.
Unknown0/unfinished0; old/new response/request/case/journal SHA и19parent pins проверены.
E1 core artifacts не перестраивались, query operations не содержат index/OpenIE.
E1known32601955/reserve61588/cost_complete=false отдельно, не цена в деньгах.

Единая таблица включает mean measured query time по10attempted cases, failures входят;
исключены index loading/preflight и pacing. Это development tuning n10/dataset,
не cold-run latency benchmark. RAPTOR provenance coverage не passage recall@5.
Posthoc tracking шести конфигураций использует сохранённые60cases с failure status,
физические расходы обоих journals считаются один раз; экспорт не новые model calls.

**Один следующий шаг:** общий пересмотр reader для всех методов до pilot200,
поскольку17/60length (28.3%) нарушают контракт завершённого ответа. Основание —
технический исход, не лучший F1. Новый reader — отдельная версия/план/допуск,
эти результаты с ней не смешиваются; новых проб и pilot200 сейчас нет.

Локальный tracking подтверждён:6MLflow runs/6Langfuse traces по10question spans,
50retrieved passages/nodes на trace, reader usage совпал;48artifact round-trips SHA
совпали (включая source/child journals/manifests). Private receipts raw/tracking,
safe trace IDs — в итоговой JSON. В установленном SDK resource manager singleton
сохраняется после client.shutdown: повторный exporter в одном процессе может
застрять на media queue flush. Экспортировать по одной конфигурации на процесс.
Один уже записанный RAPTOR trace восстановлен обратным чтением/verify без повторной
выгрузки; source traces не удалялись, новых inference/duplicated traces нет.
Воспроизведение таблицы без моделей:

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan results/summary/e2-smoke10-continuation-plan.json `
  --output-dir results/raw/e2-smoke10-continuation-v2 `
  --summarize-shared results/summary/e2-smoke10-continuation
```
