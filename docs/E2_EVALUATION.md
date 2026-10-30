# E2: общий путь оценки готовых E1 индексов (#14)

## Консолидация issue #14 в итоговый PR #36 — 26 октября

Итоговый PR36 сохраняет всю опубликованную историю issue14. PR35/HEADb708aa5
является предком исходного HEAD36/3fda04f; его закрытие не используется как способ
переноса кода. PR33 слит обычным merge ca09702999e08e973c297972c21676b54784b466.
База интеграции PR36 — master; полный E2 diff проверяется отдельно.
Итоговый diff включает общую E2 реализацию, smoke/continuation, answer-only
reader diagnostic, pilot200, tracking, тесты и документы issue14.

Карта сохранности PR35:

- scripts/e2_evaluation.py и tests/test_e2_evaluation.py: общий runner, все20исходных
  test/helper definitions сохранены. Native query adapters в e1_indexers и CLI
  интеграция run_dense_target необходимы для E2 без переиндексации.
- tests/test_e2_continuation.py: все7исходных definitions сохранены, теперь21;
  exact reuse/lineage/failed-case/no-POST guards расширены для пилота.
- token_accounting.py сохраняет известный usage HTTP-ошибки; соответствующий
  schema regression адаптирован. run_e1 CLI verify получает read-only возврат.
  Эти общие изменения принадлежат интеграции E2 и не являются новым E1 запуском.
- smoke/diagnostic artifacts, ADR0024, evaluation/tracking tests остаются в истории
  и текущем дереве. Пилот и ADR0025–0027 их дополняют; версии reader не смешиваются.
- Итоговая таблица1200cases, raw manifests/claims/usage/runtime pins и прежние
  результаты не переписываются консолидацией. Privateraw не добавляется в Git.

Объединённый diff —32файла относительно master; точный размер указан
в описании PR36. Превышение20не скрывается: это общая реализация оценки плюс pilot200 одной
issue. Посторонние пользовательские правки основного checkout не включены;
отдельный PR ради формального лимита не создаётся.

Порядок интеграции разрешён текущим сообщением пользователя: обычный merge33,
получение актуального master, смена базы36 на master и проверка дерева/merge-base/
diff/CI, затем Ready и merge36. Force-push, административный обход защиты и
изменение required checks/reviews не разрешены. Ветка33 сохраняется до окончания36.

Научные O/N/R/H подтверждены куратором по сообщению пользователя; ссылка и дата
решения не приписываются. Публичных GitHub reviews/одобрения бота не заявляется.
Сохранённые отдельные допуски mixed extractor, continuations и sealed unknown
применяются без повторного запроса; новые расходы или эксперименты не разрешены.

Критерии issue14:1200cases учтены,6конфигураций связаны с E1/run IDs, метрики и
раздельные reader/filter/BGE costs опубликованы, выбран Hippo на двух датасетах,
есть воспроизводимая таблица и offline разбор6вопросов/18случаев. Tuning, mixed
extractor/source errors, sealed unknown и неполный E1 остаются ограничениями,
а не исчезают после merge. В PR добавляется Closes14; связь Development проверяется
после перевода базы на default branch. Активные часы не выводятся из wall time.
PR35 закрыт без merge, его история и исходная ветка сохранены.

После интеграции итоговых PR очередь — issue15: фиксация полного протокола и
reuse без модельных вызовов. Сам этап15 здесь не начинается; новые S500/check/
holdout/7B/model comparison/rebuild не запускаются.

## Результат26октября: pilot200 complete по1200pipeline cases

- Все1200unique method/dataset/question cases учтены:1199completed,
  1infrastructure attempted_failed,0not_attempted. [Единая таблица](../results/summary/e2-pilot200.md)
  и[JSON](../results/summary/e2-pilot200.json). Это complete pipeline comparison,
  не1200ответов и не независимое подтверждение качества/преимущества архитектуры.
- Runtime4bd1d25, final run20a6360f-24f4-4151-a70c-76632d0a81aa:138newcompleted,
  276POST,456469known tokens (LLM452100input/941output,BGE3428),newunknown0.
  Сохранённый historical reader unknown не повторён; reserve22545,usage=null.
- Pilot physical3799313known/2708POST. E2сdevelopment4036653known/2860POST,
  cost_complete=false. Source91871 — часть development237340, безdouble count.
  E1known32601955/reserve61588/cost_complete=false отдельно. Index rebuild0.
- EM/F1(%): Mu Dense33.00/43.60,Hippo42.50/52.61,RAPTOR32.50/43.49;
  Hotpot Dense59.00/70.81,Hippo69.00/79.29,RAPTOR57.00/70.51.
  RAPTOR Hotpot199completed+1transport failure(0.5%), pipeline EM/F1=0длянего;
  это не неверный ответ reader. Paired bootstrap2000seed42,n200,12comparisons.
- HTTP0terminal audit проверил1200unique,1062parents/138new, все data/index/
  result/response/checkpoint/journal SHA, одну sealed unknown identity; sourcefailed/
  claims неизменны. Первоначальная ошибка окружения audit(PYTHONPATH) исправлена
  без нового run/POST. Execution pins4bd1d25 отделены от postprocessing correction.
- Local tracking:6MLflow/6Langfuse views по200cases,66artifact roundtripSHA;
  в обоих сервисах6000retrieval+6000generation documents совпали с source по
  title/text/order, вMLflow также answers. Reader usage/unknown проверены.
- Reporting-only correction:33BGE tokens reuse внутриpilot отнесены кpilotphysical,
  не кdevelopment cache; global cost/answers/payloads не менялись. Regression3passed.
  Langfuse содержит явную cost-attribution-correction annotation без trace reexport.
