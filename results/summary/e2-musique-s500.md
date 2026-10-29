# MuSiQue S500: неполный прогон (failed)

Descriptive S500 includes development. Source latency is not fresh E2E. RAPTOR provenance is not passage recall@5. Mixed Hippo errors and incomplete E1/source cost retained.

| Method | Completed / failed / not attempted | EM | F1 | Passage recall@5 | RAPTOR provenance | Fresh E2E seconds (n) | New reader/filter/BGE known tokens |
|---|---|---:|---:|---:|---:|---|---|
| dense | 500 / 0 / 0 | 0.348 | 0.4493305006105006 | 0.6033333333333334 | None | 2.2546996593324002 (300) | 451872/0/7533 |
| hipporag2 | 500 / 0 / 0 | 0.434 | 0.5354763572092285 | 0.7071666666666666 | None | 4.015264944000325 (300) | 472227/929349/7533 |
| raptor | 300 / 1 / 199 | None | None | None | None | 3.739350829701087 (101) | 381649/0/2629 |

New physical known tokens {'llm_input_tokens': 2212464, 'llm_output_tokens': 22633, 'embedding_input_tokens': 17695}; POST 1702; usage complete=False. Historical global expense remains separate; never add logical reuse twice. Refs #16.

## Остановка и полнота

Всего1500ожидаемых случаев:1300completed (600reuse+700new),1transport
attempted_failed,199not_attempted. Dense и HippoRAG2 имеют по500ответов;
RAPTOR300ответов+1transport failure+199незапущенных. Полного сравнения трёх
методов нет; RAPTOR EM/F1 остаются null, незапущенные вопросы не неверные ответы.

Сервер закрыл reader-соединение без HTTP-ответа: ConnectionError /
RemoteDisconnected. Case3hop1__90327_83076_319330, ответ отсутствует,
checkpoint status=started. Обе величины usage этого запроса null;15732tokens —
консервативный reserve, не фактический расход. Запрос не повторён, recovery0.
Кодовая причина не установлена; внешнюю транспортную ошибку нельзя исправить
подменой результата или снятием guard. Автоматическое продолжение остановлено.

Новые расходы2252792known tokens/1702POST,1unknown; остаток исходного cap
после reserve3721696tokens/398POST. Остаток сам по себе не разрешение на запуск.
E2включая source/development6289445known/4562POST,2unknown с суммарным
reserve38277 (oldHot22545+newMu15732); cost_complete=false. Source/development
учтены один раз. E1known32601955/reserve61588/cost_complete=false отдельно.

Offline report проверил существующие source pins, SHA новых700успешных cases,
responses/checkpoints/journal и расход; для fatal case сохранены исходная причина,
known/unknown и artifact SHA, strict_success_audit_complete=false. Это не полный
финальный audit1500cases. Runtime e144ad9 и все failed/raw/claims неизменны.
Private per-case:results/raw/e2-musique-s500-v1/evaluation.json; manifest и
usage.jsonl в той же папке. Следующий шаг требует отдельного решения о199ранее
не запущенных случаях с immutable continuation; неизвестный запрос не повторять.
Draft PR38, Refs #16; issue16 ещё не завершена.
