# ADR-0011 — Separate 7B OpenIE extraction variant (proposal)

- Date: 2026-09-25
- Status: proposed; no model request authorized by this document

## Context

The local HippoRAG candidate uses Qwen2.5 3B Q4_K_M for OpenIE. One NER stage remains unresolved after the source cap of 512 and two bounded repairs at caps 1024 and 2048. Both repair responses ended with `finish_reason=length`; the attempt-3 checkpoint is stopped (SHA-256 `1cf000239921f3dc36d4a879e5defe355c8ecbb7afc7e092bc31a193c8c57275`). Partial JSON is diagnostic only. The failed passage has 113 words and 334 measured prompt tokens; the successful preceding NER passage has 228 words. The available ledger stores response hashes, not response text, so it does not establish why generation continued to the cap.

Qwen2.5 7B Q4_K_M is already installed locally with digest `845dbda0ea48ed749caafd9e603704d7ca97d631a0b697e`; an earlier reader replay recorded GPU placement. Its OpenIE behavior on this passage has not been tested. Switching models within the existing 3B repair checkpoint would make the candidate's extraction policy inconsistent and would bypass the three-attempt limit.

## Proposal

Keep both 3B repair checkpoints stopped and immutable. First, if separately authorized, run a **diagnostic 7B probe**, not a repair attempt: use the exact pinned NER prompt and failed passage, native `/api/chat`, JSON mode, seed 42, temperature 0, `num_ctx=4096`, `truncate=false`, and cap 2048. Verify the installed digest and GPU placement. Measure the exact prompt once (`num_predict=1`), require `prompt_eval_count + 2048 <= 4096`, then make at most one extraction request. Limit each request to 300 seconds and the process to 10 minutes. Save only identity, prompt/response hashes, finish reason, parser status, usage and timing in a fresh private diagnostic artifact; never accept the output into the current ledger. Do not supply answer text or supporting labels. Unknown in-flight outcome, missing usage, digest/config mismatch, context overflow, parser error, or `finish_reason=length` stops the probe without retry. No embeddings, graph construction or QA belong to the probe.

If the diagnostic result is complete and valid, separately decide whether to build a **new 7B extraction variant** for the full frozen corpus, with a new namespace, uniform extraction model and recorded full indexing cost. Keep the common 3B reader, top-5, corpus and candidate question IDs for the later Dense comparison. Predeclare caps and gates before that build; a one-passage probe does not establish full-corpus success or model superiority. If the diagnostic fails, report the current local HippoRAG candidate as blocked and revisit the broader research plan rather than repeatedly raising caps.

## Alternatives and consequences

- Attempt 4 or another 3B cap increase: rejected for the current candidate; it breaks ADR-0008 and two increases already failed.
- Accept the partial NER list: rejected because the response is known incomplete.
- Switch only the unresolved passage to 7B: cheaper, but mixes extraction models within one index and weakens interpretation of method and cost. Reconsider only as a separately named hybrid variant.
- Split this short passage or rewrite the pinned prompt: changes the extraction method without evidence that input length caused the failure. A separate controlled variant would be needed.

No further model, embedding, rebuild or QA call follows from this proposal. A bounded diagnostic request needs the user's separate approval; a full 7B index and QA require later decisions.

## Offline preparation

The existing repair runner now has a separate `--probe-7b-ner` mode. It checks the frozen source plan, seven source artifacts, both stopped 3B checkpoint SHA values, exact pinned NER prompt SHA, installed 7B digest, and output path before any request. The diagnostic artifact is private and records an in-flight marker before each POST; a later invocation refuses to reuse the output path. A fake native transport test confirms exactly two calls and that no response text or extracted values enter the report or either 3B checkpoint. The pinned-environment `--probe-7b-ner --dry-run` passed without model requests. The proposed execution command is `& $hippoPython -m scripts.run_hipporag_repair --probe-7b-ner --execute`; it has **not** been run.
