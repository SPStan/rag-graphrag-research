# HotpotQA S500 — протокол issue17 на согласование

Статус: подготовительный Draft PR, Refs #17. Полный HotpotQA S500 не выполнен.
Новых API/model/embedding/indexing/tracking вызовов в этой подготовке нет.
Научные формулировки нового этапа ожидают проверки куратора; прежнее согласование
PR37/38 не объявляется согласованием этой карточки. Бюджет уже принят отдельно.

## Задача и вход

Закончить сравнение Dense, HippoRAG2 и RAPTOR на тех же500ordered HotpotQA IDs,
с общим reader/оценщиком и тремя готовыми индексами. Выполнять только900ранее
не запущенных method/question cases;600исходов пилота переиспользовать, включая
599ответов и1sealed transport failure. Один question ID у разных методов —
разные случаи. Плановое покрытие1500случаев не означает1500успешных ответов.

Источники: [issue17](https://github.com/SPStan/rag-graphrag-research/issues/17),
[протокол E2](E2_EVALUATION.md), [SPEC](SPEC.md),
[неизменный frozen manifest](../results/summary/full-experiment.json),
[бюджетное решение ADR0028](../.adr/0028-full-experiment-freeze-and-reuse.md#текущее-бюджетное-решение-issue15).
PR37/38 слиты, issues15/16 закрыты. Готовые индексы не перестраивать.

Доступные приватные входы относительно E2 artifact-root:
`results/raw/e2-pilot200-unattempted-v1/evaluation.json`, соседние `manifest.json`
и `usage.jsonl`; точные source/parent refs берутся из их lineage, не угадываются.
Наличие evaluation/manifest подтверждено; полный source gate нового Hot plan
в этом подготовительном PR ещё не выполнен. Тексты/raw остаются локально.

## Неизменные условия и бюджет

- Одна модель reader `iairlab/qwen3.8-27b`, local BGE-M3, общий prompt/parser,
  cap512, temperature0, seed42, thinking=false, top5/full text/order,
  byte admission65536 и закреплённые SDK/source/data/index hashes из issue15.
  Provider revision/quantization не сообщены; это ограничение, не известная версия.
- Новые combined tokens≤4982220; POST≤2100: reader≤900, Hippo filter≤300,
  query embedding≤900. Retry0. Основание4913100по pilot maxima+69120admission.
  Согласие пользователя уже записано в ADR0028, повторно его не запрашивать.
- До каждого POST: new known+unknown/in-flight reservations+exact candidate
  reservation≤cap; проверка total и operation POST caps непосредственно в transport.
  Нехватка места — stop до POST; гарантии завершить900cases нет.
- Historical Hot unknown object439b99af…/run fadc0797 не повторять, usage=null,
  reserve22545 не actual usage. Mu unknown/reserve15732 и E1known32601955/
  reserve61588 остаются отдельно; прошлые расходы/reuse не прибавлять повторно.
- Новые partial/unknown/transport/infra/pin/budget ошибки — stop без retry/
  автопродолжения. Known reader length/empty/parser — case failure без retry,
  дальнейшие cases продолжаются по прежней policy. Hippo filter остаётся fatal.

## Реализация в этом же PR после согласования

1. Проверить500IDs, data/index/code/model/reader/evaluator pins, producer journals,
   response/checkpoint hashes и все600pilot outcomes. Terminal parent/manifests/
   claims не переписывать; новое output/plan/lineage для900missing.
2. Сверить несколько заранее заданных HotpotQA examples: aliases/yes-no ответы,
   supporting facts→passage IDs, названия/порядок, отсутствие gold/supporting labels
   в генерации. Общие EM/token-F1/recall формулы не менять по результатам примеров.
3. Расширить существующие planner/shared runner/accounting/report пути. Нынешний
   `scripts/e2_s500.py` и команды `prepare-musique-*` привязаны к MuSiQue: их нельзя
   запускать как HotpotQA с подменой названия. Проверяемого Hot execution CLI пока нет;
   точную команду добавить здесь после реализации и offline tests, до разрешения API.
4. Offline tests через runner: exact missing/reuse, no paid duplicates/unknown retry,
   source/payload/index drift, active worker/claims, cap/reservation/operation limits,
   сохранение known usage и исходного исключения, Hot labels mapping, failed versus
   not_attempted. Негативные проверки обязаны дать0POST.
5. По прямому разрешению пользователя от30октября: один serial worker, готовые индексы/cache exact
   keys; результаты каждого случая/attempt с durable accounting. При завершении
   строгий audit1500unique IDs, common evaluator и immutable lineage, не один PID.
6. Сводка EM/F1/coverage/failures/retrieval/latency и reader/filter/BGE usage.
   Logical reuse и physical expense раздельно, RAPTOR provenance не passage recall@5.
   S500 включает development; mixed Hippo errors/semantic_verified=false и неполная
   стоимость E1/source сохраняются. Новый tracking-export отдельно здесь не запускать.

## Приёмка и передача

| Критерий issue17 | Что нужно для выполнения | Сейчас |
|---|---|---|
| Все500ID трёх методов учтены | 1500outcomes без скрытого исключения failures | Не выполнен: только pilot |
| Reader/оценщик и Hot labels | Pins, примеры преобразования, целевые tests | Запланировано, ещё не проверено |
| Расход/reuse/лимиты | Transport guard, журналы, immutable lineage, audit | Бюджет согласован; execution gate не готов |
| Доступные артефакты | Final per-case evaluation/manifest/usage/SHA и safe summary | Full Hot artifacts ещё отсутствуют |

Планируемые output paths — предложения, не существующие результаты:
`results/raw/e2-hotpotqa-s500-v1/` и `results/summary/e2-hotpotqa-s500.json/.md`.
Передать per-case failure markers задачам12–15, не представлять transport failure
как неверный reader answer. Старый failed case получает согласованный pipeline0
и отдельный infrastructure marker, unknown usage не превращается в0.

До выполнения критериев — Refs #17, Draft; без Ready/merge/Closes. Запуск фиксированного протокола прямо разрешён
пользователем 30 октября; научное согласование требуется перед merge.
Техническая готовность, научное согласование и разрешение исполнения различаются.
Активные часы студента не измерялись; новых результатов качества не заявляется.


## Выполненная offline-подготовка после запроса запуска

Пользователь разрешил подготовить запуск, но подтвердил, что согласование
куратора PR39 ещё ожидается перед merge. Это не запрет исполнения. Добавлены
`prepare-hotpotqa`/`verify-hotpotqa` в существующий `scripts.full_experiment`:
неисполняемый worklist, `executable=false`, `http_authorized=false`.
Он сохраняет599compatible answers+1sealed failure и900missing, budget4982220/2100.
Это не executable plan и не Hot transport guard. Старый Mu worklist идентичен.

```powershell
./.venv-check/Scripts/python.exe -m scripts.full_experiment prepare-hotpotqa `
  --artifact-root $Artifacts --data-root $Data --index-root $Indexes
./.venv-check/Scripts/python.exe -m scripts.full_experiment verify-hotpotqa `
  --artifact-root $Artifacts --data-root $Data --index-root $Indexes
```

Сначала выполняется existing full freeze/source/index gate, затем сверка с
immutable full-experiment.json. Публичный output —
`results/summary/e2-hotpotqa-s500-plan.json`. Повторная подготовка допускает
только равное содержимое; изменённый worklist не перезаписывается.
28целевых tests прошли: new CLI0HTTP, budget/source/ID tamper, sealed unknown
identity и legacy Mu equality. Это не проверка реального исполнения.


Реальный prepare/verify прошёл с заблокированным socket.connect: два прохода
source/index/lineage gate, все6индексов и source cases проверены, HTTP0.
Frozen full-experiment.json и прежний Mu plan не менялись. Worklist остаётся
неисполняемым; budget_proposal.authorized=false не отменяет отдельного согласия
ADR0028, а не даёт транспортного допуска. Hot runner/guard ещё не реализован.

## Исполнение по разрешению 30 октября

Hot связывается с общим runner через `scripts.e2_hotpot`, shared
`prepare_dataset`/`guard_dataset`, без подмены dataset в Mu wrapper.
Авторизация: `results/summary/e2-hotpotqa-s500-authorization.json`;
приватный plan: `.cache/e2-hotpotqa-s500-execution-plan.json`.
Caps4982220combined/2100POST, reader900/filter300/BGE900, retry0.
Старый sealed transport case никогда не повторяется.
Failed manifest запрещает повторный запуск; новый unknown/partial блокирует очередь.
После чистой паузы тот же runner может переиспользовать только проверенные
durable checkpoints; новый output не является способом обхода claims.
Автоматизация ведёт общий счётчик максимум2 безопасных возобновлений.
Если guard не допускает доказуемое продолжение, inference останавливается.

Shared terminal report генерируется заново в том числе в временный output,
привязывает manifest/journal/parent SHA и отдельный pinned Mu terminal report.
Logical reuse не прибавляется к physical expense. Нового tracking-export нет.
