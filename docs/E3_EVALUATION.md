# E3 — общий evaluator и парные интервалы, issue18

Технический результат:3метода×2датасета×500frozen IDs, **3000учтённых исходов**,
2996completed+4attempted_failed,0not_attempted. Одна
[таблица E3](../results/summary/e3.md), [safe JSON](../results/summary/e3.json)
с интервальными оценками, input/code/version hashes и example IDs.
Scientific O/N/R/H PR40 pending перед merge; Draft/Refs #18, без Ready/merge.

## Метод и воспроизводимость

Строгий join по ordered frozen IDs каждого датасета. Duplicate/missing/unexpected
ID, not_attempted, несопоставимый reader, неполный terminal source или SHA drift
останавливают анализ. E3 повторно применяет общий `e2.score_result` к saved answers
и labels, проверяет соответствие сохранённым per-case scores и response/checkpoints.
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
пересчёт: меняется input hash отчёта, числовые scores/CI не меняются.11целевых
synthetic tests прошли (identical/constant difference, permutation, ID gates,
failures, repeatability,0HTTP), mandatory hook финального коммита/его CI отдельно.
Промежуточная ошибка Windows setup при системном TEMP не была тестом логики;
повтор с предусмотренным TEMP дал11passed. При повторении нужен разбор среды,
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
это зависимость по данным; git base PR40 независим, source artifacts не копируются.

| Критерий issue18 | Свидетельство |
|---|---|
| E3:3метода×2датасета |3000unique frozen cases,2996completed+4failed,0not_attempted |
| Парные CI/seed/count/tests |1000shared draws/seed42,95%percentile,11targettests |
| Воспроизведение без моделей |Два byte-identical real rebuilds с0HTTP,input/code/version SHA |
| Ошибки/ограничения |Полный error ledger,10фиксированных tuning examples,development/CI caveats |

Следующий шаг — ревью PR39, затем PR40 и актуальное научное согласование перед
отдельно разрешённым merge. Новые модели/индексация/tracking-export/holdout/signal
и следующие исследовательские задачи в этом блоке не запускались.
