# ADR-0009 — Repair graph gate with pinned HippoRAG

- Date: 2026-09-25
- Status: accepted for offline integration; real rebuild remains unauthorized

## Context

The diagnostic clone contained an old graph and index manifest. The pinned HippoRAG constructor refuses to open persisted vectors when `index_manifest.json` is absent. The manifest records producer/config identity; it does not include an OpenIE state hash. Removing both files prevents the pinned graph path from opening the repaired clone.

## Decision

Keep the hash-verified, unchanged pinned `index_manifest.json` so the constructor can validate the existing vectors and producer. Remove the diagnostic `graph.pickle` from the clone and mark `repair_provenance.json` as `graph_pending`. Treat this repair provenance as the new derived-state manifest: it binds the checkpoint SHA, corrected OpenIE values SHA, vector reconciliation and gate, then records the rebuilt graph SHA and pinned manifest SHA only after the graph exists and exact vector IDs match the corrected state. A graph with the diagnostic SHA is rejected. The pinned rebuild uses `force_index_from_scratch` on the fresh clone; no old graph is loaded.

## Alternatives

- Delete `index_manifest.json`: rejected because the pinned constructor rejects nonempty vector stores without it.
- Rewrite pinned `index_manifest.json` with a repair field: rejected because the pinned schema comparison would reject later reopen.
- Accept the copied graph: rejected because its edges reflect the old OpenIE state.

## Consequences and verification

The repair gate must require `graph_ready` and verify hashes before QA. The pinned manifest SHA may be identical to the diagnostic source because producer/config identity is unchanged; the new repair provenance carries the corrected state and graph identity. The synthetic test rebuilds a graph using the pinned `HippoRAG.index` with ready vectors and fake LLM/embedding objects that raise on unexpected calls. It also verifies the bound `CacheOpenAI.infer` payload with a transport stub. No real index was rebuilt.

Revisit if upstream adds an OpenIE state hash to its index manifest or changes its constructor's vector/manifest rules.
