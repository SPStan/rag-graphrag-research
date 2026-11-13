# Один сигнал ошибки Dense — issue21

## Замороженное решение до оценки

Сигнал: **минус cosine similarity первого Dense passage**,
`u = -retrieval.scores[0]`. Чем больше `u`, тем выше предполагаемый риск ошибки.
Цель оценки: `int(EM == 0)` по существующему evaluator. Это ранжирование,
поэтому порог не подбирается и каскад не запускается.

На tuning300 каждого датасета проверена доступность сохранённых top-5 cosine
scores. Все 600 случаев имеют конечные значения в [-1,1] в убывающем порядке.
Выбор основан на доступности признака и предположении о связи сходства с качеством
контекста. Варианты по AUROC не перебирались; направление не выбиралось по check.
Logprobs не предполагаются доступными; self-consistency и verbal confidence
потребовали бы новых вызовов, поэтому не используются.

[Заморозка формулы, split и SHA](../results/summary/dense-error-signal-freeze.json)
создана до текущего доступа к меткам signal-check. Перед оценкой она должна
попасть в Git вместе с кодом. CLI требует полный SHA этого коммита и проверяет
содержимое decision/code blobs, ancestry, текущие source pins и evaluator.
Изменённый код, формула или split останавливают оценку.

## Входы и защита от утечек

Функция `error_signal` принимает только tuple из пяти числовых scores. Она не
получает вопрос, ответ, supporting labels, EM/F1, target или выборку. Проекция
из сохранённого Dense case передаёт только `retrieval.scores`; сигналы не
пересчитываются через embeddings. Эталон применяется отдельным evaluator после
проверки committed freeze. Метки не добавляются ни в сигнал, ни в модельный prompt.

Неподвижное разбиение ADR0015: S500[0:300] — tuning, [300:400] — signal-check,
[400:500] — резерв, seed42, без перемешивания. Проверяются исходные S500/split,
terminal manifests, case hashes, frozen protocol и Dense index/reader contract.
Резервные 100 не оцениваются. Полный labels JSON читается только внутри фазы
оценивания после freeze; scorer получает только выбранные 100 labels.

**Ограничение:** control/reserve EM/F1 уже раскрывались в истории PR40 и
обрабатывались E3/oracle. Это не независимый нетронутый тест. Новый коммит
доказывает порядок именно текущей работы, не отменяет прежнее раскрытие.
Нельзя обещать отсутствие исторического знания или объявлять контроль pristine.

Таблица `dataset, question_id, signal, error, source_run_id` сохраняется только
в новом файле `.cache/` private artifact root. CLI отвергает другой путь и
перезапись. Публичный JSON содержит лишь AUROC, counts, расход, время и hashes;
без ID, индивидуальных scores/targets или членства в группах. Ни вывод в консоль,
ни публичный отчёт не показывают per-case значения. Private CSV в Git не добавлять.

## Команды из корня репозитория

Окружение Python3.12: `UV_PROJECT_ENVIRONMENT=.venv-check`, `uv sync --locked`.
Указать корни сохранённых E2 артефактов и данных; сервисы/API-ключи не нужны.

```powershell
$env:E2_ARTIFACT_ROOT = 'C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG'
$env:E2_DATA_ROOT = 'C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG'
uv run --locked python -m scripts.dense_error_signal freeze --artifact-root "$env:E2_ARTIFACT_ROOT" --decision results/summary/dense-error-signal-freeze.json
# Затем обычный commit с обязательными hooks; не переписывать готовую заморозку
uv run --locked python -m scripts.dense_error_signal evaluate --artifact-root "$env:E2_ARTIFACT_ROOT" --data-root "$env:E2_DATA_ROOT" --decision results/summary/dense-error-signal-freeze.json --freeze-commit 41c2f1c6d44b98609be79f6c4986271f0e54d1e1 --private-output "$env:E2_ARTIFACT_ROOT/.cache/dense-error-signal-check.csv" --output .cache/dense-error-signal-check.json
```

