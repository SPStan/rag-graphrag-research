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

Forecast рассчитан по logical pilot operation means без просмотра EM/F1.
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

Forecast — средние tuning logical operations, не actual usage будущих запросов.
E2 pilot physical: LLM3737778input/32093output, BGE29442=3799313known,
2708POST. Development237340/152POST включает source91871; E2 total4036653known/
2860POST. Historical unknown1/reserve22545 сохраняется. E1known32601955,
reserve61588 отдельно; обе стоимости неполны. Полный исторический расход
проекта (включая ранние локальные пробы) здесь не объявляется сверенным.
Новый114669441 — предлагаемый conservative cap, превышающий старую
административную90M величину; она снята. Старый E1cap68M относится только к
индексации, старые pilot caps не дают4200новыхPOST. Перед execution нужен
отдельный допуск research budget, а не молчаливое расширение старого run.
