"""Offline native capacity audit and bounded RAPTOR summary continuation."""

import copy
import ctypes as c
import json
import os
from pathlib import Path
import sys
import uuid

from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts.token_accounting import verified_reference

POLICY = {
    "version": "length_fallback_native_capacity_v1",
    "trigger": "baseline_finish_reason_length",
    "desired_words": 300,
    "fallback_max_tokens": 1536,
    "max_corrective_attempts_per_dataset": 1,
    "max_new_corrective_attempts_this_continuation": 0,
    "max_new_posts": 4000,
    "mandatory": ["stop", "nonempty", "complete_usage", "native_embedding_fit"],
}
GGUF_SHA = "daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c"
DLL_SHA = "00ea020d8a1fe830eafd030ff0fc80eee339c7bce9916a53a3078de97c4aee8d"


class NativeBGE:
    """Installed Win64 libllama tokenizer; no context, decode, HTTP or embeddings.

    Win64 passes/returns large structs through caller-owned storage. Reserve
    storage for native default params without interpreting fields; the native
    filename loader consumes the initialized prefix. Never use the FILE* API.
    This adapter is pinned to the audited DLL, not an arbitrary llama build.
    """

    def __init__(self, blob, library_dir):
        blob, library_dir = Path(blob), Path(library_dir)
        if sys.platform != "win32" or c.sizeof(c.c_void_p) != 8:
            raise ValueError("native_bge_requires_win64")
        if (
            dense.sha256_file(blob) != GGUF_SHA
            or dense.sha256_file(library_dir / "libllama.dll") != DLL_SHA
        ):
            raise ValueError("native_bge_pin_mismatch")
        self.directory = os.add_dll_directory(str(library_dir))
        self.lib = c.CDLL(str(library_dir / "libllama.dll"))
        backend = c.CDLL(str(library_dir / "ggml.dll"))
        backend.ggml_backend_load_all_from_path.argtypes = [c.c_char_p]
        backend.ggml_backend_load_all_from_path(str(library_dir).encode())
        self.lib.llama_backend_init()

        class Params(c.Structure):
            _fields_ = [("storage", c.c_ubyte * 512)]

        self.lib.llama_model_default_params.restype = Params
        self.lib.llama_model_load_from_file.argtypes = [c.c_char_p, Params]
        self.lib.llama_model_load_from_file.restype = c.c_void_p
        self.model = self.lib.llama_model_load_from_file(
            str(blob).encode(), self.lib.llama_model_default_params()
        )
        if not self.model:
            raise ValueError("native_bge_model_load_failed")
        self.lib.llama_model_get_vocab.argtypes = [c.c_void_p]
        self.lib.llama_model_get_vocab.restype = c.c_void_p
        self.vocab = self.lib.llama_model_get_vocab(self.model)
        self.lib.llama_tokenize.argtypes = [
            c.c_void_p,
            c.c_char_p,
            c.c_int32,
            c.POINTER(c.c_int32),
            c.c_int32,
            c.c_bool,
            c.c_bool,
        ]
        self.lib.llama_tokenize.restype = c.c_int32
        self.lib.llama_model_free.argtypes = [c.c_void_p]

    def count(self, text, special=True):
        data = text.encode("utf-8")
        size = self.lib.llama_tokenize(
            self.vocab, data, len(data), None, 0, special, False
        )
        if size >= 0:
            return size
        tokens = (c.c_int32 * -size)()
        count = self.lib.llama_tokenize(
            self.vocab, data, len(data), tokens, -size, special, False
        )
        if count != -size:
            raise ValueError("native_bge_tokenization_failed")
        return count

    def close(self):
        self.lib.llama_model_free(self.model)
        self.directory.close()


