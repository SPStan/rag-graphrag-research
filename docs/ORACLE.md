# Oracle и дополняемость Dense / HippoRAG2 — issue20

## Что выяснили

HippoRAG2 в среднем лучше Dense, но не заменяет его ответы полностью.
На MuSiQue только Dense даёт точный ответ на 19 из 500 вопросов, на HotpotQA —
на 12 из 500. При идеальном выборе между уже сохранёнными ответами F1 достигает
58,16% и 79,76% соответственно. Это на **4,61 и 2,06 п.п. выше HippoRAG2**.
Резерв есть; способность маршрутизатора найти эти случаи ещё не проверялась.

[Полные таблицы](../results/summary/oracle.md) ·
[Агрегаты, версии и SHA](../results/summary/oracle.json)

| Датасет | Dense F1, % | HippoRAG2 F1, % | Oracle F1, % | Резерв к Hippo, п.п. |
|---|---:|---:|---:|---:|
| MuSiQue | 44,93 | 53,55 | 58,16 | 4,61 |
| HotpotQA | 72,03 | 77,70 | 79,76 | 2,06 |

Это ответный token F1 по единственному сохранённому ответу reader после retrieval
top-5. Он не является retrieval F1@5. Oracle выбирает один из двух ответов,
используя эталонные оценки только после генерации.

## Входы и проверка

Графовый метод — HippoRAG2, выбранный в pilot200 issue14, до этого анализа;
решение сохранено в [E2](E2_EVALUATION.md). RAPTOR не добавляется в oracle ради
увеличения результата. Для обоих датасетов берутся все 500 frozen S500 ID.

`scripts/analyze_oracle.py` использует существующий `e3_evaluation.load_dataset`:
проверяет terminal manifests, source/plan SHA, frozen protocol, reader/index/data
pins, journal и соответствие публичных E2 агрегатов пересчёту. Оценки снова
вычисляются из сохранённых ответов общим `e2.score_result`, с нормализацией
`scripts/evaluate_dense.py`. Затем они сверяются с private ledger, переданным E3:
его digest, входные SHA, версия evaluator, статусы и все оценки должны совпасть.
Изменённая оценка с пересчитанным digest тоже отклоняется при расхождении с raw.

Строки соединяются по question_id, порядок не важен. Пропуски, дубликаты,
посторонние ID, EM вне {0,1}, нечисловой/бесконечный F1 или F1 вне [0,1]
останавливают расчёт. Набор не сокращается до пересечения.

Входные private-файлы находятся в artifact root:

- `.cache/e3-oracle-inputs-private.json` — переданные полные оценки и SHA;
- `.cache/e2-musique-s500-unattempted-plan.json`,
  `results/raw/e2-musique-s500-unattempted-v1/{manifest,evaluation}.json`;
- Hot plan/output берутся из `.cache/e2-hotpotqa-s500-active.json`, сейчас это
  `.cache/e2-hotpotqa-s500-unattempted-plan.json` и
  `results/raw/e2-hotpotqa-s500-unattempted-v1/{manifest,evaluation}.json`;
- `usage.jsonl` находится рядом с каждым terminal manifest;
  parent/source lineage проверяется существующим E3 loader.

Run ID: MuSiQue `ba393849-c977-4c8f-97d7-303fc12955c8`,
HotpotQA `9e7efc49-895c-42d6-a2d3-5676e2071b6b`. Это идентификаторы исходных
прогонов, новый inference run не создаётся. Labels и списки ID находятся в
data root: `data/processed/<dataset>/labels.json` и `data/ids/<dataset>_s500.json`.
Точные относительные пути, SHA и reader config записаны в публичном oracle JSON.

## Формулы и ошибки

Для каждой метрики отдельно:
`oracle = mean(max(score_dense[q], score_hippo[q]))`.
Знаменатель — 500, включая failed pipeline outcomes. Разности приводятся в п.п.
EM-oracle и F1-oracle могут выбирать разные ответы; это две отдельные верхние границы.
Четыре EM-группы покрывают весь набор: обе верны, только Dense, только Hippo,
обе неверны. EM-oracle равен сумме первых трёх групп, делённой на 500.

Mu: 1 000 ответов этих двух методов. Hot: 998 ответов и 2 сохранённые ошибки
Hippo (reader failure и fatal fact-filter failure). Они остаются attempted_failed
с нулевой pipeline-оценкой, а не пропусками и не неверными ответами reader.
Их markers в исходных cases не меняются. Sealed transport failures RAPTOR
остаются в общей E3 истории и расходах; в эту пару RAPTOR не входит.
Новые токены/POST — 0; прежний unknown usage не превращается в ноль.

## Воспроизведение без API

Из корня репозитория, Python 3.12 и окружение `uv.lock`:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-check'
uv sync --locked
$env:E3_ARTIFACT_ROOT = 'C:/path/to/private-e2-artifacts'
$env:E3_DATA_ROOT = 'C:/path/to/data-checkout'
uv run --locked python -m scripts.analyze_oracle --artifact-root "$env:E3_ARTIFACT_ROOT" --data-root "$env:E3_DATA_ROOT" --ledger "$env:E3_ARTIFACT_ROOT/.cache/e3-oracle-inputs-private.json" --output .cache/oracle-check.json
```

На машине Елисея artifact root:
`C:/Users/Elisei/.codex/worktrees/e2-shared-evaluation/Rag, GraphRAG`, data root:
`C:/Users/Elisei/Documents/ChatGPT/Rag, GraphRAG`. JSON и Markdown генерируются
одной командой; повторять проверку следует в новом output. Сетевые соединения
`connect/connect_ex` запрещены внутри CLI. Сервисы, API-ключи, модели и индексы
для генерации новых ответов не запускаются. Без private-артефактов доступны
синтетические тесты и агрегаты; полного независимого пересчёта из GitHub нет.

## Ограничения и приёмка

S500 включает development/pilot и не является независимым тестом. Историческое
раскрытие control/reserve scores в PR40 остаётся ограничением; здесь нет новых
per-case публикаций, анализа signal-check, выбора признака или порога issue21.
Публичны только общие метрики и четыре группы, без membership списков.
Oracle использует gold для выбора и поэтому не достижим автоматически.
Экономическая выгода и полезность конкретного сигнала из него не следуют.
Mixed Hippo extraction/errors и неполнота исторического E1/E2 учёта сохраняются.

| Критерий issue20 | Проверка |
|---|---|
| ID/score gate, порядок строк | Негативные тесты и join по frozen ID |
| Пример 0,375 / 0,375 / 0,625, EM и группы | Отдельные синтетические регрессии |
| Два датасета по 500 пар | JSON/таблица, без отбрасывания ошибок |
| Одна offline-команда и честный предел | CLI с запретом сети, повторная генерация |

Проверено: 52 целевых теста oracle/E3; две реальные пересборки JSON/Markdown
совпали побайтно при запрещённой сети. Первый тестовый запуск имел setup error
Windows TEMP (20 passed / 1 error); повтор с проверенным TEMP прошёл.
Логика эксперимента ради ошибки окружения не менялась.

Активные человеко-часы Елисея в этой задаче не измерялись; время работы помощника
не выдаётся за труд студента. Научная карточка этого анализа требует отдельного
согласования, не наследует approval E3/E4. Следующий этап issue21 не запускается.
