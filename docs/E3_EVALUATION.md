# E3 — общий evaluator и парные интервалы, issue18

Технический результат:3метода×2датасета×500frozen IDs, **3000учтённых исходов**,
2996completed+4attempted_failed,0not_attempted. Одна
[таблица E3](../results/summary/e3.md), [safe JSON](../results/summary/e3.json)
с интервальными оценками, input/code/version hashes и example IDs.
Научные O/N/R/H требуют повторного актуального согласования перед merge.
Refs #18; issue и PR остаются открытыми. Полное техническое ревью запрашивается
отдельно после проверок и не заменяет научного согласия.

## Метод и воспроизводимость

Строгий join по ordered frozen IDs каждого датасета. Duplicate/missing/unexpected
ID, not_attempted, несопоставимый reader, неполный terminal source или SHA drift
останавливают анализ. E3 повторно применяет общий `e2.score_result` к saved answers
и labels, проверяет все четыре сохранённых per-case метрики: EM, F1,
passage recall@5 и supporting provenance, а также response/checkpoints.
Gold используется только offline-оценщиком; новых model/HTTP/index/tracking calls нет.

**1000paired resamples, seed42, PCG64,95%percentile [2.5%,97.5%]**, по500вопросов
с возвращением. Одна матрица индексов для всех3систем/метрик внутри датасета.
NumPy2.5.3/Python3.12.6 и SHA матрицы записаны в JSON; одинаковый seed иN дают
одинаковую positional matrix двух отдельных датасетов, между датасетами вопросы
не спариваются. Legacy10000 и pilot2000 не переписываются. Версия E3 —
`e3-paired-S500-v1`; pure kernel `compare_asbuilt.bootstrap_mean` общий с legacy.

Команда из worktree PR40:
```powershell
./.venv-check/Scripts/python.exe -m scripts.e3_evaluation `
  --artifact-root 'C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG' `
  --data-root 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG' `
  --output results/summary/e3