def audit_response(plan, row, original, body, native_tokens):
    from scripts import run_e1 as e

    choice = body["choices"][0]
    usage = e.extract_usage(body, "llm", "target_api")
    text = choice["message"]["content"]
    if (
        choice["finish_reason"] != "stop"
        or not isinstance(text, str)
        or not text.strip()
        or any(
            type(usage[k]) is not int for k in ("llm_input_tokens", "llm_output_tokens")
        )
        or usage["llm_output_tokens"] > POLICY["fallback_max_tokens"]
    ):
        raise ValueError("fallback_requires_complete_response_and_usage")
    if row.get("embedding_options") != e.RAPTOR_EMBEDDING_OPTIONS:
        raise ValueError("fallback_embedding_options_changed")
    capacity = min(row["embedding_options"].values())
    if type(native_tokens) is not int or not 0 < native_tokens <= capacity:
        raise ValueError("fallback_native_embedding_overflow")
    return {
        "policy": POLICY,
        "method": row["method"],
        "dataset": row["dataset"],
        "status": "accepted_offline",
        "http_execution_authorized": False,
        "original_request_sha256": target.digest(
            {"payload": original, "kind": "llm", "operation": "summary"}
        ),
        "response_text_sha256": target.digest(text),
        "embedding_model": plan["embedding_model"],
        "embedding_digest": plan["embedding_digest"],
        "embedding_options": row["embedding_options"],
        "native_tokens_with_special": native_tokens,
        "gguf_sha256": GGUF_SHA,
        "native_library_sha256": DLL_SHA,
        "whitespace_words": len(text.split()),
        "word_limit_is_advisory": True,
    }


def verify_adoption(plan, row, path):
    from scripts import run_e1 as e

    record = dense.read_json(path)
    if (
        record.get("policy") != POLICY
        or record.get("semantic_review", {}).get("status")
        != "supported_by_input_context"
    ):
        raise ValueError("fallback_policy_or_semantic_review_missing")
    parent = e.ROOT / record["parent_output"] / "manifest.json"
    probe = e.ROOT / record["probe_output"] / "manifest.json"
    for mp, sha in (
        (parent, record["parent_manifest_sha256"]),
        (probe, record["probe_manifest_sha256"]),
    ):
        if dense.sha256_file(mp) != sha:
            raise ValueError("fallback_source_manifest_changed")
    original_path = e.ROOT / record["original_payload_path"]
    if dense.sha256_file(original_path) != record["original_payload_file_sha256"]:
        raise ValueError("fallback_original_payload_changed")
    original = dense.read_json(original_path)
    proof_path = e.ROOT / record["native_proof_path"]
    if dense.sha256_file(proof_path) != record["native_proof_sha256"]:
        raise ValueError("fallback_native_proof_changed")
    proof = dense.read_json(proof_path)
    if (
        proof["response_sha256"] != record["response_sha256"]
        or proof["gguf_sha256"] != GGUF_SHA
        or proof["library_sha256"] != DLL_SHA
        or proof["native_tokens_with_special"] != record["native_tokens_with_special"]
        or proof["control_tokens"] != 2104
        or record["context_sha256"] != target.digest(original["messages"][1]["content"])
        or not record["semantic_review"].get("claims")
        or any(c["status"] != "supported" for c in record["semantic_review"]["claims"])
    ):
        raise ValueError("fallback_capacity_or_review_changed")
    proposed = e.summary_probe_payload(original)
    fallback_key = target.digest(
        {"payload": proposed, "kind": "llm", "operation": "summary"}
    )
    if fallback_key != record["fallback_request_sha256"]:
        raise ValueError("fallback_request_identity_changed")
    leaf = e.verified_raptor_leaf_scope(plan, row)
    _, failures, _ = e.verified_checkpoints(
        parent, leaf_producer=leaf, allow_summary_length=True
    )
    if (
        len(failures) != 1
        or failures[0][0]["object_id"] != record["original_request_sha256"]
    ):
        raise ValueError("fallback_requires_one_original_length")
    cache, rejected, ref = e.verified_checkpoints(probe)
    manifest = dense.read_json(probe)
    if (
        manifest["parent_manifest_sha256"] != record["parent_manifest_sha256"]
        or manifest["status"] != "failed"
        or manifest["policy"] != e.SUMMARY_PROBE_POLICY
        or rejected
        or not ref["summary"]["complete"]
        or ref["summary"]["attempts"] != 1
    ):
        raise ValueError("fallback_probe_provenance_invalid")
    item = cache[fallback_key]
    if item["sha256"] != record["response_sha256"]:
        raise ValueError("fallback_response_changed")
    body = dense.read_json(item["path"])
    checked = audit_response(
        plan, row, original, body, record["native_tokens_with_special"]
    )
    if any(record.get(k) != v for k, v in checked.items()):
        raise ValueError("fallback_audit_changed")
    return record, item


