# 0007 — OpenIE extraction statuses and independent evaluation plan

- Date: 2026-09-25
- Status: accepted; instrumentation and candidate ID view implemented; Dense candidate run completed; HippoRAG candidate index build failed acceptance gate before QA
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
- `completion_unknown`: response exists, but finish reason is missing or is not a known complete (`stop`) or truncated (`length`) outcome. Treat it as unresolved.

Retries are bounded and explicit. Do not retry a valid empty extraction just because it is empty. Retrying parse errors or truncated responses must bypass the response cache, create a linked attempt record, and account for the additional usage. Keep the first and retry outcomes; never silently replace the failure with the retry result. A successful retry resolves the passage for graph construction while preserving the failed attempt and its cost. An unresolved attempt remains a failure.

Every attempt must be attributable to `index_run_id`, stable `passage_id` and passage fingerprint, stage, attempt number, model digest, prompt/schema version, response-format setting, cache status (including explicitly unobserved at the LLM layer), finish reason, status/reason, response hash and byte length, retry linkage, usage and measured timings when available. Missing usage is recorded as unknown, not zero. Preserve raw response text only in ignored local cache/run storage under existing data-handling rules. Public summaries contain aggregates and hashes only, with no passage text, prompts, raw responses, local paths or secrets.

## Decision: index acceptance and rebuilds

Do not infer failure from empty lists and do not rebuild an existing index automatically. A future index intended for independent evaluation is eligible only when every expected passage has a terminal status for both extraction stages, every attempt and retry is accounted for, each outcome is attributable to an observed LLM-layer call or cache hit, and unresolved request/parse/truncation/missing-response failures are zero. Retries after already valid outputs are rejected by the gate. Valid empty outputs are allowed and counted. If this gate is not met, preserve the produced index as diagnostic, report its unresolved count, and do not present it as the primary independent HippoRAG result until the failure policy is explicitly revisited.

The runner writes an attempt ledger and acceptance-gate report to each new run manifest; synthetic tests cover status classification, retries and missing stage outcomes. A result returned only by HippoRAG's higher-level OpenIE result cache has no observed LLM-layer attempt and cannot pass the independent-index gate, even if the cached parsed value is non-empty or empty. A captured LLM-cache hit is attributable and records `cache_hit=true`. Historical runs are unchanged and have no reconstructed attempt ledger. Any rebuild requires an explicit run command and a new fingerprinted storage namespace. Never overwrite or delete an existing index, cache, or historical results. The instrumentation and ID-view preparation were implemented before the candidate run; the current candidate run was separately authorized and its outcome is recorded below.

## Independent candidate evaluation and outcome

Candidate evaluation IDs are positions 200–299 of the pinned `data/ids/musique_s500.json` list (`S500[200:300]`, 100 questions). The frozen view is [musique_independent100_candidate.json](../data/ids/musique_independent100_candidate.json); ordered-ID SHA-256 is `a026de236266ceb4ee7faa4cde5d031996ecfd74f4e6edd806a8b08cc493d42b`. The view records source and labels hashes. Before the runs, the read-only check covered 29 MuSiQue run manifests and 4 raw-only result files; there was no overlap. This range lies outside the already-used first 100 IDs and the unrun `pilot200` prefix, and does not use or alter the separately reserved `holdout100` at positions 400–499.

The reader template, model digests, generation options, top-k, corpus, metrics and tracking schema were frozen for this candidate. Dense 3B completed 100 questions (`98d8b412-cec6-45e4-9c14-0e4ad85855bb`): EM 0.110, token F1 0.1858, recall@5 0.6058. Its ordered IDs match the view and result SHA is recorded in the compact [candidate summary](../results/summary/musique-independent-candidate-s500-200-299.json).

The fresh HippoRAG index build (`e78eff08-532a-40b3-a359-49a6b08b32a7`) completed graph construction but failed the gate before QA. It recorded 11,025 attempts for 11,000 expected outcomes; no expected outcomes were missing and there were no unexpected attempt IDs. The gate found 160 unresolved terminal outcomes: 122 truncated triple extractions, 37 truncated NER extractions and one NER request error. Some failed attempts were resolved by explicit retries; 25 retry attempts are included in the attempt count. Two NER request-error attempts had no response-cache outcome and unknown usage; their attempt/error provenance is present. The failure ledger and diagnostic index are preserved locally; the safe summary contains aggregates only. No HippoRAG QA answers were generated, so paired comparison and paired bootstrap were not run. This index is diagnostic and is not an eligible independent HippoRAG result.

### Implementation finding after the candidate gate

All 39 NER truncations reached exactly 512 completion tokens; all 123 triple truncations reached exactly 2,048. These are the configured stage caps, not random malformed outputs. Upstream defaults are `openie_ner_max_tokens=512` and `openie_triple_max_tokens=2048`. A runner review found that a truncated response which the repair parser could partially parse bypassed the retry branch, because the branch only checked the parsed error flag. The runner now classifies `finish_reason=length` as retry-required even if partial JSON parsed. Before the next index build, the runner must also record and use explicitly higher per-stage retry caps and an adequate, validated context window; simply retrying with the same cap is not a repair policy. This correction is unit-tested. It does not alter or rebuild the preserved candidate index.

The retry policy remains bounded to one uncached retry per stage and passage. A complete `stop` response is never retried because its extraction is empty. A `length` outcome is retried once with a predeclared higher cap; retry cap, context setting, usage and retry linkage must be present in the manifest. If the retry remains truncated or otherwise invalid, the index remains diagnostic and QA does not start. The caps and context must be chosen and frozen before the next run; they are not silently inferred from candidate answers.

The candidate view lies within the pinned S500 sample and is not evidence of representativeness for the source datasets or target API/T4 setup. No prompt or parameter selection was done using candidate answers. A future paired comparison requires a new readiness report, a reviewed OpenIE failure/retry policy and separate authorization; do not automatically repair or rebuild this index.

## Consequences and review conditions

- OpenIE coverage is not an extraction-quality score; semantic quality needs a separate labeled audit.
- Historical cache rows remain unattributed. Do not fabricate per-passage statuses for them.
- The complete original graph-build usage remains unknown because prior attempts and one request have incomplete usage.
- The fresh candidate HippoRAG build has two NER request-error attempts with unknown usage and no response-cache outcome; their attempt/error provenance is present. Its locally observed usage is not usage for an internal API.
- The independent candidate Dense run is not paired with a HippoRAG QA run because the latter was blocked before answering questions.
- One answer in the rebuilt debug10 run ended with `length` without `Answer:`; it remains an empty evaluated answer.
- Revisit the acceptance gate if the package cannot expose a stage outcome per passage or if failures cannot be zeroed without changing the scientific protocol. Any such change needs a new ADR before an independent run.
