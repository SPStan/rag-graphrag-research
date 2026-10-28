# E2 pilot200: failed

Run `84454233-8d21-4731-922a-5a31184610e0`; plan `284af290878ef53f9a486d1df956a8e02d72f147d3a6f1e2aa0b072efc5b4f01`.

Сравнение неполное: ниже только техническое покрытие/завершённые группы, не полный comparative result.
Development/tuning pilot; one fixed shared-answer-only-v1, cap512. Not independent quality evidence.

| Dataset | Method | EM % | F1 % | Completed / failed / not attempted | Failure % | Passage recall@5 % | RAPTOR provenance % | Fresh E2E s (n) | Reader call s (n) | New R(in/out); F(in/out); BGE(in) | Reused R(in/out); F(in/out); BGE(in) |
|---|---|---:|---:|---|---:|---:|---:|---|---|---|---|
| musique | dense | 33.000 | 43.598 | 200 / 0 / 0 | 0.000 | 61.042 | — | 0.826 (190) | 0.467 (198) | R 295849/1617; F 0/0; BGE 5103 | R 2902/16; F 0/0; BGE 241 |
| musique | hipporag2 | 42.500 | 52.613 | 200 / 0 / 0 | 0.000 | 72.042 | — | 1.842 (190) | 0.456 (198) | R 312657/1543; F 578783/11243; BGE 5103 | R 2933/16; F 30436/647; BGE 241 |
| musique | raptor | — | — | 12 / 1 / 187 | 7.692 | — | — | 2.765 (3) | 0.688 (10) | R 32065/74; F 0/0; BGE 111 | R 5867/14; F 0/0; BGE 241 |
| hotpotqa | dense | 59.000 | 70.814 | 200 / 0 / 0 | 0.000 | 87.500 | — | 0.844 (190) | 0.434 (198) | R 276044/1399; F 0/0; BGE 4711 | R 2529/18; F 0/0; BGE 244 |
| hotpotqa | hipporag2 | 69.000 | 79.290 | 200 / 0 / 0 | 0.000 | 94.500 | — | 2.063 (190) | 0.501 (198) | R 282821/1381; F 578474/11809; BGE 4711 | R 2796/18; F 30417/684; BGE 244 |
| hotpotqa | raptor | — | — | 0 / 0 / 200 | — | — | — | — (0) | — (0) | R 0/0; F 0/0; BGE 0 | R 0/0; F 0/0; BGE 0 |

Reader/filter LLM input/output and embedding tokens are separated in JSON; each cell separates reader(R) input/output, filter(F) input/output and BGE input. Not-attempted is not a wrong answer; incomplete groups have null EM/F1. Known reader failures count as0 only in completed groups.
Cached context/reader results are not fresh latency; source timing provenance stays in private per-case data and is never added across runs. RAPTOR provenance coverage is not passage recall@5.

New physical known: {'llm_input_tokens': 2356693, 'llm_output_tokens': 29066, 'embedding_input_tokens': 19739}; new POST=1945; unknown=0. Reused source costs are a subset of the separately reported development expense, not additional physical cost. E1known32601955/unknown reserve61588/cost_complete=false separate.

Comparison incomplete; no paired inference reported.

Includes mixed Hippo extraction configuration and disclosed source errors; no architecture-only causality. Refs #14; Draft, no merge/holdout/S500.

Причина остановки: actual answer-only messages37608UTF-8bytes >32000 на13-м
RAPTOR/MuSiQue случае. Reader не вызывался; на этом случае только33BGE tokens.
Итого812completed/1attempted_failed/387not_attempted; не все planned cases имеют ответы.
Все813saved cases и pins проверены offline;1945started=1945finished, unknown0.

Фактически использованный source80504tokens/80operations входит в development237340,
повторно не прибавляется. E2physical cumulative2642838tokens/2097POST; E1 отдельно.
Partial pilot не экспортирован в MLflow/Langfuse. Остаток бюджета не разрешает
перезапуск. Следующий шаг — согласовать общую политику входного контекста до continuation.