- Latency instrumented/cross-run, включает guards/persistence; validation lineage
  послеcontinuation больше. Source/replay не freshE2E; RAPTORprovenance не passage
  recall@5. Tuning/mixedHippo/errors/E1incomplete раскрыты. Сравнение не causal.
- CI cleanup: восстановлены conventional title prefixes(PR36 exp,PR35 feat).
  19history findings проверены:9code SHA,6HF tokenizer SHA,2case IDs,2usage formulas.
  Добавлены только точные commit/path/rule/line fingerprints; blanket exclusions нет.
  Local full-history scan201commits:0findings; отдельный synthetic stdin canary
  обнаружен generic-api-key. Ответы/планы/расходы/модельные вызовы не менялись.
- Рабочий выбор по tuning pilot — HippoRAG2 против Dense на тех же двух датасетах,
  без 2Wiki. Обоснование F1/EM и более высокой стоимости с fact filter добавлено
  в итоговый отчёт и ADR0025; параметры/результаты/JSON/расходы не менялись.
  Это не независимое подтверждение и не допуск задачи9.
- Offline error review: SHA1200results и прежние EM/F1 подтверждены; выбранные
  по фиксированным outcome strata6вопросов/18случаев сверены с top5/source.
  Показаны missing evidence, неверное событие/организация, paraphrase/краткость
  и reference ambiguity. Это иллюстрации, не частоты причин; labels/метрики/JSON
  неизменны, HTTP0. Научные O/N/R/H подтверждены по сообщению пользователя;
  опубликованное GitHub review/одобрение бота не заявляется.
- Итоговый PR36 включает общую реализацию и pilot одной issue. Пользователь
  разрешил Ready/merge после актуального CI и проверки базы master. Следующий
  этап — issue15 (полный протокол/reuse), не начинается в этой задаче.

## Воспроизведение выбора примеров ошибок без HTTP

В E2 worktree выполнить этот код через `.venv-check/Scripts/python.exe -`
(PowerShell here-string). Он использует существующий runner/evaluator, проверяет
сохранённые lineage/results и печатает только ID/метрики, без gold или корпуса.
Ручные выводы о содержании контекста приведены в итоговом Markdown, не в JSON.

```python
import json
from pathlib import Path
from unittest.mock import patch
import requests
from scripts import e2_evaluation as e
plan = json.loads(Path("results/summary/e2-pilot200-unattempted-plan.json").read_text(encoding="utf-8"))
with patch.object(requests.Session, "request", side_effect=AssertionError("HTTP forbidden")):
    report = e.summary(plan, Path("results/raw/e2-pilot200-unattempted-v1"))
rows = {(x["dataset"], x["method"], x["question_id"]): x for x in report["question_results"]}
assert len(rows) == 1200 and report["comparison_complete"]
for ds, data in plan["datasets"].items():
    selected = []
    for rule in (lambda xs: all(x["f1"] == 0 for x in xs),
                 lambda xs: len({x["em"] for x in xs}) > 1,
                 lambda xs: any(0 < x["f1"] < 1 for x in xs)):
        q = next(q for q in data["question_ids"]
                 if all(rows[ds, m, q]["status"] == "completed" for m in e.METHODS)
                 and rule([rows[ds, m, q]["metrics"] for m in e.METHODS]))
        if q not in selected:
            selected.append(q)
    for q in selected:
        print(ds, q, [(m, rows[ds, m, q]["metrics"]) for m in e.METHODS])
```

## Воспроизведение отчёта без HTTP

Existing --summarize-shared из сохранённых raw/lineage пересчитывает только evaluation
и safe summary; runtime pins сохраняются. План/API execute ниже — история,
завершённый run не перезапускать. Стоимость остаётся incomplete из-за одного
исторического unknown, даже при полном покрытии200IDs×2×3.

## Подготовка последнего bounded run (история)

[ADR0027](../.adr/0027-pilot200-sealed-unknown-unattempted.md) сохраняет1terminal
transport failure сnull usage и22545reserve. Это новый явно разрешённый run,
не retry неизвестного POST.1061completed+1failed наследуются,138cases остаются.
Пределы138reader/138localBGE=276POST,9849117tokens из26570808available послеreserve.
Pipeline EM/F1 использует0для infrastructure failure с явным раскрытием; cost_complete
остаётсяfalse. Это не неверный ответ reader и не independent architecture evidence.

```powershell
& 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-venv/Scripts/python.exe' `
  -m scripts.run_dense_target `
  --shared-plan results/summary/e2-pilot200-unattempted-plan.json `
  --execute --shared-method raptor --output-dir results/raw/e2-pilot200-unattempted-v1 `
  --approved-plan-sha256 125dfe5e75afc2fe1bdb2eb4e2d3c174ef113b7ff847cd72dcba2b955472b24b `
  --env-file 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG/.env.target-api' `
  --raptor-source 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-source'