```
Hot plan/output берутся из точного active binding с SHA и допустимым private path;
проверяются оба terminal manifests,1071parent+429child Hot refs, immutable parent
files/usage и SHA evaluations/labels/IDs/public reports. У Mu1499ответов+1failure,
у Hot1497+3. Сохранённые ошибки — pipelineEM/F1=0, не неверные reader answers;
not_attempted нулём не заменялся. Retrieval следует прежнему общему evaluator:
пустой pipeline retrieval даёт0; настоящий missing metric остаётсяnull с coverage,
без искусственного полного CI. RAPTOR provenance не passage recall@5; paired
provenance−Dense recall не вычисляется.

Реальная E3 дважды воспроизведена в новых outputs с запрещённым socket.connect:
JSON/MD byte-identical. После уточнения отчётного scope Hot cost повторён тот же
пересчёт: меняется input hash отчёта, числовые scores/CI не меняются.12целевых
synthetic tests прошли (identical/constant difference, permutation, ID gates,
failures, repeatability,0HTTP и отклонение изменённого recall через loader/CLI), mandatory hook финального коммита/его CI отдельно.
Промежуточная ошибка Windows setup при системном TEMP не была тестом логики;
повтор с предусмотренным TEMP дал11passed; после проверки recall —12passed. При повторении нужен разбор среды,
не изменение эксперимента. Активные часы студента не измерялись.

## Результат и границы вывода

EM/F1 means/CIs и retrieval/provenance CIs полностью в safe JSON; таблица использует
доли0..1. Парные ΔF1 в процентных пунктах:

- Mu: Hippo−Dense **+8.61 [5.24;11.98]**, RAPTOR−Dense **−2.47 [−5.24;0.57]**.
- Hot: Hippo−Dense **+5.67 [3.37;8.28]**, RAPTOR−Dense **+0.90 [−1.14;3.04]**.

Для Hot наблюдаемый разрыв Hippo/Dense не подтверждает ожидавшуюся границу<2п.п.
Предварительная гипотеза не переписана по результату. Mu согласуется с ожидаемым
приростом в этом S500, но S500 включает development/pilot и не является независимым
подтверждением. Pointwise CI не simultaneous; CI с0 не доказывает равенства методов
или разности<2п.п. Новых tests equivalence/margin/параметрического подбора нет.
Mixed Hippo extraction/errors и semantic_verified=false сохранены.

Расход берётся из pinned reports, не из bootstrap. Hot fresh physical2763839known/
2099POST, Mu fresh3055781known/2100POST с historical Mu unknown/reserve15732.
Cumulative E2 **9856273known/7059POST**,2unknown/reserve38277,cost_complete=false.
Source/development/reuse не прибавляются второй раз; E1 отдельно32601955known/
reserve61588/cost_complete=false. Unknown/reservation не превращается в actual0.
Новых inference или tracking-export при E3 нет. Per-query fresh latency в исходных
reports относится к300fresh cases/метод, исключает setup/4s pacing иinitial200reuse;
это не непрерывное fresh500E2E.

## Фиксированные tuning-примеры расхождений

Правило выбрано до разбора: первые5ordered tuning300 IDs с неодинаковым F1 на
каждом датасете. Ни check/reserve, ни signal issue21 для выбора не использовались.
Ниже объяснения по сохранённым ответам и retrieval scores, без публикации raw
вопросов/ответов/корпуса. Это иллюстрации, не оценки частоты и не каузальные выводы.

| Dataset / ID | Наблюдение |
|---|---|
| Mu `2hop__21104_16334` | Dense точен; Hippo выбрал другую сущность при recall0.5. RAPTOR сократил ответ: F1=2/3,EM0 при provenance1; lexical policy не расширялась aliases постфактум. |
| Mu `2hop__126306_396277` | Dense/RAPTOR выбрали другое произведение; Hippo точен. Recall Dense0.5/Hippo1, RAPTOR provenance0.5: различие согласуется с неполнотой evidence, но причинность не установлена. |
| Mu `2hop__488811_30078` | Hippo добавил исторический квалификатор: F1=0.8,EM0; Dense/RAPTOR назвали другие стороны. Полный Hippo recall не гарантирует EM. |
| Mu `3hop1__694534_160088_73916` | У RAPTOR неверный числовой показатель и provenance1/3; Dense/Hippo точны. Dense recall2/3 достаточен для правильного ответа в этом примере. |
| Mu `4hop1__802394_153080_159767_81096` | Hippo/RAPTOR выбрали других людей в многошаговом вопросе; Dense точен при recall0.75, остальные coverage0.25. Это не основание выбирать routing signal. |
| Hot `5abd882f55429924427fd045` | Dense дал другой год при recall0.5; Hippo/RAPTOR точны с coverage1. |
| Hot `5a80ad205542992bc0c4a79d` | Dense/Hippo перепутали запрошенного предшественника с связанной фигурой/титулом. Token overlap даёт частичный F1 без EM; даже Hippo recall1 не обеспечивает верную связь. |
| Hot `5adc3a7055429947ff173913` | RAPTOR добавил лишнее обозначение к национальности: F1=0.5,EM0 при provenance1. Dense/Hippo точны; provenance не проверяет точность формулировки summary/answer. |
| Hot `5adc6f6255429947ff173961` | Dense выбрал противоположный вариант сравнения при recall1; Hippo/RAPTOR точны. Наличие supporting passages не гарантирует reader reasoning. |
| Hot `5abaee4f5542996cc5e49f15` | RAPTOR дал противоположный yes/no ответ при provenance0.5; Dense/Hippo точны сrecall1. Нормализация yes/no не менялась. |

Все4failure markers сохраняются в полном per-case ledger независимо от этих
примеров: Mu historical transport; Hot historical transport, reader_length и
filter_shape_invalid. Они не удалялись из средних и не выдаются за model QA errors.

## Передача и критерии

Private root: `C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG`.
Per-case оценки задач12/14: `results/raw/e2-musique-s500-unattempted-v1/evaluation.json`
и `results/raw/e2-hotpotqa-s500-unattempted-v1/evaluation.json`, соседние manifest/
usage/response/checkpoint и parent refs. Планы, orderedIDs/source revisions,
model/reader/index pins и все input hashes перечислены в `e3.json.inputs`;
error fields `status/error/fatal/operations` не маскируются.
Hot evidence/report получены в [PR39](https://github.com/SPStan/rag-graphrag-research/pull/39),
PR39 уже слит в master и интегрирован обычным merge в PR40.
Private source артефакты остаются на месте; execution plans и raw неизменны.

| Критерий issue18 | Свидетельство |
|---|---|
| E3:3метода×2датасета |3000unique frozen cases,2996completed+4failed,0not_attempted |
| Парные CI/seed/count/tests | 1 000 общих ресэмплов; seed 42; 95 % percentile; 30 целевых тестов |
| Воспроизведение без моделей |Два byte-identical real rebuilds с0HTTP,input/code/version SHA |
| Ошибки/ограничения |Полный error ledger,10фиксированных tuning examples,development/CI caveats |

Следующий шаг — техническая приёмка PR40 перед отдельно разрешённым merge.
Merge остановлен из-за раскрытия per-case control/reserve scores в истории.
Научные O/N/R/H [согласованы](https://github.com/SPStan/rag-graphrag-research/pull/40#pullrequestreview-5845238116)
без изменения формулировок; научное согласие не заменяет технические проверки. Новые модели/индексация/tracking-export/holdout/signal
и следующие исследовательские задачи в этом блоке не запускались.


## Проверка перед полным ревью — 9 ноября

Для исходного HEAD 0082a55 подтверждён зелёный CI Windows/Linux, conventions и
secrets. В коде собраны 12 целевых тестов; таблица критериев приведена к этому
числу. Сеть при offline-пересчёте была запрещена: проверены 3 000 исходов,
сохранённые scores и входные SHA; метрики, интервалы и выбранные примеры совпали.
Два рендера дали одинаковые байты. Переносы строк кода и Markdown LF/CRLF
учтены отдельно от содержимого. Старые raw и опубликованные численные отчёты
не записывались. Таблица HotpotQA также воспроизведена из сохранённого JSON.

Планы, manifests, evaluation, usage и все parent-файлы обоих датасетов доступны
локально по указанным выше путям. Для независимого воспроизведения куратору
потребуются эти private-артефакты: в GitHub они не опубликованы. Научное
согласование и полное ревью не объявляются полученными этим подтверждением.


## Строгая приёмка входов и демонстрация пересчёта

Команда E3 сверяет execution plan с замороженным
`results/summary/full-experiment.json` и его digest: весь контракт issue15,
включая top_k=5, reader/options/templates/parser/evaluator, Hippo-параметры,
embedding revision и порядок контекста. Отдельно проверяются byte gate,
frozen IDs/source/labels/split/index pins и условия parent-плана.
Одинаковые неправильные настройки двух датасетов также не проходят:
основание сверки — frozen-протокол, а не совпадение планов между собой.

Общий evaluator заново считает оценки из сохранённых ответов.
Штатный E2 summary заново собирает строки, counts, latency и logical usage.
Они должны совпасть с private evaluation и публичной сводкой E2.
Новые physical usage/POST сверяются с журналом child, parent physical — с
проверенным журналом parent; неизвестный расход не заменяется нулём.
Historical source/development сверяются с frozen snapshot и не добавляются
как новый расход. CLI запрещает socket connect/connect_ex, не пишет в raw.
Относительный и абсолютный путь к одному журналу нормализуются; содержание,
SHA и учёт не ослабляются.

Проверка 11 ноября на сохранённых артефактах:
**3 000 уникальных исходов = 2 996 ответов + 4 pipeline failures**.
Два запуска штатной команды дали одинаковые байты JSON.
Все **16 676** проверенных immutable файлов сохранили SHA;
ранее опубликованные метрики, интервалы и десять примеров совпали.
30 целевых тестов проверяют rebound SHA при смене top_k,
подмену F1/counts/logical usage/physical expense и unknown/partial journal.
Сначала тестам была недоступна стандартная Windows temp-папка;
с предусмотренными проектом TEMP/TMP они прошли. В синтетической фикстуре
также исправлена недостающая parent directory; эксперимент не менялся.

Fingerprints полной private-пересборки до ограничения публичных scores:

- JSON двух пересборок: `0dea854ebc46cb3b993b8704ea72d37a033635aeba44a31711d7cc47ec841a24`.
- Digest исходных файлов: `7f97a8aee8da153bdbcd7566929c4d3eb9db40fc16d3224b4fe71bebe39cebf3`.
- Digest массива оценок: `d92666caf02d84605fa08d89bcab34f515130a6e171f4af67b208121180d8276`.

Полный пересчёт из worktree PR40 в новый output:

```powershell
./.venv-check/Scripts/python.exe -m scripts.e3_evaluation --artifact-root "C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG" --data-root "C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG" --output .cache/e3-independent-rebuild
```

### Передача оценок для oracle-анализа №20 и защита контроля

Полные 3 000 per-case scores хранятся только в private-файле:
`C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG/.cache/e3-oracle-inputs-private.json`.
Файл игнорируется Git. Он содержит оценки, статусы и входные SHA, без gold,
текстов ответов и контекстов; oracle-анализ №20 не запускался.
Исходные полные evaluation/manifest/usage остаются по указанным выше private-путям.

Публичный `e3.json.question_scores` ограничен tuning300 каждого датасета:
1 800 строк (300 ID ×3метода ×2датасета). В нём нет per-case scores control100
или reserved100. Агрегаты E3 и bootstrap используют все500ID и остаются прежними.
Регрессия через штатную CLI проверяет это разделение; фильтр не опционален.
Две реальные offline-пересборки после ограничения совпали побайтно:
1 800 public tuning scores,0control/reserve scores; агрегаты по3 000исходам
и интервалы не изменились. SHA текущего JSON:
`e3e3db15ef35c1cff6fec958decbee1318d54cc3d9f22f01b5b5a705d3b1903a`;
digest tuning scores:
`6fe58b82d148a0b50ff498a454be12b58ec02977f29a47344729313f67efef43`.

**Раскрытие в истории:** коммит4793612 уже содержал полный массив — в том числе
600 control и600 reserved per-case scores. Gold-текстов он не содержал, однако
EM/F1 по методам могут служить target labels для oracle/router. Удаление из
текущей версии не удаляет опубликованный Git history и не восстанавливает
независимость контроля. История не переписывается; merge PR40 остановлен до
решения пользователя о последствиях. Нельзя считать эти случаи pristine либо
использовать их для подбора сигнала/порога. Полное научное согласование формулировок
не заменяет принятие этого отклонения.

Для независимой проверки всех интервалов нужен private ledger. Из worktree PR40:

```python
from pathlib import Path
from scripts import e3_evaluation as e3, run_dense as dense

v = dense.read_json(Path("results/summary/e3.json"))
private = dense.read_json(Path(
    "C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG/.cache/e3-oracle-inputs-private.json"
))
scores = private["question_scores"]
assert e3.e2.target.digest(scores) == private["question_scores_sha256"]
for expected in v["datasets"]:
    rows = [r for r in scores if r["dataset"] == expected["dataset"]]
    ids = [r["question_id"] for r in rows if r["method"] == "dense"]
    assert e3.analyze(rows, expected["dataset"], ids) == expected
```

Проверка текстов и supporting labels по-прежнему требует private исходных
артефактов; их куратор независимо не проверял.
