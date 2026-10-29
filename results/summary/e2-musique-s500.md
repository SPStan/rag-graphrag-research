# MuSiQue S500: 1500 исходов, 1499 ответов и 1 transport failure

На одинаковых500зафиксированных ID каждого метода учтены все1500случаев;
not_attempted=0. Dense/HippoRAG2:500ответов, RAPTOR:499ответов+1сохранённый
инфраструктурный сбой. Unknown reader не повторён, usage=null; pipeline EM/F1=0
для этого случая — не утверждение о неправильном ответе модели.

| Метод | Completed / failed | EM, % | F1, % | Passage recall@5, % | RAPTOR provenance, % | Новые query wall seconds (n) | Reader I/O known¹ | Filter I/O known¹ | BGE input¹ |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| dense | 500 / 0 | 34.80 | 44.93 | 60.33 | — | 2.255 (300) | 748067 / 4189 | — | 12877 |
| hipporag2 | 500 / 0 | 43.40 | 53.55 | 70.72 | — | 4.015 (300) | 785279 / 4097 | 1521944 / 28514 | 12877 |
| raptor | 499 / 1 | 32.40 | 42.47 | — | 62.12 | 4.316 (300) | 1954121 / 4464 | — | 12877 |

¹Логическиеquerytokens для500cases, включая200reuse на метод; это не новая
оплата. Для RAPTOR это known subtotal с1unknown, не полный расход. Physical
новые300cases/method (parent+child), child-only и inherited logical выделены
в JSON отдельно. Hippo fact filter включён. BGE — локальные токены, не расход API.

Query wall измерен только для300новыхcases/method: включает guards/persistence,
исключает загрузку индекса и4сек throttle-pause. Фазы исполнялись последовательно
в разных запусках; source/replay не freshE2E. RAPTOR provenance не passage recall@5.

## Расходы и lineage

- Child ba393849-c977-4c8f-97d7-303fc12955c8:199completed,398POST,802989known
  tokens (LLM796282input/1803output, local BGE4904), newunknown0.
- S500 parent7936654d+child:900новых outcomes=899completed+1failure,2100POST,
  3055781known tokens (LLM3008746input/24436output, BGE22599). Initial600reuse
  не оплачены повторно. Mu unknown reserve15732 — не actual usage.
- E2сsource/development:7092434known/4960POST,2unknown, reserve38277=
  oldHot22545+Mu15732, cost_complete=false. Source91871 — часть development,
  не добавлен повторно. E1known32601955/reserve61588/cost_complete=false отдельно.
- Исходный cap5990220new S500 tokens/2100POST не расширялся; остаток после
  unknown reservation2918707tokens/0POST не разрешает новые эксперименты.

Parent runtime e144ad9, child runtime a0a52cf; failed manifest, claims, journals
и старыеcode/runtime SHA неизменны. Unknown case3hop1__90327_83076_319330:
ConnectionError/RemoteDisconnected, checkpoint started, response отсутствует.
Приращение F1 одного такого pipeline failure ограничено0.2п.п. на500случаев;
это disclosed infrastructure limitation, а не оценка качества неизвестного ответа.

## Проверка и передача

Terminal audit:1500uniqueexpected,1301parents+199child, source/index/data/code
pins, successful response/checkpoint/journal SHA, sealed reader identity и отсутствие
response проверены;0newunknown/unfinished/duplicate attempts. Historical sealed
unknown ожидаем, не объявляется успешным ответом. Private per-case оценки:
`results/raw/e2-musique-s500-unattempted-v1/evaluation.json`; manifest и usage.jsonl
там же, parent artifacts остаются в `results/raw/e2-musique-s500-v1`.

Tracking:3MLflow runs/3Langfuse traces по500cases; в каждом сервисе7500retrieval
и7500generation documents совпали с source поID/title/text/order и answers.
36artifact/linked-JSONL roundtrip SHA подтверждены, reader usage известная часть
совпала, ровно1Mu reader unknown остался null. Derived JSONL связан сtrace IDs.
Это posthoc export, новых modelcalls0. Сырые тексты остаются только локально.

Postprocessor fix после terminal: Langfuse meta.cursor вместо meta.next_cursor
обрезал чтение на1000из2001observations. Reader теперь поддерживает оба поля
и отвергает повтор cursor;3регрессии и реальный native readback прошли. Dense
trace дочитан без reexport. AST guard допускает изменение только этой функции
наблюдений; generator/evaluator не менялись. Execution pins не переписаны.

S500 включает development; mixed Hippo extractor/errors и неполнота E1/source
cost сохранены. Это описательное фиксированное сравнение, не независимое
подтверждение универсального преимущества. Параметры по F1 не подбирались.
Следующий шаг — ревью PR38 и передача per-case артефактов задачам12/14.
Новых моделей/индексов/HotpotQA/signal/holdout/E3 в этом блоке не запускалось.
Draft, Refs #16; без Ready/merge/закрытияissue.


Security:2historicalgeneric-api-key matches independently verified as one case
SHA256, not credentials. Only exact Git061b306/path/rule/line fingerprints are
allowlisted; public field uses case_id_sha256.219commit historyscan found0leaks,
syntheticstdin canary detected. Raw/model outputs and expenses unchanged.
