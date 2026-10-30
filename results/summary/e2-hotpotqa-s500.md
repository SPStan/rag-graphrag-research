# hotpotqa S500: completed

Descriptive S500 includes development. Source latency is not fresh E2E. RAPTOR provenance is not passage recall@5. Mixed Hippo errors and incomplete E1/source cost retained.

| Method | Completed / failed / not attempted | EM | F1 | Passage recall@5 | RAPTOR provenance | Fresh E2E seconds (n) | S500 reader/filter/BGE known tokens |
|---|---|---:|---:|---:|---:|---|---|
| dense | 500 / 0 / 0 | 0.596 | 0.7202900463521152 | 0.878 | None | 2.546623831666584 (300) | 419200/0/7212 |
| hipporag2 | 498 / 2 / 0 | 0.666 | 0.7769847374847375 | 0.935 | None | 4.4840140603332115 (300) | 425861/932174/7212 |
| raptor | 499 / 1 / 0 | 0.606 | 0.7293154179154179 | None | 0.886 | 4.060463957333268 (300) | 964968/0/7212 |

New physical known tokens {'llm_input_tokens': 1538809, 'llm_output_tokens': 10764, 'embedding_input_tokens': 10355}; POST 987; usage complete=True. Historical global expense remains separate; never add logical reuse twice. Refs #17.

Historical failures remain immutable: pipeline EM/F1=0 with their original error markers. Unknown usage stays null; reservation is not actual usage. No paid or unknown failure was retried.

S500 cumulative physical: {'known_subtotal': {'llm_input_tokens': 2716828, 'llm_output_tokens': 25375, 'embedding_input_tokens': 21636}, 'POST': 2099, 'unknown_reservation_not_actual': 0, 'cost_complete': True}; source/development and E1 remain separate. Fresh latency includes original S500 parent plus child, excludes initial pilot600. Child runtime/code pins are separate from immutable parent runtime.
