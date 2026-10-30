# HotpotQA S500 — результат issue17

Технический результат завершён: **1500ожидаемых уникальных исходов**,1497ответов,
3attempted_failed,0not_attempted; по500frozen IDs каждого метода.
Dense500/0, HippoRAG2 498/2, RAPTOR499/1. Это не1500успешных ответов.
[Воспроизводимая таблица](../results/summary/e2-hotpotqa-s500.md),
[safe JSON с audit/расходом](../results/summary/e2-hotpotqa-s500.json).
Научные O/N/R/H PR39 ожидают согласования перед merge. Draft/Refs #17,
без Ready/merge; научные настройки и формулировки не менялись.

## Протокол и lineage

Те же500ordered HotpotQA IDs, три готовых E1 индекса, общий reader/evaluator,
Qwen3.8-27b/cap512/top5/seed42 и прежний split. Labels используются только оценщиком.
Supporting mapping проверен на первых3заранее выбранных tuning IDs по title+full
passage, с валидацией sentence indices; gold не передавался в генерацию.
Новых индексов, extraction, моделей, tracking-export или signal/holdout нет.

600pilot outcomes (599ответов+1sealed transport failure) переиспользованы.
Root `91f59cf6-e61c-499d-9d29-d55bff1824c2`, execution `7a67791`, сохранил471новый
исход и terminal failed на fact filter. После конкретного уведомления пользователь
прямо разрешил только429unattempted. Child `9e7efc49-895c-42d6-a2d3-5676e2071b6b`,
execution `f23bb5956b4fab3e4e38aa0fcadd1853b1fb200d`, завершил429/429без новых failures.
Исходные manifests/results/checkpoints/journals/claims/plans/runtime SHA неизменны.
Подробное решение и альтернативы — [ADR0028](../.adr/0028-full-experiment-freeze-and-reuse.md).
Ни оплаченный запрос, ни unknown не повторялся. Filter-fatal policy не ослаблялась.

## Расход и время

Исходный Hot cap4982220combined tokens/2100POST не расширялся, retry0.
Root:1203911known/1112POST. Child:1559928known/987POST. Вместе Hot S500 physical:
**2763839known/2099POST**, включая reader и Hippo fact filter; BGE отдельно в таблице.
Один reader slot failed-filter case не использован. Новые журналы полностью измерены;
S500physical cost_complete=true, новыхunknown0/unfinished0. Это не полный historical cost.

Cumulative E2: **9856273known/7059POST**,2historical unknown/reserve38277,
cost_complete=false. Резерв — не actual usage и не0. Source/development4036653 и
source91871 уже включены один раз. E1 отдельно32601955known/reserve61588,
cost_complete=false; mixed extractor/errors/semantic_verified=false сохранены.

Время в таблице — mean query wall time для300fresh physical cases/метод,
без4s pacing и загрузки индекса; root+child объединены, initial200reuse исключены.
Это не время непрерывного прогона500новых вопросов. Logical source usage отдельно
от physical expense. RAPTOR provenance не passage recall@5. S500development
не является независимым тестом.

## Сохранённые failures

| Метод / ID | Исход | Учёт |
|---|---|---|
| Hippo / `5a772e465542994aec3b7209` | reader_length | known usage, без retry/cap change |
| Hippo / `5adcc5715542990d50227d0a` | E2_filter_shape_invalid | known usage, root остаётся failed |
| RAPTOR / `5adbe75455429944faac23af` | historical transport failure | usage=null, reserve22545 |

Все три получают pipeline EM/F1=0 с исходным error marker; это не три неверных
reader answers. Retrieval сохраняет политику общего evaluator, включая пустой
pipeline retrieval; missing/not_attempted не подменяется успешным наблюдением.

## Воспроизведение и передача

В worktree PR39 при сохранённых private artifacts:
```powershell
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan .cache/e2-hotpotqa-s500-unattempted-plan.json `
  --output-dir results/raw/e2-hotpotqa-s500-unattempted-v1 `
  --summarize-shared results/summary/e2-hotpotqa-s500
```
Команда не исполняет inference. Перед публикацией полный JSON/MD дважды получен
в новом temporary output с запрещённым socket.connect, byte/equality verified;
private evaluation SHA не изменился. Исполнение pinned в плане f23bb59; SHA кода
отдельного postprocessor сохранён в `report_code_sha256`, execution hashes —
`execution_code_sha256`. Прежний frozen plan не меняется из-за reporting fix.

Точные private входы задач12/14/18: `results/raw/e2-hotpotqa-s500-unattempted-v1/`
с `evaluation.json`, `manifest.json`, `usage.jsonl`, `question-<casekey>.json`,
`<object>.json`/`<object>.response.json`. Parent refs ведут к
`results/raw/e2-hotpotqa-s500-v1/` и исходному pilot lineage. Error markers находятся
в per-case `status/error/fatal/operations`; source runtime и SHA сохраняются.
Public JSON не содержит question/answer/corpus texts. Финальный source/index/
code/authorization gate и strict1500audit выполнены,0duplicate/unbound attempts.
23целевых tests после reporting-scope fix прошли; mandatory hook финального коммита
и CI его точного HEAD проверяются отдельно. Новые model calls для проверки не нужны.

| Критерий issue17 | Свидетельство |
|---|---|
| Все500ID трёх методов | 1500unique,1497completed+3failed,0not_attempted |
| Reader/evaluator и labels | Неизменные pins,3tuning mappings, общий evaluator |
| Расход/reuse/лимиты | Immutable lineage,2763839/2099 в cap,0newunknown/retry |
| Доступные артефакты | Private per-case paths/SHA и воспроизводимый safe report |

Следующий шаг — техническое ревью PR39 и зависимой E3 в PR40, затем актуальное
научное согласование перед отдельно разрешённым merge. Следующие исследования
и signal-check в этом блоке не запускались.
