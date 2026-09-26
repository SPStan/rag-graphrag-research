# ADR-0010 — Measure complete chat prompts before OpenIE repair

- Date: 2026-09-25
- Status: native transport selected offline; full context policy and real run remain unverified

## Context

The pinned Qwen2.5 3B Q4_K_M tokenizer and Ollama chat template are not available as an independently verified local counting path. UTF-8 byte lengths for 158 known prompts are diagnostics only. Another 38 triple prompts depend on corrected NER values and cannot exist before those values are saved.

## Decision proposal

Use a bounded native Ollama `/api/chat` measurement request with the same model, full rendered messages, JSON mode, seed, temperature and `num_ctx`, `num_predict=1`, `stream=false`, and `truncate=false`. Record `prompt_eval_count` against the exact prompt SHA. Reject absent/invalid counts and any server that does not confirm nontruncating chat behavior. First run a two-request pilot on the longest known NER and triple prompts; no automatic continuation follows it. If the pilot validates the method, measure each remaining known prompt before its repair request. Measure each dependent triple only after its successful NER checkpoint exists and immediately before its triple request. Keep the current context-fit guard until an ADR update and a test establish that native measured counts match the actual OpenAI-compatible transport for the same prompt. No measurement is authorized by this decision text.

## Alternatives

- Infer tokens from UTF-8 bytes: rejected because byte length is not token count.
- Require all 38 dependent prompts before NER: impossible without the corrected entities.
- Disable context guard and rely on runtime truncation: rejected because it can silently change the extraction input.
- Continue searching indefinitely for a local tokenizer/template pairing: rejected after the bounded environment inspection recorded in the existing preflight.

## Consequences and verification

The pilot costs at most two local one-token model requests and writes only hashes/counts to ignored `results/raw`. An interrupted pilot leaves an in-flight marker and does not auto-replay. A two-request pilot cannot prove fit for the other 194 prompts or the later corrected triple prompts; any full pass would require per-prompt measurements and a separate bounded repair authorization. The source run, digest, plan hash, frozen caps, and namespace are listed in `docs/R3_RUN_PROPOSAL.md`. Reconsider this approach if the installed Ollama version ignores `truncate=false`, native and compatible API usage disagree, or the model/context cannot accommodate the declared output caps.

Primary API references: [Ollama chat request types](https://github.com/ollama/ollama/blob/main/api/types.go) and [API usage fields](https://github.com/ollama/ollama/blob/main/docs/api.md).

## Transport finding, 2026-09-25

Ollama 0.34.4's OpenAI-compatible middleware decodes only declared ChatCompletionRequest fields. That type has no `options`, `num_ctx`, or `truncate` field; conversion to native ChatRequest therefore drops the executor's `extra_body.options.num_ctx`. The earlier SDK payload capture proves what the client sent, not what Ollama applied. The OpenAI-compatible repair adapter now refuses to construct a request callback. The two pilot counts remain observations for native `/api/chat` only.

The offline implementation now uses one native `/api/chat` payload builder for measurement and extraction. A transport stub verifies `num_ctx`, `truncate=false`, JSON mode, seed, temperature and output cap without sending a request. The per-task wrapper measures the rendered prompt first, validates input tokens plus the frozen output cap, then permits extraction; a synthetic overflow sends no extraction request. Measurement usage is attached to the private attempt record. This removes the cross-route mismatch. A live server result, all per-prompt token counts, and real repair remain unverified and require a separately authorized run. The OpenAI-compatible adapter stays fail-closed.

Versioned source: [OpenAI request conversion](https://github.com/ollama/ollama/blob/v0.34.4/openai/openai.go), [middleware](https://github.com/ollama/ollama/blob/v0.34.4/middleware/openai.go).

## Pilot observation, 2026-09-25

The user authorized exactly two local measurement requests. Ollama 0.34.4 was available; its versioned API declares `truncate=false` for chat. The selected known NER prompt reported 691 input tokens and the selected known triple prompt 1003. With frozen proposed caps, the totals are 1715/4096 and 4075/4096; the latter leaves only 21 tokens. The private pilot artifact SHA-256 is `385b3538b48fdb1acf6c09b5ae32ee78723449e2d594b5248b7c5fa5c2db659c`. No extraction or graph request was made. These two byte-longest examples do not bound the other prompt token counts, especially the 38 dependent triples. The native and OpenAI-compatible usage equivalence is still unverified, so the existing context guard remains closed. Completion token counts from these two responses were not retained by the first pilot implementation and are recorded as unknown, not zero.

## Bounded-run observation, 2026-09-25

The user later authorized a bounded first repair attempt. Offline preflight verified the frozen 196-task plan and seven source artifact hashes. Four native `/api/chat` requests were made for two NER tasks (measure then extract). Ollama `/api/ps` confirmed `size_vram=2159374499`. The first extraction was `valid_nonempty` (45 completion tokens); the second hit the frozen 1024-token NER cap and was `truncated` (1024 completion tokens). All measurement and extraction usage counters were present. The runner stopped immediately after that unresolved result, without retries or later tasks. Private checkpoint SHA-256: `83f61962940c06c912ff0c595a8617be298698b802151bc50d8136d2ef331d13`. This confirms native context accounting and GPU placement for those requests only; it does not establish fit for remaining prompts. Cap/retry changes require an ADR-0008 review and explicit decision before any further model calls. No embeddings, graph rebuild, or QA ran.