def reuse_fallback(runner, original_key):
    entry = runner.row.get("summary_adoption")
    if not entry or original_key != entry["original_request_sha256"]:
        return None
    from scripts import run_e1 as e

    path = e.ROOT / entry["path"]
    if dense.sha256_file(path) != entry["sha256"]:
        raise ValueError("fallback_adoption_changed")
    # Verification was performed before construction/HTTP in Transport.__init__.
    record, item = runner.summary_adoption_verified
    if dense.sha256_file(item["path"]) != item["sha256"]:
        raise ValueError("fallback_response_changed")
    mapping_path = runner.calls.parent / "summary-fallbacks.json"
    mapping = dense.read_json(mapping_path) if mapping_path.exists() else {}
    association = {
        "fallback_request_sha256": record["fallback_request_sha256"],
        "response_sha256": item["sha256"],
        "producer_run_id": item["run_id"],
        "adoption_sha256": entry["sha256"],
        "policy_version": POLICY["version"],
    }
    if original_key in mapping and mapping[original_key] != association:
        raise ValueError("fallback_association_changed")
    mapping[original_key] = association
    dense.write_json_atomic(mapping_path, mapping)
    # The journal names the DIFFERENT request, never a hit on the old length key.
    runner.journal.cache_hit(
        phase="index",
        operation="summary",
        provider="target_api",
        model=runner.plan["model"],
        kind="llm",
        object_id=record["fallback_request_sha256"],
        producer_run_id=item["run_id"],
        producer_usage_complete=item["producer_complete"],
    )
    runner.last_cache_hit = True
    return dense.read_json(item["path"])


def check_embedding_fit(runner, payload):
    key = target.digest(
        {"payload": payload, "kind": "embedding", "operation": "index_embedding"}
    )
    if key in runner.parent_cache:
        return
    if not hasattr(runner, "native_bge"):
        config = runner.plan["native_tokenizer"]
        runner.native_bge = NativeBGE(config["gguf_path"], config["library_dir"])
    capacity = min(runner.row["embedding_options"].values())
    if any(runner.native_bge.count(text) > capacity for text in payload["input"]):
        raise ValueError("summary_native_embedding_overflow_before_http")