```

Preflight: strict source/result/response/checkpoint/three-journal SHA и sealed unknown
identity, новое usage должно бытьcomplete. Одна попытка/request, retry/redirect/recovery0,
timeout30/300; новые unknown/transport/infra/budget/pin/overflow → stop. Автопродолжения
нет, original failed/unknown не меняются. После1200accountedcases — один existing
report/paired bootstrap и posthoc local tracking без model calls. Старая неполная
таблица вGit85a61b8, raw результаты immutable; текущая safe summary обновляется.

## Результат предыдущего continuation: неполный pilot, unknown

- Runtime3914d70, child fadc0797-34e3-4468-8f0d-bc9ef1289f3a terminal failed
  в2026-10-26T02:11:11Z. Worker завершён, retry/recovery0; исходные manifests/claims
  не менялись. Мониторинг завершает работу; повтор POST не разрешён.
- Reader target API оборвал соединение без ответа (RemoteDisconnected), HotpotQA
  question5adbe75455429944faac23af. Один physical reader POST имеет unknown usage.
  Reserve22545tokens сохранён как консервативная граница, не расход/ноль.
- [Текущая неполная таблица](../results/summary/e2-pilot200.md):1061completed,
  1attempted_failed,138not_attempted. Dense/Hippo×2 и RAPTOR Mu по200готовых;
  RAPTOR Hotpot61completed+1transport failure+138not attempted. Paired inference нет.
- Child487POST=248reader+239BGE,937346known tokens;1unknown reader. Pilot parent+child
  2432POST/3342844known; E2сdevelopment2584POST/3580184known,cost_complete=false.
  E1known32601955/reserve61588/cost_complete=false отдельно. Unknown не засчитан нулём.
- Бывший byte overflow пройден полным неизменённым payload:37608bytes,
  native9860/server9860input tokens,5output; embedding/retrieval reused. Byte gate
  не вызвал новую остановку. Все новые результаты и стоимость сохраняются.
- Existing report-only сформировал6строк без новых HTTP. Live reader подтвердил
  finished487,unknown1,inflight0,corrupt-tail0. Partial tracking не экспортирован;
  полное1200-case/audit/paired сравнение не объявляется выполненным.
- Единственный следующий шаг: уточнить у владельца API исход запроса по сохранённым
  метаданным/времени, не повторяя его. Сообщения оператору не отправлялись. До решения
  о пропущенном unknown case нового continuation нет; бюджет/протокол не ослаблять.

## Подготовка продолжения (история; failed child не перезапускать)

[ADR0026](../.adr/0026-pilot200-input-admission-continuation.md) и
[bound proof](../results/summary/e2-pilot200-input-bound.json) обосновывают общий
byte gate65536, без truncation/payload/retrieval изменений. Native overflow count9860,
а не37608tokens. Пользователь разрешил любой план продолжения RAPTOR.
812completed наследуются;388outcomes=386новыхreader+2cached,377новыхlocalBGE,
filter0. Новые≤763POST/27530699tokens; исходный остаток не расширен.

Подготовка offline уже выполнена existing runner:

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan results/summary/e2-pilot200-continuation-plan.json `
  --continue-pilot-plan results/summary/e2-pilot200-plan.json `
  --parent-output-dir results/raw/e2-pilot200-v1 `
  --pilot-bound-proof results/summary/e2-pilot200-input-bound.json
```

Однократное выполнение разрешённого exact плана (parent не перезапускать):

```powershell
& 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-venv/Scripts/python.exe' `
  -m scripts.run_dense_target `
  --shared-plan results/summary/e2-pilot200-continuation-plan.json `
  --execute --shared-method raptor --output-dir results/raw/e2-pilot200-continuation-v1 `
  --approved-plan-sha256 cbdc1a8c063d74d4848793338c78c7b915c9e9a98b6815943741b4e644ddf400 `
  --env-file 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG/.env.target-api' `
  --raptor-source 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-source'
```

Одна попытка на request; retry/redirect/recovery0,timeout30/300. Первый fatal
останавливает worker без новой копии/child. Known reader failure сохраняется,
следующие cases продолжаются. Budget проверяется доPOST. Исходные manifests,
claims, responses и стоимость неизменны; parent stage reuse не double count.
После terminal — existing report-only --summarize-shared results/summary/e2-pilot200;
строгий audit1200cases, paired bootstrap по протоколу и local tracking безmodelcalls.

## Результат первоначального запуска26октября: pilot200 неполон

- Отдельный зависимый Draft PR36, codex/e2-pilot200; PR35 и основной checkout
  не изменены. Runtime `41ee909c14ffca5dff552fa65d46f33f39d9ed8d`.
- После прямого допуска exact plan284af290…5b4f01 выполнен run
  `84454233-8d21-4731-922a-5a31184610e0`. Terminal failed; без retry/recovery.
- 812completed,1attempted_failed,387not_attempted из1200уникальных случаев.
  Dense/Hippo×2 завершили по200, RAPTOR Mu12completed+1overflow, Hotpot0.
  [Неполная таблица](../results/summary/e2-pilot200-incomplete.md): парные выводы
  не публикуются; незапущенные случаи не засчитаны как неверные ответы.
- RAPTOR Mu question `4hop1__802394_153080_159767_81096`: actual answer-only
  messages37608UTF8bytes >32000. Это реальный overflow без truncation;
  reader POST не было, только33known BGE tokens. Не ошибка ответа reader.
- 1945новых POST=802reader+380Hippo filter+763BGE; все finished/known,
  unknown0/unfinished0. LLM2356693input/29066output, BGE19739input:
  2405498новых combined tokens. Все813saved cases,374source pins,
  полные data/index/code pins и immutable terminal journal проверены offline.
- Used source80504tokens/80operations — часть development237340/152POST,
  не дополнительный расход. E2physical cumulative2642838tokens/2097POST.
  E1known32601955/reserve61588/cost_complete=false остаётся отдельно.
  Исторические времена не превращены в freshE2E. Старые результаты неизменны.
- Единственный следующий шаг: предложить общую политику ограничения входного
  контекста для всех методов через ADR до continuation. Нельзя молча поднять
  limit/обрезать контекст/перезапустить failed plan. Остаток54784356tokens/763POST
  не является разрешением. S500/check/holdout/7B/rebuild/новые пробы не запущены.
- Partial pilot не экспортирован в MLflow/Langfuse: публичная таблица и строгие
  raw artifacts — источник этого результата; прежние tracking views не менялись.

## Подготовка и команда первого запуска (история; failed run не перезапускать)

[ADR0025](../.adr/0025-pilot200-shared-reader.md),
[точный plan](../results/summary/e2-pilot200-plan.json), file SHA
`284af290878ef53f9a486d1df956a8e02d72f147d3a6f1e2aa0b072efc5b4f01`.
Работа в зависимой codex/e2-pilot200 от PR35/b708aa5; PR35 не расширяется.
Reader shared-answer-only-v1 принят текущим поручением для всех3методов. Детали
старого smoke/diagnostic ниже — исторические результаты, не новые pilot responses.

1200cases=200pilot IDs×2datasets×3methods; исключены signal-check/holdout/прочиеS500.
Reuse60contexts/12reader responses даёт максимум1188новых reader,380filter,
1140localBGE; всего2708POST,1568externalLLM. Reserve57189854tokens, не forecast:
1520×35584+530385cached-reader+2571789BGE.374source hashes, все6ready индексов прежние.
План/limiting transport/stop policy/source costs/timing/CI подробно вADR0025.

Воспроизвести подготовку без HTTP (существующий frozen plan не перезаписывается):

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan results/summary/e2-pilot200-plan.json --prepare-pilot `
  --e1-plan 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/e1-hotpot-local-recovery2-plan.json' `
  --e1-workspace 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG' `
  --reuse-shared-plan results/summary/e2-smoke10-continuation-plan.json `
  --reuse-shared-output results/raw/e2-smoke10-continuation-v2 `
  --reuse-diagnostic-plan .cache/e2-answer-only-diagnostic-plan.json `
  --reuse-diagnostic-output results/raw/e2-answer-only-diagnostic-v1
```

