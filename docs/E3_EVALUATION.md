# E3 — метрики и парные интервалы, issue18 на согласование

Статус: подготовительный Draft PR, Refs #18. Итоговая E3 не рассчитана.
Полный HotpotQA S500 отсутствует; issue17 остаётся входным блокером. Этот PR
фиксирует предлагаемый статистический протокол для куратора, а не результаты.
Новых model/API/embedding/indexing/tracking вызовов и анализа signal-check нет.

## Вход и границы

[Issue18](https://github.com/SPStan/rag-graphrag-research/issues/18) зависит от
issues16/17. [SPEC](SPEC.md), [протокол E2](E2_EVALUATION.md) и раздел статистики
[трека](../3_1_student_track_v1.md) остаются источниками условий.

- MuSiQue: готовые1500учтённых случаев (1499ответов+1sealed transport failure),
  private `results/raw/e2-musique-s500-unattempted-v1/evaluation.json`, соседние
  manifest/usage и source refs; [safe report](../results/summary/e2-musique-s500.json)
  и [hash-bound evidence](../results/summary/e2-musique-s500-evidence.json).
- HotpotQA: сейчас доступны только600pilot outcomes, включая1sealed failure.
  Полный1500-case набор, final audit и summary должны прийти из issue17.
  Путь `results/raw/e2-hotpotqa-s500-v1/` — предложение для будущего результата,
  не существующий вход. Не заменять его200pilot IDs и не дублировать Mu данными.
- Обоим датасетам нужны по500ожидаемых ID на каждый из3методов, единые условия,
  per-case scores/status/error, metric version и manifest/source hashes.
  Первичный private artifact-root задаётся явно; raw между ветками не копировать.

Gate до анализа проверяет ID completeness/uniqueness, dataset/method/config/metric
pins и immutable lineage. Дубликаты, drift, недостающие или not_attempted cases
блокируют полную E3. Не удалять трудные вопросы и не считать не запущенные нулём.
Входные sealed failures сохраняются как pipeline EM/F1=0 с infrastructure marker,
а не как неправильные reader answers; их usage остаётся null и cost_complete=false.
Любые новые необъяснённые незавершённые outcomes требуют разбора до final report.

## Статистический протокол до просмотра итоговых результатов

1. Для каждого датасета отдельно сопоставить строки всех методов по frozen
   ordered IDs. Перестановка входных строк допустима только через явный join;
   repeated/missing/unexpected ID — ошибка. Между датасетами вопросы не спаривать.
2. Переиспользовать общий оценщик проекта для per-question EM/token-F1 и
   passage recall@5 Dense/Hippo. Средние — по500pipeline outcomes, не только
   по успешным ответам; отдельно показывать completed/failed/not_attempted.
   Retrieval errors/coverage и пригодность исходных per-case scores проверять
   явно, не придумывать пропущенный recall=0 и не менять прежнюю metric policy.
3. Предлагаются **1000ресэмплов, seed42, percentile95% [2.5%,97.5%]** по issue18
   и треку. Один ресэмпл —500индексов с возвращением; одна матрица индексов
   используется всеми3методами и метриками внутри датасета. Seed/RNG/library
   version/count/index digest сохранять. Выбор числа повторов не зависит от F1/CI.
4. Рассчитать mean EM/F1 и их CI; paired Δ(Hippo−Dense), Δ(RAPTOR−Dense) EM/F1
   и CI из разностей на одинаковых ID каждого ресэмпла. Единицы0..1 в JSON,
   проценты/п.п. явно в таблице. Для Dense/Hippo retrieval допустима парная
   разность только одной и той же passage metric с проверенными per-case inputs.
5. RAPTOR summary-node provenance показывать отдельной метрикой с coverage и CI;
   это **не passage recall@5**, парную разность provenance−Dense recall не считать.
6. CI pointwise95%, не simultaneous; не выдавать несколько сравнений за один
   подтверждающий тест. Доверительный интервал, содержащий0, не доказывает равенство
   методов или разность<2п.п. Не вводить постфактум equivalence test/новый margin.
   S500 включает development/pilot; интервалы описательные, не независимая проверка
   архитектуры, mixed Hippo/errors/E1cost incompleteness сохраняются.

## Переиспользование существующего кода

`scripts/evaluate_dense.py` и общий E2 evaluator сохраняют metric formulas.
`scripts/compare_asbuilt.py::paired_summary` — legacy pure helper: сейчас он
требует одинаковый порядок строк, считает10000повторов и содержит две системы/
поле recall_at_k. Это не готовая команда полной E3. Не вызывать его `run(execute=True)`.

В этом же PR потребуется минимально вынести/параметризовать existing bootstrap
kernel, добавить явный ID join и общий resample input, сохранив legacy default/
исторические отчёты. `scripts/e2_pilot.py` уже использует shared resamples,
но pilot2000seed42 — другая версия; его результаты/default не переписывать и
не смешивать с S5001000. Новый CLI и точная команда пересчёта появятся после
реализации/test и freeze анализа; в этом подготовительном PR команды ещё нет.
Модельный transport в пути E3 должен быть недоступен, проверка обязана дать0HTTP.

## Проверки и выходы

План целевых offline tests:

- одинаковые scores дают Δ0 и CI[0,0], постоянная разность воспроизводится;
- перестановка строк не меняет результат после ID join, дубликаты/пропуски/drift
  отвергаются; все системы используют одинаковые resample IDs;
- fixed seed/count даёт тот же output; failed markers не исчезают, not_attempted
  блокирует final E3, null usage не становится0;
- RAPTOR provenance не попадает в passage recall column; no model/HTTP calls;
- источники/manifests/checksums и старые per-case artifacts не меняются.

Планируемые safe outputs `results/summary/e3.json/.md` и воспроизводимый private
per-case artifact с source references для задачи14. Это имена будущих файлов,
а не уже созданные результаты. Хранить sample counts, версии, seed/n_resamples,
mean/CI/delta, coverage/errors и lineage hashes; тексты ответов/корпуса не публиковать.
Расход брать из неизменных accounting, logical и physical отдельно, historical
unknown/reserves не оценивать нулём. Денежных тарифов нет — денежную цену не выводить.

После метрик разобрать до5иллюстративных расхождений на датасет из tuning300:
фиксированные outcome strata, seed42 и явный список ID/причин выбора. Все failures
сохранить в ledger независимо от отбора примеров. Это иллюстрации, не частоты причин;
не менять ответы/labels и не использовать check/reserve для выбора сигнала issue21.
В этом подготовительном PR ни примеры, ни реальные intervals не рассчитываются.

| Критерий issue18 | Необходимое свидетельство | Сейчас |
|---|---|---|
| E3:3метода×2датасета, approved IDs | Full input audit/mean metrics | Не выполнен: полный Hot вход отсутствует |
| Парные CI, seed/count, tests | Shared resamples и целевые regressions | Протокол предложен, код не реализован |
| Воспроизводимость без моделей | Offline CLI, hashes, deterministic rebuild0HTTP | Команда/итог ещё отсутствуют |
| Ошибки/ограничения, верная интерпретация | Ledger, до5примеров/датасет, CI caveats | Правила записаны; анализа ещё нет |

Научные O/N/R/H нового этапа ожидают согласования. Все дальнейшие реализация,
проверки и результаты issue18 останутся в этом PR. До приёмки — Draft/Refs #18,
без Closes/Ready/merge. Активные часы студента не измерялись.