В репозитории решение уже заморожено: повторно вызывать `freeze` поверх него
нельзя. Для воспроизведения оценки нужны новый output/private-output и исходные
private cases/labels. Старые raw/plans не записываются. `socket.connect/connect_ex`
блокируются на обеих стадиях; дополнительные LLM/embedding токены и POST равны 0.

AUROC — доля пар «ошибка/правильный ответ», где сигнал ошибки выше, с весом 0,5
при равенстве. Один класс даёт `null` / `undefined_single_class`, без замены split.
Направление не инвертируется при AUROC<0,5. Повтор проверяет воспроизводимость
фиксированного расчёта, не выбирает новый сигнал. `analytical_digest` и private CSV
SHA воспроизводимы; измеренное wall time может отличаться.

Время измеряется вокруг чистой функции сигнала с валидацией пяти scores,
без чтения файлов, SHA-аудита и оценки меток. Это локальная вычислительная
накладная стоимость, не свежая end-to-end latency Dense или каскада.
Исторический расход E1/E2 и unknown usage не пересчитываются и не обнуляются.

## Проверки и границы

23 целевых синтетических теста: формула/направление, запрет gold на входе,
неверные/NaN scores, AUROC/ties/один класс, gold только после freeze, mismatch
committed decision/code, приватность output, неизменный split и повторяемость CLI
с 0HTTP. Подагентов, новых моделей, индексации, tracking-export и E6 нет.
Активные человеко-часы Елисея не измерялись; время помощника не равно труду студента.
Научная карточка новой задачи требует отдельного согласования.


## Результат фиксированной проверки

[Таблица](../results/summary/dense-error-signal.md) и [JSON](../results/summary/dense-error-signal.json):
MuSiQue AUROC 0,585 (59 ошибок / 41 точный ответ), HotpotQA 0,441 (37 / 63).
Гипотеза точечной AUROC>0,5 на каждом наборе не подтвердилась. Направление
не менялось, новый сигнал не выбирался. Выборка мала; CI и независимое
подтверждение не заявляются. Для универсального E6 этот результат не даёт
достаточного основания: полноценный каскад, порог и экономия не измерялись.
Следующий шаг — ревью фиксированного отрицательного результата и принятие
ограничения загрязнённого контроля; не новый поиск по этим check labels.

Freeze commit: `41c2f1c6d44b98609be79f6c4986271f0e54d1e1`, опубликован до текущей
оценки. Все input/code pins прошли проверку. Точное аналитическое воспроизведение
подтверждено совпадением analytical_digest и private CSV SHA. Wall time измерено
заново и закономерно может различаться; оно исключено из analytical_digest.

Private таблица200строк: artifact-root/.cache/dense-error-signal-v1-private.csv;
повтор: .cache/dense-error-signal-v1-rebuild-private.csv. Доступ только локальный,
в Git не включаются. Содержимое и цели не печатаются. Run ID источников:

- musique: `7936654d-8820-4449-803b-f7ef6074424a`;

- hotpotqa: `91f59cf6-e61c-499d-9d29-d55bff1824c2`;

Исходные составные terminal manifests/plans: Mu e2-musique-s500-unattempted-v1
и Hot e2-hotpotqa-s500-unattempted-v1 в results/raw artifact-root. Их SHA и
reader/index contract hashes находятся в public freeze; frozen IDs и split
остаются в data/ids. Старые raw/планы/usage и E1/E2 unknown cost не изменялись.

| Критерий issue21 | Состояние |
|---|---|
| Формула/направление/split до отложенной оценки | Зафиксированы до текущего пересчёта; историческая нетронутость контроля отсутствует, ограничение требует согласования |
| Нет gold/EM/F1 на входе сигнала | Tuple пяти retrieval scores, gold отдельно в scorer; тесты изоляции |
| AUROC/один класс/расход воспроизводимы | Два набора по100, private CSV + analytical digest, null при одном классе, 0 новых POST/токенов |
| Вывод для E6 без имитации каскада | Общая гипотеза не подтвердилась; каскад/экономия не объявляются полученными |

Refs #21: до закрытия нужны полное ревью, научное согласование и принятие
ограничения ранее раскрытого контроля. Чистый holdout не восстановлен.