Однократное исполнение **только после допуска exact SHA**, все методы одним
согласованным блоком, каждый в прежнем SDK interpreter (никакого install/update):

```powershell
$pilotPlan = 'results/summary/e2-pilot200-plan.json'
$pilotOutput = 'results/raw/e2-pilot200-v1'
$pilotSha = '284af290878ef53f9a486d1df956a8e02d72f147d3a6f1e2aa0b072efc5b4f01'
$pilotRuntimes = [ordered]@{
  dense = './.venv-check/Scripts/python.exe'
  hipporag2 = 'C:/Users/Elisei/.codex/worktrees/template-alignment/Rag, GraphRAG/.cache/hipporag-sdk-venv/Scripts/python.exe'
  raptor = 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-venv/Scripts/python.exe'
}
foreach ($pilotMethod in $pilotRuntimes.Keys) {
  & $pilotRuntimes[$pilotMethod] -m scripts.run_dense_target `
    --shared-plan $pilotPlan --execute --shared-method $pilotMethod `
    --output-dir $pilotOutput --approved-plan-sha256 $pilotSha `
    --env-file 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG/.env.target-api' `
    --hippo-source 'C:/Users/Elisei/.codex/worktrees/template-alignment/Rag, GraphRAG/.cache/hipporag-sdk-1438aba3' `
    --raptor-source 'C:/Users/Elisei/.codex/worktrees/dense-target-smoke/Rag, GraphRAG/.cache/raptor-source'
  if ($LASTEXITCODE -ne 0) { throw 'Pilot stopped; no automatic retry/recovery' }
  $pilotState = (Get-Content -LiteralPath "$pilotOutput/manifest.json" -Raw | ConvertFrom-Json).status
  if ($pilotState -eq 'failed') { throw 'Fatal stop; preserve results, no next method' }
}
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan $pilotPlan --output-dir $pilotOutput `
  --summarize-shared results/summary/e2-pilot200
```

Get-Content выше читает только atomic manifest после завершения worker, не live
usage.jsonl. Один active running.lock/canonical claim; stale lock/unknown/failed
не обходить и не удалять автоматически. Между штатными methods/checkpoints
допускается same-output continuation с полным verify и без оплаты terminal cases.
До исполнения убедиться, что нет другого worker; ошибки на первом запросе не
запускают fresh-output/retry под тем же согласием. Готовые6индексов не пересчитывать.

Report-only команда последняя выше не вызывает моделей и работает при partial
run: not_attempted=null, comparison incomplete, сохранённый known/unknown usage.
Итог:6строкEM/F1/failures/retrieval, fresh E2E сn, generation отдельно, input/output
reader/filter/BGE отдельно для новых и source requests. Source times не складываются
в новый E2E. Paired ΔEM/ΔF1 и descriptive95% bootstrap CI по тем же200IDs,
2000resamples/seed42; это tuning/development, не independent confirmation.
Development237340 включает91871доступных source reuse; не прибавлять оба повторно.
E1cost_complete=false/reserve61588 отдельно, RAPTOR provenance не passage recall@5.
Новых запросов в подготовке0; этот текст не допуск. Никаких S500/check/holdout,
7B/новых model/prompt/cap серий/индексации/merge по этому плану.

## Предыдущие законченные блоки E2 (история)

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

## Зафиксированный план answer-only probe (теперь выполнен)

[ADR0024: rationale,12IDs/payload SHA и критерии](../.adr/0024-shared-evaluation-ready-indexes.md).
Plan `.cache/e2-answer-only-diagnostic-plan.json`, SHA
`1b816118b0f2b5574abeb1e384fcde61a391f6bca9fe45a78b00a2649a71cf8b`,≤12readerPOST/152350new tokens, без retrieval/filter/embedding.
Ответы всех методов используют те же cached contexts, источник347pins проверен.
Прежний reader не изменён: новый candidate — отдельная версия, не continuation v2.
Подготовка воспроизводится без HTTP и без labels/evaluator:

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan .cache/e2-answer-only-diagnostic-plan.json `
  --reader-probe-from results/summary/e2-smoke10-continuation-plan.json `
  --parent-output-dir results/raw/e2-smoke10-continuation-v2
```

