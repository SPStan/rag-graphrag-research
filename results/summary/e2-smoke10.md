# E2 smoke10: failed

Run `e4bd76e8-e779-48b0-9e02-b7746ed866d2`; plan `8d9ce08b71255ef619a84299da5001096de8da2186de40988e4507da36d7cb97`.

| Датасет | Метод | План | Completed | Failed | Не запускались |
|---|---|---:|---:|---:|---:|
| musique | dense | 10 | 2 | 1 | 7 |
| musique | hipporag2 | 10 | 0 | 0 | 10 |
| musique | raptor | 10 | 0 | 0 | 10 |
| hotpotqa | dense | 10 | 0 | 0 | 10 |
| hotpotqa | hipporag2 | 10 | 0 | 0 | 10 |
| hotpotqa | raptor | 10 | 0 | 0 | 10 |

Модельных POST: 6 (3LLM/3local BGE).
Known LLM input=4516, output=1102, local embedding=69; всего 5687.
Query cost_complete=True; unknown=0; unfinished=0.

Остаток исходных caps: 3271113tokens/134POST. Это не допуск к новому run после остановки.

Первый stop: dense/musique/2hop__126306_396277; reader finish_reason=length. Partial response не принят.

При failed сравнительные F1/EM не публикуются: это техническая остановка, не полный E2. Полная declared-denominator оценка выбранных tuning IDs сохранена только в private evaluation.json.
E1 known32601955/unknown reserve61588 и все6индексов сохранены отдельно. В Git нет gold/сырого ответа/корпуса. Refs #14; без pilot200/QA holdout/merge.

Данные: [e2-smoke10.json](e2-smoke10.json). Private raw: `results\raw\e2-smoke10-8d9ce08b`.
