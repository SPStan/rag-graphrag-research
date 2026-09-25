"""Optional two-request context pilot; never run without explicit authorization."""

import argparse
from importlib import metadata as importlib_metadata
import json
from pathlib import Path
from urllib.request import Request, urlopen

from scripts.plan_hipporag_repair import load_source_inputs, build_plan_report
from scripts.preflight_hipporag_repair_prompts import (
    render_source_prompts, validate_upstream_pin,
)
from scripts.run_hipporag import model_info, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]


def select_pilot_prompts(rows):
    """Choose the longest known NER and triple prompt by rendered bytes."""
    selected = []
    for stage in ("openie_ner", "openie_triples"):
        candidates = [row for row in rows if row["stage"] == stage]
        if not candidates:
            raise ValueError(f"No known prompt for {stage}")
        selected.append(max(candidates, key=lambda row: (row["utf8_bytes"], -row["order"])))
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "results" / "raw" /
                        "hipporag2-musique-e78eff08-532a-40b3-a359-49a6b08b32a7.manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "raw" /
                        "hipporag-repair-context-pilot.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        raise RuntimeError("Measurement model requests require --execute and separate authorization")
    raw_root = (ROOT / "results" / "raw").resolve()
    output = args.output.resolve()
    if raw_root not in output.parents or output.exists():
        raise ValueError("Pilot output must be a new private file under results/raw")
    manifest, ids, attempts, manifest_sha, corpus_sha = load_source_inputs(args.manifest)
    distribution = importlib_metadata.distribution("hipporag")
    validate_upstream_pin(distribution.version, distribution.read_text("direct_url.json"))
    plan = build_plan_report(manifest["run_id"], ids, attempts,
                             manifest_sha256=manifest_sha, corpus_sha256=corpus_sha)
    frozen_plan = json.loads((ROOT / "results" / "summary" /
                              "hipporag-repair-plan.json").read_text(encoding="utf-8"))
    if plan["plan_sha256"] != frozen_plan["plan_sha256"]:
        raise ValueError("Frozen repair plan changed")
    generation = manifest["generation"]
    model = generation["model"]["name"]
    digest = generation["model"]["digest"]
    options = generation["options"]
    if model_info(model, generation["endpoint"])["digest"] != digest:
        raise ValueError("Local model digest changed")
    rows, pending = render_source_prompts(manifest, ids, attempts, include_messages=True)
    chosen = select_pilot_prompts(rows)
    result = {"status": "running", "source_manifest_sha256": manifest_sha,
              "source_corpus_sha256": corpus_sha,
              "plan_sha256": plan["plan_sha256"], "model_digest": digest,
              "num_ctx": options["num_ctx"], "pending_dependent_prompts": pending,
              "max_requests": 2, "completed": [], "in_flight": None}
    endpoint = generation["endpoint"].removesuffix("/v1").rstrip("/") + "/api/chat"
    output.parent.mkdir(parents=True, exist_ok=True)
    for row in chosen:
        result["in_flight"] = {"stage": row["stage"], "prompt_sha256": row["prompt_sha256"]}
        write_json_atomic(output, result)
        payload = {"model": model, "messages": row["messages"], "stream": False,
                   "format": "json", "truncate": False,
                   "options": {"num_ctx": options["num_ctx"], "num_predict": 1,
                               "temperature": options["temperature"],
                               "seed": options["seed"]}}
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=300) as response:
            reply = json.load(response)
        count = reply.get("prompt_eval_count")
        if type(count) is not int or count < 0:
            raise ValueError("Ollama did not report a valid prompt token count")
        completion = reply.get("eval_count")
        if type(completion) is not int or completion < 0:
            completion = None
        result["completed"].append({"stage": row["stage"],
                                    "prompt_sha256": row["prompt_sha256"],
                                    "input_tokens": count,
                                    "completion_tokens": completion,
                                    "usage_unknown": completion is None})
        result["in_flight"] = None
        write_json_atomic(output, result)
    result["status"] = "pilot_complete"
    write_json_atomic(output, result)
    print(json.dumps({"status": result["status"], "requests": len(result["completed"]),
                      "output": output.name}))


if __name__ == "__main__":
    main()
