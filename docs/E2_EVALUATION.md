# E2: общий путь оценки готовых E1 индексов (#14)

Статус: **offline-подготовка**, реальных smoke/E2 ответов нет. PR зависит от
Draft PR33/f8b9bb8; собственный diff считается к `codex/e1-indexing`.
После merge33 базу отдельного Draft PR нужно перевести на master. PR33 не меняется.

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

## Замороженный smoke10: требуется допуск расходов

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

## Воспроизведение offline и будущий запуск

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
Сначала проверить доступность локальных сервисов; сейчас экспорт не выполнялся.
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
