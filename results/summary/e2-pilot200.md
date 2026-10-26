# E2 pilot200: failed

Run `fadc0797-34e3-4468-8f0d-bc9ef1289f3a`; plan `cbdc1a8c063d74d4848793338c78c7b915c9e9a98b6815943741b4e644ddf400`.

Сравнение неполное: ниже только техническое покрытие/завершённые группы, не полный comparative result.
Development/tuning pilot; one fixed shared-answer-only-v1, cap512. Not independent quality evidence.

| Dataset | Method | EM % | F1 % | Completed / failed / not attempted | Failure % | Passage recall@5 % | RAPTOR provenance % | Fresh E2E s (n) | Reader call s (n) | New R(in/out); F(in/out); BGE(in) | Reused R(in/out); F(in/out); BGE(in) |
|---|---|---:|---:|---|---:|---:|---:|---|---|---|---|
| musique | dense | 33.000 | 43.598 | 200 / 0 / 0 | 0.000 | 61.042 | — | 0.826 (190) | 0.467 (198) | R 295849/1617; F 0/0; BGE 5103 | R 2902/16; F 0/0; BGE 241 |
| musique | hipporag2 | 42.500 | 52.613 | 200 / 0 / 0 | 0.000 | 72.042 | — | 1.842 (190) | 0.456 (198) | R 312657/1543; F 578783/11243; BGE 5103 | R 2933/16; F 30436/647; BGE 241 |
| musique | raptor | 32.500 | 43.491 | 200 / 0 / 0 | 0.000 | — | 62.167 | 3.007 (189) | 0.777 (198) | R 771238/1732; F 0/0; BGE 5070 | R 5867/14; F 0/0; BGE 274 |
| hotpotqa | dense | 59.000 | 70.814 | 200 / 0 / 0 | 0.000 | 87.500 | — | 0.844 (190) | 0.434 (198) | R 276044/1399; F 0/0; BGE 4711 | R 2529/18; F 0/0; BGE 244 |
| hotpotqa | hipporag2 | 69.000 | 79.290 | 200 / 0 / 0 | 0.000 | 94.500 | — | 2.063 (190) | 0.501 (198) | R 282821/1381; F 578474/11809; BGE 4711 | R 2796/18; F 30417/684; BGE 244 |
| hotpotqa | raptor | — | — | 61 / 1 / 138 | 1.613 | — | — | 3.305 (52) | 0.991 (60) | R 189812/428; F 0/0; BGE 1283 | R 11105/18; F 0/0; BGE 244 |

Reader/filter LLM input/output and embedding tokens are separated in JSON; each cell separates reader(R) input/output, filter(F) input/output and BGE input. Not-attempted is not a wrong answer; incomplete groups have null EM/F1. Known reader failures count as0 only in completed groups.
Cached context/reader results are not fresh latency; source timing provenance stays in private per-case data and is never added across runs. RAPTOR provenance coverage is not passage recall@5.

Pilot physical lineage known: {'llm_input_tokens': 3285678, 'llm_output_tokens': 31152, 'embedding_input_tokens': 26014}; total POST=2432; current run POST=487; unknown=1. Reused source costs are a subset of the separately reported development expense, not additional physical cost. E1known32601955/unknown reserve61588/cost_complete=false separate.

Comparison incomplete; no paired inference reported.

Includes mixed Hippo extraction configuration and disclosed source errors; no architecture-only causality. Refs #14; Draft, no merge/holdout/S500.

Остановка: reader transport RemoteDisconnected на HotpotQA; результат POST неизвестен,
не повторён. Child:487POST,937346known tokens,1unknown reader request.
Консервативный резерв этого неизвестного запроса:22545tokens, не actual usage.
Суммарно pilot:3342844known tokens/2432POST; development237340 включён отдельно,
cumulative E2 known3580184/2584POST, cost_complete=false. E1unknown отдельно.
Итого1061completed/1attempted_failed/138not_attempted; RAPTOR Mu200completed,
Hotpot61completed/1failed/138not_attempted. Полное сравнение не завершено, paired
inference не публикуется. Tracking partial run не экспортирован. Повтор POST запрещён.