Исторический однократный запуск после отдельного допуска exact SHA (выполнен; не повторять):

```powershell
./.venv-check/Scripts/python.exe -m scripts.run_dense_target `
  --shared-plan .cache/e2-answer-only-diagnostic-plan.json --execute `
  --output-dir results/raw/e2-answer-only-diagnostic-v1 `
  --approved-plan-sha256 1b816118b0f2b5574abeb1e384fcde61a391f6bca9fe45a78b00a2649a71cf8b `
  --env-file 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG/.env.target-api'
```

Результат responses_pending_source_audit не означает принятие reader. Первый любой
сбой — стоп; failed/unknown/repeat claims не перезапускаются. Проба не вызывает
evaluator, не меняет старые summary/manifests, не запускает pilot200. Source audit
отдельно до любого предложения большого прогона. Новых HTTP в подготовке0.

## Завершение reader-only diagnostic — 25 октября

Run eb9668ff-ef12-45c5-ac4e-4c52f868a84c, execution22e4553/exact file SHA1b816118…71cf8b,
пользователь разрешил12POST ответом «Продолжай».12/12stop/valid Answer,100output tokens,
28132input, embedding/filter0, unknown0/unfinished0; всё в bounds.347source pins
проверены после запуска. Parent/continuation manifests/results/расходы immutable.

Source audit:7supported/2observed_error/3needs_review. Две бывшие length ситуации
теперь format-complete, но источник не поддерживает выбранный ответ для заданного
вопроса. Три direct answers имеют неполную multihop evidence chain. Ответы и их
источники разобраны offline без gold/F1; полный private source-audit.json закреплён
в manifest/response/journal SHA, RAPTOR original-source-proof.json проверяет claims
по исходным descendant passages. Это не новая comparative таблица качества.

Technical pass не равен semantic pass/adoption. Только предложение зафиксировать
один общий output contract для отдельно согласуемого pilot200; без новой цепочки
prompt tuning на этих4вопросах, без смешивания версий. Текущий diagnostic закончен;
никаких дополнительных POST, pilot200/S500/check/holdout/rebuild/merge не запускать.
Совокупный query known237340tokens/152POST включает прежний smoke один раз;
исторический E1 cost_complete=false сохраняется отдельно. Raw worker manifest
responses_pending_source_audit не переписывается; отдельная assessment содержит
завершённый audit с раскрытыми ошибками. Diagnostic tracking не создаёт F1 и не
маскирует cached embedding/retrieval как новые операции.

Локальный diagnostic export выполнен через existing MLflow/Langfuse exporters,
один mixed-method reader-only view с12tuple identities dataset/method/original ID.
MLflow `b7fad1509ffa409e895761f68eeffbea`, Langfuse
`bdb7418a6537553f33942e2c9c6806b8`.12question/generation spans,60cached contexts;
embedding observations явно performed_this_run=false, реальных embedding POST0.
Reader usage28132/100 подтверждён;8artifact round-trip SHA совпали. EM/F1/recall=null,
никаких новых model calls экспорт не создал. Source audit7/2/3 раскрыт в артефактах,
а historical E1 incomplete cost и прежний smoke расход не пересчитаны как новые.

## Offline freeze S500 — issue #15

[Манифест](../results/summary/full-experiment.json) содержит ordered IDs и SHA,
шесть index/provenance pins, compatibility decisions по каждому пилотному case,
missing IDs, logical/physical accounting, прогноз и консервативный предел.
[ADR-0028](../.adr/0028-full-experiment-freeze-and-reuse.md) задаёт политику
sealed failure и границы будущего запуска. Он имеет `executable=false` и
`http_authorized=false`; это вход для следующего согласованного execution-plan,
а не файл для немедленного `--execute`.

Повторить **offline** проверку из чистой ветки с check environment:

```powershell
# Указать существующие каталоги; roots могут отличаться от исторических путей.
$Data = '<каталог с data/processed>'
$Artifacts = '<каталог с results/raw и исходными plans>'
$Indexes = '<E1 worktree с indexes/e1 и .cache E1 plan>'
./.venv-check/Scripts/python.exe -m scripts.full_experiment verify `
  --data-root $Data --artifact-root $Artifacts --index-root $Indexes
