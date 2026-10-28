# E2 smoke10: completed

Run `3bee5af5-13f9-43ad-b9d9-dee3dfd11171`; plan `723a9993cfd710c8e958cc5ae422ca26dfce27b448acb6538b89f28b3990ffe6`.

Учтены60cases: 43 completed, 17 attempted_failed, 0 not_attempted. Reader/model/prompt/cap512 неизменны; retries0.

| Dataset | Method | EM % | F1 % | Completed / failed | Failure % | Mean query s | LLM in / out | BGE tokens | Passage recall@5 % | RAPTOR provenance % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| musique | dense | 30.00 | 32.86 | 5 / 5 | 50.0 | 9.361 | 15667 / 3816 | 241 | 63.33 | — |
| musique | hipporag2 | 30.00 | 42.62 | 6 / 4 | 40.0 | 4.214 | 46525 / 3946 | 241 | 78.33 | — |
| musique | raptor | 20.00 | 33.33 | 5 / 5 | 50.0 | 5.479 | 30974 / 3856 | 241 | — | 68.33 |
| hotpotqa | dense | 30.00 | 37.33 | 8 / 2 | 20.0 | 2.475 | 14414 / 2586 | 244 | 85.00 | — |
| hotpotqa | hipporag2 | 50.00 | 57.33 | 10 / 0 | 0.0 | 3.105 | 45564 / 2548 | 244 | 95.00 | — |
| hotpotqa | raptor | 40.00 | 47.33 | 9 / 1 | 10.0 | 4.198 | 34974 / 2783 | 244 | — | 90.00 |

Query LLM input=188118, output=19535; local BGE input=1455. Query cost_complete=True; unknown=0; unfinished=0.
Модельных POST=140 (80LLM/60localBGE), новых child POST=134. Parent/child учтены один раз.
Hippo fact filter включён в LLM totals: input=60853, output=1331. Reader/filter отдельно — usage_by_operation в JSON.

На законченном smoke denominator=10/cfg; attempted_failed даёт EM/F1=0. Mean query time включает failed cases, query embedding/retrieval/filter/reader; исключает preflight/index loading/паузы между cases. Source parent timing сохранён, это не cold-run benchmark.
RAPTOR top5 — nodes. Passage recall@5 не сопоставим; provenance — покрытие union descendant source IDs, не доказательство сохранения нужного факта в summary.
E1 отдельно: physical known=32601955; unknown reserve=61588; cost_complete=False. Reserve не actual usage; деньги не оценивались. E1 индексы не перестраивались.

Ошибки и точные source/request/response SHA: [e2-smoke10-continuation.json](e2-smoke10-continuation.json). Private raw: `results\raw\e2-smoke10-continuation-v2`. Полные тексты/gold в Git не публикуются.
Development tuning smoke n=10/dataset, не pilot200 и не выбор победителя. Hippo Qwen/GPT extraction policy/observed errors раскрыты в ADR0023; это сравнение конкретных конфигураций, не чистого эффекта архитектуры.

**Один следующий шаг:** общий пересмотр reader для всех методов перед pilot200 из-за наблюдаемых reader length failures. Решение основано на завершённости ответа, не на лучшем F1; новая reader version не смешивается с v2. Новых model calls этот отчёт не разрешает.
Refs #14; Draft, без pilot200/S500/check/holdout/новых моделей/rebuild/merge.
