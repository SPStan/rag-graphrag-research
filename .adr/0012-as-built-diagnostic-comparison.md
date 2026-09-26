# ADR-0012 — Compare Dense and the existing diagnostic HippoRAG index

Date: 2026-09-26. Status: accepted for a local diagnostic comparison.

The user explicitly requested execution of Dense versus HippoRAG comparison,
instead of further model-size experiments. The candidate graph already exists;
its strict independent-evaluation gate failed on 160 OpenIE stage outcomes.

Evaluate the as-built graph on the same frozen S500[200:300] questions as the
completed Dense run 98d8b412-cec6-45e4-9c14-0e4ad85855bb. This measures the
actual imperfect local pipeline, not a repaired or accepted independent index.
Keep `independent_benchmark_eligible=false` and the original failed gate in the
new manifest. Do not change the strict gate or relabel truncated extractions.

Copy the source index into a new namespace, verify file hashes and corpus
coverage, and never call index/OpenIE/rebuild. Use pinned HippoRAG retrieval,
native Ollama text chat for its upstream fact-filter prompt, and the exact
Dense reader messages, model digest, options and top-k. Fact-filter failures
and native upstream dense fallbacks must be reported. No 7B or holdout100.
The native transport fixes explicit context handling; this is a separately
identified diagnostic query configuration, not a reproduction of the original
OpenAI-compatible query transport. Source index extraction remains unchanged.

Bound the run to 100 questions, at most 100 fact-filter and 100 reader calls,
300 seconds per call and two hours before starting another question. No
automatic request retries. Persist each completed question and model response
privately; unknown request outcomes stop the run. Gold labels enter evaluation
only, never retrieval/generation. Reuse Dense answers after exact configuration,
ordered ID, corpus, template and result-SHA checks. Report paired differences
and descriptive bootstrap intervals without claiming population generalization.

Alternative: keep repairing until zero unresolved extraction. Rejected for this
diagnostic milestone because it prevents observing the current system's quality.
This does not establish that failures are harmless. A later primary benchmark
needs a separately frozen failure policy and target API validation.
