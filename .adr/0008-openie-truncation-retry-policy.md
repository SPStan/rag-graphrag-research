# ADR-0008 — OpenIE truncation retry policy

- Date: 2026-09-25
- Status: accepted for runner behavior; numeric retry caps and context window must be frozen before the next index build
- Related: [ADR-0007](0007-openie-extraction-audit-and-independent-evaluation.md)

## Context

The candidate HippoRAG index build `e78eff08-532a-40b3-a359-49a6b08b32a7` failed the OpenIE gate before QA. Every observed NER truncation reached the 512-token stage cap and every triple truncation reached the 2,048-token cap. Code review found that a partial JSON repair could make an answer parse successfully while `finish_reason=length` was ignored by the runner's retry condition. The existing retry also reused the upstream stage cap, so its token budget was not sufficient to address a hard-cap truncation.

## Decision

- A response with `finish_reason=length` is incomplete even when the repair parser can recover some entities or triples. Preserve the truncated attempt and always classify it as retry-required.
- Permit at most one uncached retry per passage and extraction stage. Do not retry a valid `finish_reason=stop` empty extraction.
- The retry must use an explicitly configured, higher stage-specific generation cap. Runner defaults are 1,024 generated tokens for NER retry and 3,072 for triples retry, versus upstream initial caps of 512 and 2,048. The values are CLI-overridable and the runner requires `num_ctx` to exceed the larger retry cap. Record both initial and retry caps, context-window setting, attempt linkage, finish reason, response hash, cache status, usage (unknown when unavailable), and elapsed time in the run manifest/ledger.
- Do not silently accept recovered partial content as a complete extraction. If the retry is still truncated or invalid, keep the index diagnostic and stop before QA.
- Freeze caps, model, prompt/schema, and context setting before the run. Check that the configured context can accommodate the rendered prompt and retry generation. Do not tune them against the candidate answers.
- A rebuild is explicit, uses a new fingerprinted storage namespace, and preserves the diagnostic index, cache, manifests, and raw outputs. No automatic rebuild is permitted.

## Alternatives considered

1. Treat repairable partial JSON as success: rejected because it hides known truncation and can omit later entities/triples.
2. Retry with the original cap: rejected because the candidate outputs demonstrably reached that same hard limit.
3. Raise all caps automatically from `finish_reason`: rejected because context limits, resource use, and cache identity must be explicit and reproducible.
4. Accept unresolved failures and continue QA: rejected because systems would be evaluated on a graph with undocumented missing extractions.

## Consequences and verification

The runner's retry predicate now includes `finish_reason=length`, stage retry caps are explicit CLI settings included in the manifest and index namespace fingerprint, and a unit test covers truncated output whose partial JSON was otherwise parseable. The default retry caps are a protocol proposal; inspect expected prompt lengths and confirm hardware/context feasibility in the readiness report before a costly build. This ADR does not authorize or trigger an index rebuild. Before a candidate comparison, verify the frozen configuration, cache behavior, manifest fields, zero unresolved gate outcomes, and exact question-ID pairing. A failed gate means no HippoRAG QA and no paired metrics/bootstrap.

## Review conditions

Revisit this policy if the chosen model/context cannot complete extractions under a predeclared cap, if one retry is insufficient, or if a future labeled extraction audit shows that valid empty outputs need different handling. Any additional retries or partial-output salvage policy requires a new decision and must account for all additional usage.