```

`prepare` теми же аргументами строит этот же публичный JSON; `verify` заново
проверяет источники и сравнивает всё содержимое. Ни один режим не запускает
модели: HTTP/socket transport заблокирован. Labels только хэшируются, queries
и corpus доступны для payload/byte bounds; ответы/gold/metrics check/reserve
не читаются. Отсутствующий/повреждённый candidate исключается как incompatible,
verify не даёт успешного допуска. Тексты, raw и абсолютные roots в JSON не
публикуются. Старые manifests/checkpoints/claims не меняются.

Будущий запуск **отдельно**: в issue16/17 потребуется execution-plan для
missing-set, допуск рассчитанного бюджета и проверка его существующим shared
runner перед `scripts.run_dense_target --shared-plan <approved-plan> --execute`.
Текущий freeze не подменяет такой plan; не передавать его напрямую в runner.
Ни эта команда-шаблон, ни неизрасходованные tokens старого run не разрешают HTTP.

Forecast использует только fully measured logical pilot operations: отдельные
complete subtotal и count; все известные partial tokens остаются в отчётном
known_subtotal. Partial/fully unknown и неизвестные поля считаются отдельно.
При отсутствии complete observations forecast=null, а не0. EM/F1 не используются.
Filter ≤1/case Hippo, BGE ≤1/case каждого метода: межметодное сокращение не
выдумывается. Reader input bound строится по всем500 queries и готовым индексам,
cap65536/no truncation неизменен. Filter reserve использует admission upper,
не измеренный будущий контекст. Bytes/reservations не называются measured tokens.
Физические расходы пилота/разработки/индексации и logical reuse раздельны,
source — часть development, unknown reserve — не actual usage.

Итог freeze: **1199compatible completed +1terminal failure +1800missing,
0incompatible**. Максимальный S500 reader bound:63955bytes MuSiQue RAPTOR,
58988bytes HotpotQA RAPTOR,13239/29780bytes corpus top5; прежний cap65536
достаточен для доказанной статической reader-bound, не утверждает размер
backend token window. Filter size остаётся admission upper.

| Новые операции | POST upper | Forecast input / output tokens | Conservative reservation |
|---|---:|---:|---:|
| Reader |1800|3917901.739 /13721.955|69145500|
| Hippo filter |600|1827165 /36574.5|41472000|
| Query BGE |1800|46345.5 /—|4051941|
| Всего |4200|5841708.693 combined|114669441|

Forecast — средние complete tuning logical operations, не actual usage будущих запросов.
E2 pilot physical: LLM3737778input/32093output, BGE29442=3799313known,
2708POST. Development237340/152POST включает source91871; E2 total4036653known/
2860POST. Historical unknown1/reserve22545 сохраняется. E1known32601955,
reserve61588 отдельно; обе стоимости неполны. Полный исторический расход
проекта (включая ранние локальные пробы) здесь не объявляется сверенным.
114669441 — сумма статических worst-case reservations, не операционный budget.
Она превышает старую административную90M величину; эта граница снята. Старый E1cap68M относится только к
индексации, старые pilot caps не дают4200новыхPOST. Перед execution нужен
отдельный допуск research budget, а не молчаливое расширение старого run.


### Историческое предложение бюджета issue15 (до scoped Mu-разрешения)

После исправления partial usage манифест пересобран той же offline-командой.
В текущем пилоте partial operations=0, fully unknown=1. Forecast до/после одинаков:
5841708.693. Known reporting subtotals, physical usage, case decisions и старые
journals/results не менялись. Полностью unknown response не заменён нулевым usage.

**Один операционный вариант:10903320 новых combined tokens и≤4200POST**
(1800reader/600filter/1800BGE). Он вычислен как10834200: сумма300новых вызовов
×максимум полной pilot операции отдельно по6конфигурациям и стадиям; плюс69120 —
один крупнейший admission reserve. Все maxima, sample counts и allocations —
в `budget_proposal.operational_budget_proposal`. Это даёт запас5061611.307 над
mean forecast; число не подбиралось округлением или по качеству ответов.
Static worst-case114669441 сохраняется отдельной оценкой, не operating cap.

Перед любым POST требуется `new_known + new_unknown_reserves + in_flight_reserves
+ exact_candidate_reserve <= approved_cap` и остаток POST caps. Один serial worker;
exact reserve из реального payload bytes+2048+max_tokens(LLM), а не из среднего
forecast. При нехватке места — остановка без POST; unknown/partial/transport/
budget/pin failure — сохранение данных и stop, без retry/автоповышения.
Offline-регрессия проверяет существующий checked_post с insufficient budget и0POST.
Полный future execution-plan обязан реализовать/проверить этот контракт до допуска.

Operating cap не гарантирует завершение всех1800: unseen costs могут превысить
пилотные maxima, а admission может остановить очередь ещё до исчерпания cap.
Тогда остаётся неполный набор и требуется отдельное решение. Исторический E2
unknown reserve22545, расходы E1 и development не входят в новую allocation,
не освобождаются и не суммируются повторно. До согласования этого бюджета
критерий3 issue15 не выполнен; PR37 содержит **Refs #15**, остаётся Draft.
Утверждение бюджета само по себе не разрешает запуск в этой offline-задаче.


## Issue16: начало MuSiQue S500

[Рабочий список](../results/summary/e2-musique-s500-plan.json) — первый
подготовительный результат, **не executable execution-plan и не отчёт запуска**.
Он фиксирует1500case identities:600готовых pilot ответов и900not attempted,
по200reuse+300missing для каждого из трёх методов. Чужой HotpotQA sealed failure
остаётся в historical accounting родителя, не запрашивается повторно и не
объявляется MuSiQue failure. Фактический итог приведён ниже; worklist остаётся первоначальным offline-снимком.

Список строится тем же offline planner после полного existing artifact gate:

```powershell
./.venv-check/Scripts/python.exe -m scripts.full_experiment prepare-musique `
  --artifact-root $Artifacts --data-root $Data --index-root $Indexes
./.venv-check/Scripts/python.exe -m scripts.full_experiment verify-musique `
  --artifact-root $Artifacts --data-root $Data --index-root $Indexes
```

Вход — существующий `full-experiment.json` из PR37; canonical SHA связывает
его с worklist. Старый worklist остаётся immutable offline-снимком, не меняется
на executable задним числом. Старые runtime/code/result/journal SHA сохраняются.

### Разрешение Mu-only и исполнение

Пользователь делегировал расчёт бюджета с запасом и разрешил его в этой задаче
2026-10-29. [Запись согласия](../results/summary/e2-musique-s500-authorization.json)
содержит точную цитату; выбранный агентом cap —5990220new combined tokens,
≤2100POST(900reader/300filter/900local BGE). Это5921100по maxima полностью
измеренных pilot операций+69120admission headroom. Ни HotpotQA, ни весь
двухдатасетный cap PR37 автоматически не разрешены. Завершение900missing
не гарантировано: payload reservation может исчерпать остаток раньше.

```powershell
./.venv-check/Scripts/python.exe -m scripts.full_experiment prepare-musique-execution `
  --artifact-root $Artifacts --data-root $Data --index-root $Indexes
./.venv-check/Scripts/python.exe -m scripts.full_experiment verify-musique-execution `
  --artifact-root $Artifacts --data-root $Data --index-root $Indexes
