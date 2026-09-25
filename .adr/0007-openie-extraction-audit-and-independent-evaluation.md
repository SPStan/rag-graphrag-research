# 0007 — OpenIE extraction statuses and independent evaluation plan

- Date: 2026-09-25
- Status: accepted protocol; implementation and independent evaluation are pending
- Related: [ADR-0002](0002-pinned-data-and-passage-identity.md), [ADR-0006](0006-hipporag-common-reader-debug10.md)

## Context

The rebuilt MuSiQue OpenIE state contains 5,500 documents: 446 have no entities but have triples, 27 have entities but no triples, 8 have neither, and 5,019 have both. These are coverage categories, not proven extraction errors. The SQLite LLM cache contains 11,048 rows, including 180 responses with `finish_reason=length` and 200 non-JSON responses, but stores request hashes, response text and metadata without prompts or passage IDs. Its aggregates cannot be linked to individual passages. The final cache-replay run's `openie_extraction_failures=[]` records only that replay and says nothing about earlier index-build attempts.

The 10-question debug view was used during development and is included in `baseline100`. The first 200 IDs (`pilot200`) have not been run; the final 100 IDs (`holdout100`) remain reserved and must not be used in this stage.

## Decision: classify each extraction stage and attempt

NER/entity extraction and triple extraction are separate stages, each recorded per passage and attempt. An empty list is a valid empty extraction only when a response exists, generation ended with `stop`, parsing and schema validation succeeded, and the expected list field is present with value `[]`. Empty entities do not imply empty triples, or vice versa.

Use distinct attempt statuses:

- `valid_empty`: complete response, valid expected schema, empty list;
- `valid_nonempty`: complete response, valid expected schema, non-empty list;
- `parse_error`: a response exists but is invalid JSON or fails expected object/field/type validation; an empty body is recorded as a parse error with a specific reason;
- `truncated`: `finish_reason=length`, whether or not a repair parser can recover partial structured content; preserve whether recovery succeeded, but do not relabel the original attempt as complete;
- `raw_response_missing`: the request layer returned without a response body; record transport/API exception separately as `request_error` when available.

Retries are bounded and explicit. Do not retry a valid empty extraction just because it is empty. Retrying parse errors or truncated responses must bypass the response cache, create a linked attempt record, and account for the additional usage. Keep the first and retry outcomes; never silently replace the failure with the retry result. A successful retry resolves the passage for graph construction while preserving the failed attempt and its cost. An unresolved attempt remains a failure.

Every attempt must be attributable to `index_run_id`, stable `passage_id` and passage fingerprint, stage, attempt number, model digest, prompt/schema version, response-format setting, cache-hit flag, finish reason, status/reason, response hash and byte length, retry linkage, usage and measured timings when available. Preserve raw response text only in ignored local cache/run storage under existing data-handling rules. Public summaries contain aggregates and hashes only, with no passage text, prompts, raw responses, local paths or secrets.

## Decision: index acceptance and rebuilds

Do not infer failure from empty lists and do not rebuild an existing index automatically. A future index intended for independent evaluation is eligible only when every expected passage has a terminal status for both extraction stages, every attempt and retry is accounted for, and unresolved request/parse/truncation/missing-response failures are zero. Valid empty outputs are allowed and counted. If this gate is not met, preserve the produced index as diagnostic, report its unresolved count, and do not present it as the primary independent HippoRAG result until the failure policy is explicitly revisited.

After status instrumentation and synthetic tests are implemented, any rebuild requires an explicit run command and a new fingerprinted storage namespace. Never overwrite or delete the current index, cache, or historical results. Record usage for every attempt; if usage is absent, record unknown rather than zero. This ADR authorizes documentation and implementation of the recording/gating policy, not an LLM call, rebuild, or benchmark run.

## Independent evaluation plan (planned, not run)

Candidate evaluation IDs are positions 200–299 of the pinned `data/ids/musique_s500.json` list (`S500[200:300]`, 100 questions). This range lies outside the already-used first 100 IDs and the unrun `pilot200` prefix, and does not use or alter the separately reserved `holdout100` at positions 400–499. Freeze these ordered IDs and their SHA-256 in a new view before any evaluation. Verify disjointness against every development/debug/replay run manifest and confirm the source revision and labels hash.

Before generation, freeze the reader template, model digests, generation options, top-k, corpus, retriever/index policy, evaluation formulas, extraction acceptance gate and tracking schema. All systems must use the same 100 question IDs and the pinned shared corpus; labels remain evaluator-only. Run each required system once on this view after a readiness report and separate authorization. Save complete ordered IDs, configuration, code/data hashes, raw results, failure statuses and phase usage. Compare systems by question ID using paired bootstrap with 10,000 resamples, seed 42, and 95% intervals; no prompt or parameter selection may use these evaluation answers. This is a candidate local evaluation view within the pinned S500 sample, not evidence of representativeness for the full source datasets or target API/T4 setup.

## Consequences and review conditions

- OpenIE coverage is not an extraction-quality score; semantic quality needs a separate labeled audit.
- Historical cache rows remain unattributed. Do not fabricate per-passage statuses for them.
- The complete original graph-build usage remains unknown because prior attempts and one request have incomplete usage.
- One answer in the rebuilt debug10 run ended with `length` without `Answer:`; it remains an empty evaluated answer.
- Revisit the acceptance gate if the package cannot expose a stage outcome per passage or if failures cannot be zeroed without changing the scientific protocol. Any such change needs a new ADR before an independent run.