def prepare_continuation(prior_path, adoption_path, native_config):
    from scripts import run_e1 as e

    original = dense.read_json(prior_path)
    if (
        e.code_dirty()
        or original["workspace"] != str(e.ROOT.resolve())
        or original.get("raptor_summary_resume")
    ):
        raise ValueError("summary_resume_requires_clean_live_prior")
    parent = {
        "path": str(prior_path.resolve()),
        "sha256": dense.sha256_file(prior_path),
        "digest": target.digest(original),
    }
    plan = copy.deepcopy(original)
    plan.update(
        parent_plan=parent,
        lineage=[parent, *original.get("lineage", [])],
        raptor_summary_resume=True,
        summary_fallback_policy=POLICY,
    )
    for pin in plan["lineage"]:
        if dense.sha256_file(Path(pin["path"])) != pin["sha256"]:
            raise ValueError("lineage_plan_changed")
    for r in plan["rows"]:
        directory = e.ROOT / r["output"]
        mp = directory / "manifest.json"
        if (directory / "running.lock").exists() or (
            mp.exists() and dense.read_json(mp)["status"] == "running"
        ):
            raise ValueError("summary_resume_requires_stopped_workers")
    row = next(
        r for r in plan["rows"] if (r["method"], r["dataset"]) == ("raptor", "hotpotqa")
    )
    if row.get("history_runs"):
        raise ValueError("summary_resume_requires_original_hotpot")
    record, item = verify_adoption(plan, row, adoption_path)
    tokenizer = NativeBGE(native_config["gguf_path"], native_config["library_dir"])
    try:
        actual = tokenizer.count(
            dense.read_json(item["path"])["choices"][0]["message"]["content"]
        )
        if actual != record["native_tokens_with_special"]:
            raise ValueError("fallback_native_count_changed")
    finally:
        tokenizer.close()
    plan["native_tokenizer"] = {
        **native_config,
        "gguf_sha256": GGUF_SHA,
        "library_sha256": DLL_SHA,
    }
    history = []
    for output in (record["parent_output"], record["probe_output"]):
        mp = e.ROOT / output / "manifest.json"
        manifest = dense.read_json(mp)
        ref = verified_reference(manifest, mp)
        reserve = e.current_unknown_reservation(mp.parent)
        if ref["status"] != "verified" or type(reserve) is not int:
            raise ValueError("summary_resume_incomplete_history")
        history.append(
            {
                "output": output,
                "run_id": manifest["run_id"],
                "manifest_sha256": dense.sha256_file(mp),
                "summary": ref["summary"],
                "unknown_reserved_upper_bound": reserve,
            }
        )
    charge = sum(
        sum(h["summary"]["known_subtotal"].values()) + h["unknown_reserved_upper_bound"]
        for h in history
    )
    if charge >= row["token_limit"]:
        raise ValueError("summary_resume_budget_exhausted")
    old = e.ROOT / row["output"]
    row.update(
        history_runs=history,
        prior_run=history[-1],
        diagnostics_in_history=True,
        resume_sources=[
            {k: h[k] for k in ("output", "manifest_sha256")} for h in history
        ],
        resume_from={k: history[-1][k] for k in ("output", "manifest_sha256")},
        resume_kind="summary_native",
        output=f"indexes/e1/{plan['batch_id']}/raptor/hotpotqa-summary1",
        run_id=str(uuid.uuid4()),
        code_commit=e.git("rev-parse", "HEAD"),
        prior_budget_charge=charge,
        token_limit=row["token_limit"] - charge,
        max_new_posts=POLICY["max_new_posts"],
        summary_adoption={
            "path": adoption_path.relative_to(e.ROOT).as_posix(),
            "sha256": dense.sha256_file(adoption_path),
            "original_request_sha256": record["original_request_sha256"],
        },
    )
    if (e.ROOT / row["output"]).exists():
        raise ValueError("summary_resume_output_must_be_new")
    with (old / "summary-resume-once.claim.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {"child_run_id": row["run_id"], "parent_plan_sha256": parent["sha256"]},
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan["combined_token_limit"] = sum(r["token_limit"] for r in plan["rows"])
    return plan


TLS_POLICY = {
    "version": "raptor_tls_connect_once_v1",
    "timeout_seconds": [30, 300],
    "max_continuations": 1,
    "max_total_new_posts": 4000,
    "retry": 0,
}


def validate_network_failure(row, failures, reference):
    """Bind a fresh continuation to one terminal unknown summary request."""
    if len(failures) != 1 or reference["summary"]["attempts"] <= 0:
        raise ValueError("summary_network_requires_one_failure")
    started, terminal, checkpoint = failures[0]
    if (
        started["kind"] != "llm"
        or started["provider"] != "target_api"
        or started["operation"] != "summary"
        or terminal.get("error_code") != "ReadTimeout"
        or terminal["usage_status"] != "unknown"
        or checkpoint["status"] != "started"
        or type(checkpoint.get("reserved_tokens")) is not int
        or not 0 < checkpoint["reserved_tokens"] <= 262144
        or any(p["unfinished"] for p in reference["summary"]["phases"])
        or sum(p["errors"] for p in reference["summary"]["phases"]) != 1
    ):
        raise ValueError("summary_network_unexpected_failure")
    if row.get("network_prior_attempts") is not None and (
        row["network_prior_attempts"] != reference["summary"]["attempts"]
        or row["network_first_request_key"] != started["object_id"]
    ):
        raise ValueError("summary_network_failure_binding_changed")
    return started["object_id"], checkpoint["reserved_tokens"]


def prepare_network_continuation(prior_path, audit_path):
    """One explicit network continuation; failed usage remains unknown."""
    from scripts import run_e1 as e

    original = dense.read_json(prior_path)
    if (
        e.code_dirty()
        or original.get("raptor_summary_network_resume")
        or original["workspace"] != str(e.ROOT.resolve())
    ):
        raise ValueError("summary_network_requires_clean_unused_prior")
    plan = copy.deepcopy(original)
    row = next(
        r for r in plan["rows"] if (r["method"], r["dataset"]) == ("raptor", "hotpotqa")
    )
    if (
        row.get("resume_kind") != "summary_native"
        or row.get("max_new_posts") != POLICY["max_new_posts"]
    ):
        raise ValueError("summary_network_requires_first_native_continuation")
    for r in plan["rows"]:
        out = e.ROOT / r["output"]
        mp = out / "manifest.json"
        if (out / "running.lock").exists() or (
            mp.exists() and dense.read_json(mp)["status"] == "running"
        ):
            raise ValueError("summary_network_workers_must_be_stopped")
    audit = audit_path.read_text(encoding="utf-8")
    if not all(
        marker in audit
        for marker in (
            "do_handshake",
            "The handshake operation timed out",
            "read timeout=5",
            "requests.exceptions.ReadTimeout",
        )
    ):
        raise ValueError("summary_network_tls_audit_missing")
    parent = {
        "path": str(prior_path.resolve()),
        "sha256": dense.sha256_file(prior_path),
        "digest": target.digest(original),
    }
    lineage = [parent, *original.get("lineage", [])]
    for pin in lineage:
        if dense.sha256_file(Path(pin["path"])) != pin["sha256"]:
            raise ValueError("lineage_plan_changed")
    adoption = e.ROOT / row["summary_adoption"]["path"]
    if dense.sha256_file(adoption) != row["summary_adoption"]["sha256"]:
        raise ValueError("fallback_adoption_changed")
    verify_adoption(plan, row, adoption)
    cache = {}
    leaf = e.verified_raptor_leaf_scope(plan, row)
    for source in row["resume_sources"]:
        mp = e.ROOT / source["output"] / "manifest.json"
        if dense.sha256_file(mp) != source["manifest_sha256"]:
            raise ValueError("summary_network_source_changed")
        cache, _, _ = e.verified_checkpoints(
            mp, inherited=cache, leaf_producer=leaf, allow_summary_length=True
        )
    directory = e.ROOT / row["output"]
    mp = directory / "manifest.json"
    manifest = dense.read_json(mp)
    if manifest["status"] != "failed" or manifest.get("error_type") != "ReadTimeout":
        raise ValueError("summary_network_prior_not_failed_timeout")
    cache, failures, ref = e.verified_checkpoints(
        mp, inherited=cache, leaf_producer=leaf, allow_summary_length=True
    )
    key, bound = validate_network_failure(row, failures, ref)
    if (
        key in cache
        or (directory / "requests" / f"{key}.response.json").exists()
        or e.current_unknown_reservation(directory) != bound
    ):
        raise ValueError("summary_network_unknown_response_or_reserve_changed")
    history = copy.deepcopy(row["history_runs"])
    history.append(
        {
            "output": row["output"],
            "run_id": manifest["run_id"],
            "manifest_sha256": dense.sha256_file(mp),
            "summary": ref["summary"],
            "unknown_reserved_upper_bound": bound,
        }
    )
    if len({h["run_id"] for h in history}) != len(history):
        raise ValueError("summary_network_duplicate_history")
    for h in history:
        hp = e.ROOT / h["output"] / "manifest.json"
        actual = verified_reference(dense.read_json(hp), hp)
        if (
            dense.sha256_file(hp) != h["manifest_sha256"]
            or actual["status"] != "verified"
            or actual["summary"] != h["summary"]
            or e.current_unknown_reservation(hp.parent)
            != h["unknown_reserved_upper_bound"]
        ):
            raise ValueError("summary_network_history_changed")
    charge = sum(
        sum(h["summary"]["known_subtotal"].values()) + h["unknown_reserved_upper_bound"]
        for h in history
    )
    posts = ref["summary"]["attempts"]
    if charge >= e.LIMITS["raptor"] or posts >= TLS_POLICY["max_total_new_posts"]:
        raise ValueError("summary_network_budget_exhausted")
    row.update(
        history_runs=history,
        prior_run=history[-1],
        prior_budget_charge=charge,
        token_limit=e.LIMITS["raptor"] - charge,
        max_new_posts=TLS_POLICY["max_total_new_posts"] - posts,
        network_prior_attempts=posts,
        network_first_request_key=key,
        run_id=str(uuid.uuid4()),
        code_commit=e.git("rev-parse", "HEAD"),
        output=f"indexes/e1/{plan['batch_id']}/raptor/hotpotqa-summary-network1",
        resume_sources=[
            {k: h[k] for k in ("output", "manifest_sha256")} for h in history
        ],
        resume_from={k: history[-1][k] for k in ("output", "manifest_sha256")},
    )
    if (e.ROOT / row["output"]).exists():
        raise ValueError("summary_network_output_must_be_new")
    plan.update(
        parent_plan=parent,
        lineage=lineage,
        raptor_summary_network_resume=True,
        network_policy=TLS_POLICY,
        network_audit={
            "path": str(audit_path.resolve()),
            "sha256": dense.sha256_file(audit_path),
        },
        combined_token_limit=sum(r["token_limit"] for r in plan["rows"]),
    )
    with (directory / "network-resume-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {"parent_plan_sha256": parent["sha256"], "child_run_id": row["run_id"]},
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    return plan