# В проверенном experimental environment, последовательно для dense/hipporag2/raptor:
python -m scripts.run_dense_target --shared-plan .cache/e2-musique-s500-execution-plan.json `
  --execute --shared-method dense --output-dir results/raw/e2-musique-s500-v1 `
  --approved-plan-sha256 $ExactPlanFileSHA --env-file $MainEnv
# Для hipporag2/raptor передаются прежние --hippo-source / --raptor-source.
# На первой fatal ошибке остановить очередь: следующий метод не запускать.
```

`scripts.e2_s500` интегрирован в существующие verify/Calls/summary/write_report
только для новой версии плана; старый AST runner после удаления этих guards
сравнивается с закреплённым runtime. Исходная full freeze не переписывается.
Execution-plan заново проверяет все артефакты offline и связывает600completed
Mu cases с источниками. У каждого метода те же500ordered IDs; запросы выполняются
лишь для300missing. Gold не передаётся генерации; evaluator запускается после неё.
Parent claims не позволяют перенести тот же бюджет в другую output-directory.
Один worker, durable checkpoint перед POST; known+candidate reserve≤cap до
каждого нового вызова. Reserve=serialized payload UTF8 bytes+2048+max_tokens
для LLM. Отсутствующий usage не ноль: новый partial/unknown/transport/infra/pin/
budget failure останавливает очередь без retry/recovery. Исторический Hotpot
unknown не является Mu failure и не даёт разрешения на повтор.

После worker terminal report проверяет response/checkpoint/journal SHA успешных
случаев,500IDs/method и исходные parent pins; ошибки явно сохранены. Fatal case
без полного response не объявляется строго проверенным успехом: отчёт содержит
`strict_success_audit_complete=false`, исходные artifact SHA, unknown и неполное
сравнение. Private evaluation.json содержит per-case оценки для задач12/14;
публичная сводка не содержит корпуса/ответов. Fresh latency считается только
для новых случаев; reused latency не fresh E2E. Новые physical reader/filter/BGE
затраты отделены от inherited logical usage, глобального source/development и E1.
RAPTOR provenance не passage recall@5; S500 включает development, mixed Hippo
extractor/errors и неполнота исходных расходов раскрываются. Issue16 остаётся
Draft/Refs #16 до реального завершения и проверки набора.


### Фактическая остановка MuSiQue S500

Run7936654d-8820-4449-803b-f7ef6074424a остановлен guard на новом remote reader
unknown, не на бюджете:700new completed+1transport failure,199missing;
с600reuse это1300completed/1failed/199not_attempted. [Неполная таблица](../results/summary/e2-musique-s500.md).
RAPTOR case3hop1__90327_83076_319330 не имеет ответа; checkpoint started,
usage null, reserve15732 не actual. Новые known2252792/1702POST; cap5990220/2100
сохранён, retry/recovery0. Ночного разрешения на технические исправления
недостаточно для обхода unknown-stop/failed-run guard: локальная кодовая ошибка
не обнаружена. Отдельное решение может касаться лишь199unattempted с новым
verified immutable lineage и прежним совокупным бюджетом, без повтора unknown.
Текущий результат не заменяет полный500-ID/method comparison; Refs #16.


### Явно разрешённое unattempted-only продолжение

После уведомления об unknown и необходимости решения о199не запущенных cases
пользователь ответил «Делай то что нужно». Это разрешение завершить только эти
199случаев, не повторять неизвестный запрос и не расширять исходный cap.
[Точная запись](../results/summary/e2-musique-s500-unattempted-authorization.json).
Новый private plan строится existing `scripts.full_experiment prepare-musique-unattempted`
с `--execution-plan .cache/e2-musique-s500-unattempted-plan.json`; старый root plan
не переписывается. Сначала strict parent audit/claim/code-runtime/source pins и
existing `e2_pilot.seal_unknown_reader`, затем ровно199missing RAPTOR IDs.
Все1301родительских outcomes immutable, включая700new completed,600reuse и1failure.

Остаток пересчитывается из terminal journal:3721696tokens/398POST после
2252792known и15732reservation; filter0, reader199/local BGE199. Это остаток того
же5990220/2100, не новый расход сверх cap. Per-POST admission остаётся строгим,
никакого worst-case promise завершения. New child допускается один раз; новый
unknown/transport/infra/pin/budget failure снова останавливает очередь без retry.
Unknown case имеет отдельный infrastructure marker и pipeline EM/F1=0, согласно
переиспользуемой sealed-failure policy; он не называется неверным ответом reader.
Usage остаётся null; reservation не actual. При завершении expected1500outcomes
будут1499answers+1failure, а не1500ответов. Common evaluator не исключает failed ID.

Parent physical и child physical учитываются по одному разу, отдельно от
pilot/development и E1. S500 latency/usage объединяет обе physical части, исключая
начальные600reuse; данные child-only также сохранены. Новый runtime фиксируется
отдельно от parent e144ad9. До terminal audit работа Draft/Refs #16; HotpotQA,
новые модели/индексы/prompt/cap/retrieval/split и следующие задачи не запускаются.


### Проверенный итог MuSiQue S500

[Единая таблица](../results/summary/e2-musique-s500.md)/[safe JSON](../results/summary/e2-musique-s500.json):
1500uniqueoutcomes=1499answers+1sealed transportfailure,0notattempted.
Dense EM/F1=34.80/44.93%, Hippo43.40/53.55%, RAPTOR32.40/42.47%.
Childba393849/runtimea0 закончил199unattempted/398POST/802989known/newunknown0.
Root7936654d/e144 остаётсяfailed; unknownreader не повторён. Sealed failure
pipeline0 — infrastructure marker, не неверный ответreader; usage остаётсяnull.
S500physical3055781known/2100POST +reserve15732; E2csource/development7092434/
4960POST,2unknown/reserve38277,cost_complete=false; E1отдельно. Logicalreuse
иsource91871 повторно не добавлялись. ПолныйauditSHA/IDs/lineage выполнен.

Localtracking3MLflow/3Langfuse views по500:fulltext/order/answers,usage/null и
36artifact/linkedJSONL roundtripSHA проверены без modelcalls. Послеterminal
обнаружен иисправлен только native observation cursor reader:API meta.cursor
не читался как next_cursor,1000/2001observations. Поддерживаются оба schema,
repeatedcursor rejected;3targeted tests/native readback прошли. Dense trace
дочитан без повторного экспорта. AST guard дляofflinefreeze допускает изменение
толькоget_all_langfuse_observations, не exporter/generator; старые execution
codeSHA не переписываются. Sourceexecutiona0/e144 отделены отpostprocessorHEAD.
Privatepercasepaths/receipt находятсявchildraw; safeIDs/audit витоговомJSON.
Параметры/модели/индексы неизменны, S500development/mixedHippo/errors/replay
ограничения сохранены. Следующиезадачи не запущены; Draft/Refs #16.


### Воспроизводимый полный отчёт S500

`e2_s500.write_report` восстанавливает дополнительные разделы из проверяемого
`results/summary/e2-musique-s500-evidence.json`, а не из старого destination JSON.
Привязка к run/plan/manifest, pinned audit/receipt/evaluation и сверка cumulative
accounting обязательны. Per-case raw не перезаписывается; пересборка проверяется
в новом временном output с запрещённым HTTP. Команда и точные входы задач12/14
даны в [итоговой таблице](../results/summary/e2-musique-s500.md#воспроизведение-и-передача-результатов-offline).
Дополнительный файл — проверяемое приложение к одному отчёту, не новый эксперимент.
PR38 остаётся Draft и зависит от PR37; научные формулировки согласованы по
сообщению пользователя, опубликованное bot/GitHub review не утверждается.


## Текущее бюджетное решение issue15

Прямое согласие пользователя от2026-10-29: «Я согласен с этими лимитами»
в ответ на предложение4 982 220новых combined tokens/2100POST только HotpotQA.
Это согласование операционного бюджета как протокольного решения в PR37,
**не команда запуска**. Научные O/N/R/H уже согласованы по сообщению пользователя;
публикация bot/GitHub review не утверждается.

| Scope | Утверждённые новые tokens | POST caps | Статус |
|---|---:|---|---|
| MuSiQue | 5990220 | reader900/filter300/localBGE900 =2100 | Ранее разрешён и выполнен в PR38; отдельный continuation199 не расширял caps |
| HotpotQA | 4982220 | reader900/filter300/localBGE900 =2100 | Бюджет согласован; execution не запущен/не разрешён этим решением |

Hot allocation4913100 = сумма300missing calls × maximum fully measured pilot
operation для каждого метода/стадии; плюс69120 для допуска очередного запроса.
Источник — неизменный `budget_proposal.operational_budget_proposal.allocations`
в frozen `results/summary/full-experiment.json`, строки HotpotQA. Scope — только
900ранее не запущенных method/question cases,600исходов пилота переиспользуются,
включая один sealed transport failure. Это не600успешных ответов.

Исходный общий proposal10903320 и static worst-case114669441 остаются историческими
расчётами, не переписываются и не называются actual usage. Сумма отдельно принятых
allocation caps10972440 выше старого proposal на69120: admission headroom теперь
отдельный у двух последовательных этапов. Это не перенос неиспользованного Mu
остатка; исходный Mu cap не расширяется. Исторические costs и unknown reserves
(Hot22545/Mu15732/E1отдельно) сохраняются, не считаются новыми расходами или нулём.

Перед любым будущим Hot POST необходимы отдельный проверенный missing-only
execution-plan, актуальная сверка ID/data/index/model/reader/evaluator/source/
claims/остатков caps и отдельная команда запуска. Один serial worker, retry0.
До запроса: known+unknown reservations+in-flight+exact candidate reservation
не выше4982220, totalPOST не выше2100 и отдельные operation caps не превышены.
При нехватке — stop без POST. Новые partial/unknown/transport/infra/pin/budget
ошибки останавливают очередь без retry/автопродолжения; sealed unknown не повторять.
Прежняя политика известных reader case failures сохраняется. Reader cap512,
prompt/model/top5/index/split/SDK и строгий Hippo filter не меняются.
Завершение900cases не гарантируется; новый расход/отступление потребует нового
решения. Никаких моделей/embeddings/индексации/tracking-export этим согласованием
не запускать. Анализ signal-check для выбора сигнала issue21 не разрешён.

Все четыре критерия issue15 выполнены: шесть configurations/ID закреплены;
каждый reused result проверен/исключён; missing-set, оценки, scoped caps и stop
условия зафиксированы;300/100/100 и development-ограничения сохранены.
PR37: Closes #15, Draft. Исходный frozen manifest/runtime SHA/raw неизменны.
Записи Mu-согласий остаются в существующем PR38:
[budget](https://github.com/SPStan/rag-graphrag-research/blob/codex/musique-s500-comparison/results/summary/e2-musique-s500-authorization.json),
[continuation](https://github.com/SPStan/rag-graphrag-research/blob/codex/musique-s500-comparison/results/summary/e2-musique-s500-unattempted-authorization.json).
