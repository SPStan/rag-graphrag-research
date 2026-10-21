"""Bounded full-corpus E1 indexing; private checkpoints, public cost summaries."""

import argparse
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

import numpy as np
import requests
from dotenv import dotenv_values

from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts.token_accounting import (
    Journal,
    extract_usage,
    read_records,
    verified_reference,
)

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("dense", "hipporag2", "raptor")
DATASETS = ("musique", "hotpotqa")
# Independent, disjoint allocations: no caller can spend another row's allowance.
LIMITS = {"dense": 2_000_000, "hipporag2": 20_000_000, "raptor": 12_000_000}
RAPTOR_CLUSTERING_POLICY = "pinned_gmm_umap_singletons_n_le_4_v1"
PARAMETERS = {
    "seed": 42,
    "temperature": 0,
    "embedding_batch_size": 32,
    "embedding_dimension": 1024,
    "truncate": False,
    "ner_max_tokens": 1024,
    "triple_max_tokens": 3072,
    "summary_max_tokens": 4096,
    "num_layers": 2,
    "max_cluster_tokens": 3000,
    "reduction_dimension": 5,
    "threshold": 0.1,
    "timeout_seconds": [5, 300],
    "retry": 0,
    "redirects": False,
    "target_context": 262144,
    "thinking": False,
    "embedding_pacing_seconds_per_text": 0.1,
    "target_connection_close": True,
}
CYCLE_REPAIR = {
    "version": "unique-triples-v1",
    "max_per_dataset": 20,
    "instruction": 'Return only the JSON object with the "triples" field. Extract each supported triple exactly once. Do not repeat any triple. Do not output named_entities. When no more distinct supported facts remain, close the JSON array and object immediately.',
}
RAPTOR_EMBEDDING_OPTIONS = {"num_ctx": 4096, "num_batch": 4096}

TRIPLES_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "uniqueItems": True,
            "items": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 1},
            },
        }
    },
    "required": ["triples"],
    "additionalProperties": False,
}


def schema_probe_payload(original):
    """Change only response format; this does not establish server enforcement."""
    if original.get("max_tokens") != 3072 or original.get("response_format") != {
        "type": "json_object"
    }:
        raise ValueError("schema_probe_requires_original_triples_payload")
    payload = copy.deepcopy(original)
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": "openie_triples_unique_v1",
            "strict": True,
            "schema": copy.deepcopy(TRIPLES_SCHEMA),
        },
    }
    reserve = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 2048 + 3072
    if reserve > PARAMETERS["target_context"]:
        raise ValueError("schema_probe_context_reservation_exceeded")
    return payload, reserve


def validate_schema_probe_response(body):
    """Strict local acceptance; semantic support and server enforcement are separate."""
    choice = body["choices"][0]
    if choice["finish_reason"] != "stop":
        raise ValueError("schema_probe_generation_not_complete")
    usage = extract_usage(body, "llm", "target_api")
    if usage["llm_input_tokens"] is None or usage["llm_output_tokens"] is None:
        raise ValueError("schema_probe_unknown_usage")

    def unique_fields(pairs):
        if len(dict(pairs)) != len(pairs):
            raise ValueError("schema_probe_duplicate_json_field")
        return dict(pairs)

    parsed = json.loads(choice["message"]["content"], object_pairs_hook=unique_fields)
    if not isinstance(parsed, dict) or set(parsed) != {"triples"}:
        raise ValueError("schema_probe_invalid_object")
    values = parsed["triples"]
    if not isinstance(values, list) or any(
        not isinstance(x, list)
        or len(x) != 3
        or not all(isinstance(v, str) and v.strip() for v in x)
        for x in values
    ):
        raise ValueError("schema_probe_invalid_triples")
    if len({tuple(x) for x in values}) != len(values):
        raise ValueError("schema_probe_duplicate_triples")
    return values


def triple_cycle(text):
    """Diagnostic only: count complete tuples inside an unfinished response."""
    decoder, triples = json.JSONDecoder(), []
    for match in re.finditer(r'\[\s*"', text):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except ValueError:
            continue
        if (
            isinstance(value, list)
            and len(value) == 3
            and all(isinstance(x, str) for x in value)
        ):
            triples.append(tuple(value))
    unique = len(set(triples))
    return {
        "complete_tuples": len(triples),
        "unique_tuples": unique,
        "cycle": len(triples) >= 12 and unique * 4 <= len(triples),
    }


def git(*args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), *args],
        text=True,
    ).strip()


def code_dirty():
    allowed = {"results/summary/e1-indexing.json", "results/summary/e1-indexing.md"}
    # Strip individual lines only after retaining porcelain's three prefix columns.
    output = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "-C",
            str(ROOT),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        text=True,
    )
    return any(line[3:] not in allowed for line in output.splitlines())


def load_corpus(data_root, dataset):
    directory = Path(data_root) / "data/processed" / dataset
    corpus = dense.read_json(directory / "corpus.json")
    provenance = dense.validate_processed_data(
        dataset, directory, dense.read_json(directory / "queries.json"), corpus
    )
    if len(corpus) != 5500 or len({r["id"] for r in corpus}) != 5500:
        raise ValueError("E1_requires_5500_distinct_passages")
    return corpus, provenance


def make_plan(data_root, config, embedding_digest):
    rows = []
    batch_id = str(uuid.uuid4())
    code = git("rev-parse", "HEAD")
    if code_dirty():
        raise ValueError("commit_E1_code_before_preparing_plan")
    for method in METHODS:
        for dataset in DATASETS:
            corpus, provenance = load_corpus(data_root, dataset)
            rows.append(
                {
                    "run_id": str(uuid.uuid4()),
                    "method": method,
                    "dataset": dataset,
                    "passages": len(corpus),
                    "corpus": provenance,
                    "corpus_fingerprint": dense.corpus_fingerprint(corpus),
                    "code_commit": code,
                    "token_limit": LIMITS[method],
                    "output": f"indexes/e1/{batch_id}/{method}/{dataset}",
                }
            )
    return {
        "schema_version": 1,
        "kind": "E1_full_corpus_indexing",
        "batch_id": batch_id,
        "workspace": str(ROOT.resolve()),
        "data_root": str(Path(data_root).resolve()),
        "model": config["TARGET_API_MODEL"],
        "endpoint": config["TARGET_API_BASE_URL"].rstrip("/"),
        "embedding_model": "bge-m3:latest",
        "embedding_digest": embedding_digest,
        "parameters": PARAMETERS,
        "upstream_commits": {
            "hipporag2": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff",
            "raptor": "7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767",
        },
        "deployed_revision_and_quantization": "not reported; endpoint alias and backend contract only",
        "combined_token_limit": sum(r["token_limit"] for r in rows),
        "rows": rows,
        "historical_cost": "Previous smoke/failed runs excluded from NEW E1 cost; historical unknown remains unknown.",
    }


def verify_plan(plan, row, config):
    if plan.get("independent_raptor") and row["method"] != "raptor":
        raise ValueError("independent_plan_allows_only_raptor")
    for item in plan.get("lineage", []):
        if dense.sha256_file(Path(item["path"])) != item["sha256"]:
            raise ValueError("lineage_plan_changed")
    if (
        plan.get("parent_plan")
        and dense.sha256_file(Path(plan["parent_plan"]["path"]))
        != plan["parent_plan"]["sha256"]
    ):
        raise ValueError("parent_plan_changed")
    combinations = [(r["method"], r["dataset"]) for r in plan["rows"]]
    if (
        plan["kind"] != "E1_full_corpus_indexing"
        or plan["parameters"] != PARAMETERS
        or plan["workspace"] != str(ROOT.resolve())
        or row["method"] not in METHODS
        or row["dataset"] not in DATASETS
        or row["token_limit"]
        != LIMITS[row["method"]] - row.get("prior_budget_charge", 0)
        or plan["combined_token_limit"] != sum(r["token_limit"] for r in plan["rows"])
        or row["code_commit"] != git("rev-parse", "HEAD")
        or code_dirty()
        or (plan.get("cycle_repair") and plan["cycle_repair"] != CYCLE_REPAIR)
        or plan["model"] != config["TARGET_API_MODEL"]
        or plan["endpoint"] != config["TARGET_API_BASE_URL"].rstrip("/")
        or sorted(combinations) != sorted((m, d) for m in METHODS for d in DATASETS)
        or row["output"]
        != f"indexes/e1/{plan['batch_id']}/{row['method']}/{row['dataset']}"
        + (
            "-cluster1"
            if row.get("resume_kind") == "clustering"
            else "-batch1"
            if row.get("resume_kind") == "embedding_batch"
            else "-cycle1"
            if row.get("resume_kind") == "cycle"
            else "-network1"
            if row.get("resume_from")
            else "-continuation1"
            if row.get("prior_run")
            else ""
        )
    ):
        raise ValueError("E1_plan_or_code_mismatch")
    if plan.get("cycle_repair") and (row["method"], row["dataset"]) == (
        "hipporag2",
        "hotpotqa",
    ):
        pilot = next(
            r
            for r in plan["rows"]
            if (r["method"], r["dataset"]) == ("hipporag2", "musique")
        )
        path = ROOT / pilot["output"] / "manifest.json"
        prior = dense.read_json(path)
        probe = path.parent / "cycle-probe.json"
        if (
            prior["status"] != "completed"
            or prior["artifacts"].get("cycle-probe.json") != dense.sha256_file(probe)
            or dense.read_json(probe)["status"] != "passed"
        ):
            raise ValueError("cycle_repair_requires_successful_MuSiQue_probe_and_index")
    response = requests.get("http://localhost:11434/api/tags", timeout=10)
    response.raise_for_status()
    actual = next(
        m["digest"]
        for m in response.json()["models"]
        if m["name"] == plan["embedding_model"]
    )
    if actual != plan["embedding_digest"]:
        raise ValueError("embedding_model_changed")
    corpus, provenance = load_corpus(plan["data_root"], row["dataset"])
    if row["corpus"] != provenance or row[
        "corpus_fingerprint"
    ] != dense.corpus_fingerprint(corpus):
        raise ValueError("E1_input_changed")
    return corpus


@contextmanager
def exclusive(directory):
    """A canonical output lock; a crash deliberately needs operator inspection."""
    path = directory / "running.lock"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        yield
    finally:
        path.unlink()


class Transport:
    def __init__(self, plan, row, config, directory, journal, session=None):
        self.plan, self.row, self.config = plan, row, config
        self.directory, self.journal = directory, journal
        self.session = session or requests.Session()
        if any(adapter.max_retries.total for adapter in self.session.adapters.values()):
            raise ValueError("transport_retry_must_be_zero")
        self.calls = directory / "requests"
        self.calls.mkdir(exist_ok=True)
        self.logical_calls = 0
        self.last_embedding_started = 0.0
        self.last_cache_hit = False
        self.parent_cache = {}
        self.replayed_count = 0
        self.require_cache = False
        self.require_repair_key = False
        self.repairs_path = directory / "cycle-repairs.json"
        self.repairs = (
            dense.read_json(self.repairs_path) if self.repairs_path.exists() else {}
        )
        sources = row.get(
            "resume_sources", [row["resume_from"]] if row.get("resume_from") else []
        )
        leaf_producer = (
            verified_raptor_leaf_scope(plan, row)
            if sources and row["method"] == "raptor"
            else None
        )
        for source in sources:
            parent = ROOT / source["output"] / "manifest.json"
            if dense.sha256_file(parent) != source["manifest_sha256"]:
                raise ValueError("resume_manifest_changed")
            self.parent_cache, _, _ = verified_checkpoints(
                parent,
                inherited=self.parent_cache,
                allow_length=row.get("resume_kind") == "cycle",
                leaf_producer=leaf_producer,
            )

    def call(self, payload, *, kind, operation):
        key = target.digest({"payload": payload, "kind": kind, "operation": operation})
        checkpoint = self.calls / f"{key}.json"
        response = self.calls / f"{key}.response.json"
        if (
            self.require_cache
            and key not in self.parent_cache
            and not checkpoint.exists()
        ):
            raise ValueError("probe_requires_verified_cached_NER")
        summary = self.journal.summary()
        if not summary["complete"] or any(p["errors"] for p in summary["phases"]):
            raise ValueError("incomplete_or_failed_journal_cannot_continue")
        if key in self.parent_cache and not checkpoint.exists():
            item = self.parent_cache[key]
            if item["operation"] != operation or item["kind"] != kind:
                raise ValueError("parent_checkpoint_kind_mismatch")
            if dense.sha256_file(item["path"]) != item["sha256"]:
                raise ValueError("parent_response_changed")
            self.journal.cache_hit(
                phase="index",
                operation=operation,
                provider=item["provider"],
                model=item["model"],
                kind=kind,
                object_id=key,
                producer_run_id=item["run_id"],
                producer_usage_complete=item["producer_complete"],
            )
            self.last_cache_hit = True
            self.replayed_count += 1
            if self.replayed_count % 250 == 0:
                print(
                    f"Verified response replay: {self.replayed_count}/{len(self.parent_cache)}",
                    flush=True,
                )
            return dense.read_json(item["path"])
        if checkpoint.exists():
            saved = dense.read_json(checkpoint)
            records = read_records(self.journal.path)
            physical = {
                r["attempt_id"]
                for r in records
                if r["event"] == "finished" and not r.get("cache_hit")
            }
            starts = {
                r["attempt_id"]
                for r in records
                if r["event"] == "started"
                and r["object_id"] == key
                and r["attempt_id"] in physical
            }
            finishes = [
                r
                for r in records
                if r["event"] == "finished" and r["attempt_id"] in starts
            ]
            if (
                saved["status"] != "complete"
                or saved["request_sha256"] != key
                or saved["response_sha256"] != dense.sha256_file(response)
                or len(starts) != 1
                or len(finishes) != 1
            ):
                raise ValueError("unresolved_or_changed_checkpoint")
            self.journal.cache_hit(
                phase="index",
                operation=operation,
                provider="target_api" if kind == "llm" else "local_ollama",
                model=self.plan["model"]
                if kind == "llm"
                else self.plan["embedding_model"],
                kind=kind,
                object_id=key,
                producer_run_id=self.row.get("run_id", self.journal.run_id),
                producer_usage_complete=summary["complete"]
                and summary["historical_cache_cost_complete"],
            )
            self.last_cache_hit = True
            return dense.read_json(response)
        # UTF-8 byte upper bound plus framing and output reservation, before HTTP.
        input_bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
        if (
            kind == "llm"
            and input_bound + payload["max_tokens"] > PARAMETERS["target_context"]
        ):
            raise ValueError("context_reservation_exceeded")
        if self.journal.summary()["attempts"] >= 40000:
            raise ValueError("request_limit_exceeded")
        saved = {"request_sha256": key, "status": "started", "operation": operation}
        saved["reserved_tokens"] = input_bound + payload.get("max_tokens", 0)
        dense.write_json_atomic(checkpoint, saved)
        remote = kind == "llm"
        self.last_cache_hit = False
        if not remote:
            delay = len(payload["input"]) * PARAMETERS[
                "embedding_pacing_seconds_per_text"
            ] - (time.monotonic() - self.last_embedding_started)
            if delay > 0:
                time.sleep(delay)
            self.last_embedding_started = time.monotonic()
        body = target.checked_post(
            self.session,
            self.plan["endpoint"] + "/chat/completions"
            if remote
            else "http://localhost:11434/api/embed",
            payload,
            self.journal,
            phase="index",
            operation=operation,
            provider="target_api" if remote else "local_ollama",
            model=self.plan["model"] if remote else self.plan["embedding_model"],
            kind=kind,
            object_id=key,
            headers={
                "Authorization": f"Bearer {self.config['LITELLM_API_KEY']}",
                "Connection": "close",
            }
            if remote
            else None,
            response_path=response,
            token_limit=self.row["token_limit"],
            timeout=(5, 300),
        )
        # Invalid content is not a usable checkpoint, even with known usage.
        if remote:
            choice = body["choices"][0]
            if (
                choice["finish_reason"] != "stop"
                or not choice["message"]["content"].strip()
            ):
                raise ValueError("generation_not_complete")
        else:
            vectors = dense.normalize_rows(body["embeddings"])
            if vectors.shape != (len(payload["input"]), 1024):
                raise ValueError("embedding_shape_mismatch")
        saved.update(status="complete", response_sha256=dense.sha256_file(response))
        dense.write_json_atomic(checkpoint, saved)
        self.logical_calls += 1
        if self.logical_calls % 20 == 0:
            print(
                f"{self.row['method']}/{self.row['dataset']}: {self.journal.summary()['attempts']} POST",
                flush=True,
            )
        return body

    def embed(self, texts):
        options = self.row.get("embedding_options")
        if options is not None and (
            self.row["method"] != "raptor" or options != RAPTOR_EMBEDDING_OPTIONS
        ):
            raise ValueError("unsupported_RAPTOR_embedding_options")
        vectors = []
        for offset in range(0, len(texts), 32):
            payload = {
                "model": self.plan["embedding_model"],
                "input": texts[offset : offset + 32],
                "truncate": False,
            }
            old_key = target.digest(
                {
                    "payload": payload,
                    "kind": "embedding",
                    "operation": "index_embedding",
                }
            )
            # Reuse only an exact, verified old physical response. New options
            # affect uncached calls, never relabel or repay old embeddings.
            if options is not None and old_key not in self.parent_cache:
                payload["options"] = dict(options)
            body = self.call(
                payload,
                kind="embedding",
                operation="index_embedding",
            )
            vectors.extend(body["embeddings"])
        return dense.normalize_rows(vectors)

    def generate(self, messages, max_tokens, operation, response_format=None):
        payload = {
            **target.OPTIONS,
            "model": self.plan["model"],
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        key = target.digest({"payload": payload, "kind": "llm", "operation": operation})
        if self.require_repair_key and key != self.row.get("cycle_repair_request_key"):
            raise ValueError("probe_request_does_not_match_truncated_request")
        policy = self.plan.get("cycle_repair")
        if policy and policy != CYCLE_REPAIR:
            raise ValueError("cycle_repair_policy_mismatch")
        if policy and (
            key in self.repairs or key == self.row.get("cycle_repair_request_key")
        ):
            body = self.repair_cycle(payload, key, operation)
        else:
            try:
                body = self.call(payload, kind="llm", operation=operation)
            except ValueError as exc:
                if (
                    str(exc) != "generation_not_complete"
                    or not policy
                    or operation != "openie_triples"
                ):
                    raise
                old = dense.read_json(self.calls / f"{key}.response.json")
                choice = old["choices"][0]
                if (
                    choice["finish_reason"] != "length"
                    or not triple_cycle(choice["message"]["content"])["cycle"]
                ):
                    raise
                body = self.repair_cycle(payload, key, operation)
        return body["choices"][0]["message"]["content"], {
            **body["usage"],
            "finish_reason": body["choices"][0]["finish_reason"],
            "cache_hit": self.last_cache_hit,
        }

    def repair_cycle(self, payload, key, operation):
        if operation != "openie_triples":
            raise ValueError("cycle_repair_only_for_triples")
        revised = {
            **payload,
            "messages": [
                *payload["messages"],
                {"role": "user", "content": CYCLE_REPAIR["instruction"]},
            ],
        }
        revised_key = target.digest(
            {"payload": revised, "kind": "llm", "operation": operation}
        )
        if key not in self.repairs:
            if len(self.repairs) >= CYCLE_REPAIR["max_per_dataset"]:
                raise ValueError("cycle_repair_limit_exceeded")
            self.repairs[key] = {
                "revised_request_sha256": revised_key,
                "status": "started",
            }
            dense.write_json_atomic(self.repairs_path, self.repairs)
        elif (
            self.repairs[key]["status"] != "complete"
            or self.repairs[key]["revised_request_sha256"] != revised_key
        ):
            raise ValueError("unresolved_cycle_repair_cannot_repeat")
        body = self.call(revised, kind="llm", operation=operation)
        parsed = json.loads(body["choices"][0]["message"]["content"])
        values = parsed.get("triples")
        if not isinstance(values, list) or any(
            not isinstance(x, list)
            or len(x) != 3
            or not all(isinstance(v, str) and v.strip() for v in x)
            for x in values
        ):
            raise ValueError("invalid_cycle_repair_triples")
        if len({tuple(x) for x in values}) != len(values):
            raise ValueError("cycle_repair_still_repeats")
        self.repairs[key]["status"] = "complete"
        dense.write_json_atomic(self.repairs_path, self.repairs)
        return body


def verified_raptor_leaf_scope(plan, row):
    from scripts.e1_indexers import verified_dense_leaves

    corpus, provenance = load_corpus(plan["data_root"], row["dataset"])
    if (
        provenance != row["corpus"]
        or dense.corpus_fingerprint(corpus) != row["corpus_fingerprint"]
    ):
        raise ValueError("raptor_leaf_source_changed")
    _, manifest, leaves = verified_dense_leaves(corpus, plan, row["dataset"], ROOT)
    return {
        "run_id": manifest["run_id"],
        "keys": {target.digest(text) for text in leaves},
        "dataset": row["dataset"],
        "model": plan["embedding_model"],
    }


def verified_checkpoints(
    manifest_path,
    *,
    inherited=None,
    allow_length=False,
    allow_summary_length=False,
    leaf_producer=None,
):
    """Verify successful physical responses individually; never reuse a failed one."""
    manifest = dense.read_json(manifest_path)
    reference = verified_reference(manifest, manifest_path)
    if reference["status"] != "verified":
        raise ValueError("resume_journal_not_intact")
    for name, sha in manifest["artifacts"].items():
        if dense.sha256_file(manifest_path.parent / name) != sha:
            raise ValueError("resume_artifact_changed")
    records = read_records(reference["path"])
    finished = {r["attempt_id"]: r for r in records if r["event"] == "finished"}
    cache, failures = dict(inherited or {}), []
    for row in (r for r in records if r["event"] == "started"):
        terminal = finished.get(row["attempt_id"])
        if terminal is None:
            raise ValueError("resume_requires_terminal_physical_attempts")
        key = row["object_id"]
        if terminal.get("cache_hit"):
            if leaf_producer and key in leaf_producer["keys"]:
                if (
                    terminal["producer_run_id"] != leaf_producer["run_id"]
                    or terminal.get("producer_usage_complete") is not True
                    or (
                        row["method"],
                        row["dataset"],
                        row["phase"],
                        row["operation"],
                        row["provider"],
                        row["model"],
                        row["kind"],
                    )
                    != (
                        "raptor",
                        leaf_producer["dataset"],
                        "index",
                        "index_embedding",
                        "local_ollama",
                        leaf_producer["model"],
                        "embedding",
                    )
                ):
                    raise ValueError("unverified_dense_leaf_cache_hit")
                continue
            item = cache.get(key)
            if (
                not item
                or terminal["producer_run_id"] != item["run_id"]
                or any(
                    row[k] != item[k]
                    for k in ("operation", "kind", "provider", "model")
                )
            ):
                raise ValueError("unverified_inherited_cache_hit")
            continue
        checkpoint = manifest_path.parent / "requests" / f"{key}.json"
        saved = dense.read_json(checkpoint)
        if saved["request_sha256"] != key or saved["operation"] != row["operation"]:
            raise ValueError("resume_checkpoint_identity_mismatch")
        if terminal["status"] != "success":
            failures.append((row, terminal, saved))
            continue
        response = checkpoint.with_name(f"{key}.response.json")
        if terminal["usage_status"] != "complete":
            raise ValueError("resume_success_checkpoint_invalid")
        body = dense.read_json(response)
        usage = extract_usage(body, row["kind"], row["provider"])
        if any(terminal[field] != value for field, value in usage.items()):
            raise ValueError("resume_response_usage_mismatch")
        if saved["status"] != "complete":
            if (
                (allow_length and row["operation"] == "openie_triples")
                or (allow_summary_length and row["operation"] == "summary")
            ) and body["choices"][0]["finish_reason"] == "length":
                failures.append((row, terminal, saved))
                continue
            raise ValueError("resume_success_checkpoint_invalid")
        if dense.sha256_file(response) != saved["response_sha256"]:
            raise ValueError("resume_success_checkpoint_invalid")
        if key in cache:
            raise ValueError("duplicate_resume_physical_request")
        cache[key] = {
            "path": response,
            "sha256": saved["response_sha256"],
            "run_id": row["run_id"],
            "operation": row["operation"],
            "kind": row["kind"],
            "provider": row["provider"],
            "model": row["model"],
            # The response has complete usage, but the producing RUN has one unknown.
            "producer_complete": reference["summary"]["complete"]
            and reference["summary"]["historical_cache_cost_complete"],
        }
    return cache, failures, reference


def dense_index(corpus, transport, directory):
    path = directory / "vectors.npz"
    matrix = transport.embed([f"{r['title']}\n{r['text']}" for r in corpus])
    with path.open("wb") as stream:
        np.savez_compressed(
            stream, ids=np.asarray([r["id"] for r in corpus]), vectors=matrix
        )
    with np.load(path, allow_pickle=False) as saved:
        if saved["ids"].tolist() != [r["id"] for r in corpus] or not np.array_equal(
            saved["vectors"], matrix
        ):
            raise ValueError("dense_reload_mismatch")
        dense.normalize_rows(saved["vectors"])
    return {"passages": len(corpus), "dimension": 1024, "reload_model_calls": 0}


def row_usage(row):
    return row.get(
        "cumulative_accounting", row.get("token_accounting", {}).get("summary", {})
    )


def attribute_costs(rows):
    """Keep physical spending separate from standalone construction attribution."""
    for row in rows:
        usage = row_usage(row)
        row["cost_semantics"] = "Physical new cost; replay is not charged twice."
        row["standalone_cost_complete"] = bool(usage.get("complete", False)) and bool(
            usage.get("historical_cache_cost_complete", False)
        )
        row["standalone_known_subtotal"] = dict(usage.get("known_subtotal", {}))
        row["measured_run_seconds"] = row.get("seconds")
        row["attributed_construction_seconds"] = row.get(
            "cumulative_seconds", row.get("seconds")
        )
        if row["method"] != "raptor":
            continue
        producer_id = row.get("validation", {}).get("leaf_producer_run_id")
        if not producer_id:
            row["standalone_cost_complete"] = False
            continue
        producer = next(r for r in rows if r["run_id"] == producer_id)
        producer_usage = row_usage(producer)
        reused = producer_usage.get("known_subtotal", {})
        row["reused_leaf_build_cost"] = dict(reused)
        row["reused_leaf_cost_complete"] = bool(
            producer_usage.get("complete", False)
        ) and bool(producer_usage.get("historical_cache_cost_complete", False))
        row["standalone_cost_complete"] &= row["reused_leaf_cost_complete"]
        for key, value in reused.items():
            row["standalone_known_subtotal"][key] = (
                row["standalone_known_subtotal"].get(key, 0) + value
            )
        producer_seconds = producer.get("cumulative_seconds", producer.get("seconds"))
        own_seconds = row["attributed_construction_seconds"]
        row["attributed_construction_seconds"] = (
            own_seconds + producer_seconds
            if own_seconds is not None and producer_seconds is not None
            else None
        )
        row["cost_semantics"] += (
            " Standalone attribution includes Dense producer history, including failed "
            "attempts and unknowns; exclude reused cost from batch physical total. "
            "Attributed seconds are a sum of measured histories, not a measured fresh run."
        )


def failure_diagnostic(directory):
    """Publish response metadata, never private source text or generated facts."""
    journal = directory / "usage.jsonl"
    if not journal.exists():
        return {}
    finished = [r for r in read_records(journal) if r["event"] == "finished"]
    if not finished:
        return {}
    last = finished[-1]
    key = last.get("object_id")
    result = {
        "operation": last["operation"],
        "request_sha256": key,
        "usage_status": last["usage_status"],
    }
    response = directory / "requests" / f"{key}.response.json"
    if response.exists() and last["kind"] == "llm":
        body = dense.read_json(response)
        if body.get("choices"):
            choice = body["choices"][0]
            result["finish_reason"] = choice.get("finish_reason")
            result["repetition"] = triple_cycle(choice["message"].get("content") or "")
    repairs = directory / "cycle-repairs.json"
    if repairs.exists():
        result["corrective_request"] = any(
            r["revised_request_sha256"] == key
            for r in dense.read_json(repairs).values()
        )
    return result


def current_unknown_reservation(directory):
    """A saved pre-HTTP bound is a reserve, never measured usage."""
    journal = directory / "usage.jsonl"
    if not journal.exists():
        return 0
    records = read_records(journal)
    finished = {r["attempt_id"]: r for r in records if r["event"] == "finished"}
    total = 0
    for row in records:
        if row["event"] != "started":
            continue
        end = finished.get(row["attempt_id"], {})
        if end.get("cache_hit") or end.get("usage_status") == "complete":
            continue
        checkpoint = directory / "requests" / f"{row['object_id']}.json"
        bound = (
            dense.read_json(checkpoint).get("reserved_tokens")
            if checkpoint.exists()
            else None
        )
        if type(bound) is not int or bound < 0:
            return None
        total += bound
    return total


def export(plan, plan_path):
    rows = []
    for row in plan["rows"]:
        manifest = ROOT / row["output"] / "manifest.json"
        result = (
            dense.read_json(manifest) if manifest.exists() else {"status": "pending"}
        )
        public = {key: value for key, value in result.items() if key != "artifacts"}
        public["current_unknown_reserved_upper_bound"] = current_unknown_reservation(
            manifest.parent
        )
        if result["status"] == "failed":
            public["failure_diagnostic"] = failure_diagnostic(manifest.parent)
        if result["status"] == "running" and (manifest.parent / "usage.jsonl").exists():
            from scripts.token_accounting import summarize

            live = manifest.parent / "usage.jsonl"
            public["token_accounting"] = {
                "journal_sha256": dense.sha256_file(live),
                "summary": summarize(read_records(live)),
            }
        history = row.get(
            "history_runs", [row["prior_run"]] if row.get("prior_run") else []
        )
        if history:
            from scripts.token_accounting import summarize

            records, seconds = [], 0
            for prior_row in history:
                prior = ROOT / prior_row["output"] / "manifest.json"
                if dense.sha256_file(prior) != prior_row["manifest_sha256"]:
                    raise ValueError("prior_failed_manifest_changed")
                records.extend(read_records(prior.parent / "usage.jsonl"))
                seconds += dense.read_json(prior)["seconds"]
            current = manifest.parent / "usage.jsonl"
            if current.exists():
                records.extend(read_records(current))
            public["cumulative_accounting"] = summarize(records)
            public["cumulative_seconds"] = seconds + result.get("seconds", 0)
        probe_kind = (
            "summary"
            if (row["method"], row["dataset"]) == ("raptor", "hotpotqa")
            else {"hipporag2": "schema", "raptor": "embedding"}.get(row["method"])
        )
        if (
            probe_kind
            and (row["dataset"] == "musique" or probe_kind == "summary")
            and not row.get("diagnostics_in_history")
        ):
            probe_path = (
                manifest.parent.parent
                / f"{row['dataset']}-{probe_kind}-probe1/manifest.json"
            )
            if probe_path.exists():
                probe = dense.read_json(probe_path)
                if probe["parent_manifest_sha256"] != dense.sha256_file(manifest):
                    raise ValueError(f"{probe_kind}_probe_parent_manifest_changed")
                if verified_reference(probe, probe_path)["status"] != "verified":
                    raise ValueError(f"{probe_kind}_probe_journal_not_intact")
                for name, sha in probe["artifacts"].items():
                    if dense.sha256_file(probe_path.parent / name) != sha:
                        raise ValueError(f"{probe_kind}_probe_artifact_changed")
                from scripts.token_accounting import summarize

                records = []
                for prior_row in history:
                    records.extend(
                        read_records(ROOT / prior_row["output"] / "usage.jsonl")
                    )
                if (manifest.parent / "usage.jsonl").exists():
                    records.extend(read_records(manifest.parent / "usage.jsonl"))
                records.extend(read_records(probe_path.parent / "usage.jsonl"))
                public["cumulative_accounting"] = summarize(records)
                public["cumulative_seconds"] = (
                    public.get("cumulative_seconds", result.get("seconds", 0))
                    + probe["seconds"]
                )
                public[f"{probe_kind}_probe"] = {
                    k: probe[k]
                    for k in (
                        "status",
                        "run_id",
                        "unknown_reserved_upper_bound",
                        "full_index_authorized",
                        "cases",
                    )
                }
                if probe_kind == "embedding":
                    public["embedding_probe"].update(
                        {
                            k: probe[k]
                            for k in (
                                "embedding_options",
                                "producer_response_sha256",
                                "native_tokens_with_special",
                                "native_tokens_without_special",
                                "code_commit",
                                "operator_sha256",
                            )
                            if k in probe
                        }
                    )
        if manifest.exists():
            public["artifact_manifest_sha256"] = dense.sha256_file(manifest)
        exported_row = {**row, **public}
        if "cycle_repair_request_key" in exported_row:
            exported_row["cycle_repair_request_sha256"] = exported_row.pop(
                "cycle_repair_request_key"
            )
        rows.append(exported_row)
    report = {
        "batch_id": plan["batch_id"],
        "plan_sha256": dense.sha256_file(plan_path),
        "models": {
            key: plan[key] for key in ("model", "embedding_model", "embedding_digest")
        },
        "parameters": plan["parameters"],
        "raptor_clustering_policy": plan.get(
            "raptor_clustering_policy", "pinned_upstream"
        ),
        "rows": rows,
        "combined_token_limit": plan["combined_token_limit"],
        "complete": all(r["status"] == "completed" for r in rows),
        "limitations": "E1 measures indexing cost/coverage, not retrieval or answer quality. Historical smoke unknowns are preserved outside these new runs.",
    }
    report["physical_known_tokens"] = sum(
        sum(row_usage(r).get("known_subtotal", {}).values()) for r in rows
    )
    report["physical_usage_complete"] = all(
        row_usage(r).get("complete", False) for r in rows
    )
    attribute_costs(rows)
    report["cost_complete"] = all(r["standalone_cost_complete"] for r in rows)
    report["budget_charge_upper_bound"] = (
        report["physical_known_tokens"]
        + sum(
            sum(
                p.get("unknown_reserved_upper_bound", 0)
                for p in r.get(
                    "history_runs", [r["prior_run"]] if r.get("prior_run") else []
                )
            )
            for r in rows
        )
        + sum(
            r.get(f"{kind}_probe", {}).get("unknown_reserved_upper_bound", 0)
            for r in rows
            for kind in ("schema", "embedding", "summary")
        )
        + sum(r.get("current_unknown_reserved_upper_bound") or 0 for r in rows)
    )
    report["budget_reservation_complete"] = all(
        r["current_unknown_reserved_upper_bound"] is not None for r in rows
    )
    if not report["budget_reservation_complete"]:
        report["budget_charge_upper_bound"] = None
    report["original_combined_token_limit"] = plan.get(
        "original_combined_token_limit", plan["combined_token_limit"]
    )
    dense.write_json_atomic(ROOT / "results/summary/e1-indexing.json", report)
    lines = [
        "# E1: индексация",
        "",
        "| Метод | Датасет | Статус | LLM in/out | Embed | POST | Секунды | Полнота | Run ID / index |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        usage = row_usage(row)
        known = usage.get("known_subtotal", {})
        completeness = row["standalone_cost_complete"]
        lines.append(
            f"| {row['method']} | {row['dataset']} | {row['status']} | {known.get('llm_input_tokens', '—')}/{known.get('llm_output_tokens', '—')} | {known.get('embedding_input_tokens', '—')} (+cache {row.get('reused_leaf_build_cost', {}).get('embedding_input_tokens', 0)}) | {usage.get('attempts', '—')} | {row.get('cumulative_seconds', row.get('seconds', '—'))} | {completeness} | {row['run_id']} / `{row['output']}` |"
        )
    (ROOT / "results/summary/e1-indexing.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return report


def continuation_plan(prior_path):
    """One inspected local socket-failure continuation, within the original allocation.

    Original plan/failed directory stay immutable. Unknown cost is NOT measured;
    its conservative request reservation is charged against the remaining budget.
    """
    original = dense.read_json(prior_path)
    if original.get("parent_plan"):
        raise ValueError("only_one_E1_continuation_per_original_plan")
    plan = copy.deepcopy(original)
    if code_dirty():
        raise ValueError("commit_continuation_before_preparing_plan")
    candidates = []
    for row in plan["rows"]:
        path = ROOT / row["output"] / "manifest.json"
        manifest = dense.read_json(path) if path.exists() else {}
        if manifest.get("status") == "completed":
            continue
        row["code_commit"] = git("rev-parse", "HEAD")
        if manifest.get("status") == "failed":
            if row["method"] != "dense" or row["dataset"] != "hotpotqa":
                raise ValueError("continuation_scope_is_local_Dense_Hotpot_only")
            from scripts.token_accounting import verified_reference

            reference = verified_reference(manifest, path)
            if reference["status"] != "verified":
                raise ValueError("prior_journal_not_intact")
            for name, sha in manifest["artifacts"].items():
                if dense.sha256_file(path.parent / name) != sha:
                    raise ValueError("prior_artifact_changed")
            summary = reference["summary"]
            if sum(p["errors"] for p in summary["phases"]) != 1 or any(
                p["unfinished"] or p["provider"] != "local_ollama"
                for p in summary["phases"]
            ):
                raise ValueError("unexpected_prior_error_scope")
            corpus, _ = load_corpus(plan["data_root"], row["dataset"])
            unresolved = [
                dense.read_json(p)
                for p in path.parent.joinpath("requests").glob("*.json")
                if not p.name.endswith(".response.json")
                and dense.read_json(p)["status"] != "complete"
            ]
            if len(unresolved) != 1:
                raise ValueError("expected_exactly_one_socket_failure")
            saved = unresolved[0]
            response = dense.read_json(
                path.parent / "requests" / f"{saved['request_sha256']}.response.json"
            )
            error = response.get("error", "")
            if (
                "/tokenize" not in error
                or "Only one usage of each socket address" not in error
            ):
                raise ValueError("failure_is_not_inspected_local_socket_exhaustion")
            bound = None
            texts = [f"{r['title']}\n{r['text']}" for r in corpus]
            for offset in range(0, len(texts), 32):
                payload = {
                    "model": original["embedding_model"],
                    "input": texts[offset : offset + 32],
                    "truncate": False,
                }
                key = target.digest(
                    {
                        "payload": payload,
                        "kind": "embedding",
                        "operation": "index_embedding",
                    }
                )
                if key == saved["request_sha256"]:
                    bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
            if bound is None:
                raise ValueError("unknown_request_cannot_be_reconstructed")
            known = sum(reference["summary"]["known_subtotal"].values())
            row["prior_run"] = {
                "run_id": row["run_id"],
                "output": row["output"],
                "manifest_sha256": dense.sha256_file(path),
                "summary": reference["summary"],
                "unknown_reserved_upper_bound": bound,
                "reason": "Local Ollama internal /tokenize socket exhaustion; endpoint allocations recovered during inspection. Add per-text pacing, one fresh attempt, preserve unknown.",
            }
            row["prior_budget_charge"] = known + bound
            row["token_limit"] -= known + bound
            row["run_id"] = str(uuid.uuid4())
            row["output"] += "-continuation1"
            candidates.append(path.parent)
    if len(candidates) != 1:
        raise ValueError("expected_one_failed_Dense_row")
    with (candidates[0] / "continuation-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {
                "parent_plan_sha256": dense.sha256_file(prior_path),
                "new_run_id": next(
                    r["run_id"] for r in plan["rows"] if r.get("prior_run")
                ),
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan["parent_plan"] = {
        "path": str(prior_path.resolve()),
        "sha256": dense.sha256_file(prior_path),
        "digest": target.digest(original),
    }
    plan["parameters"] = PARAMETERS
    plan["combined_token_limit"] = sum(r["token_limit"] for r in plan["rows"])
    plan["original_combined_token_limit"] = original["combined_token_limit"]
    return plan


def network_resume_plan(prior_path):
    """One explicitly initiated continuation after a recorded remote disconnect."""
    original = dense.read_json(prior_path)
    if original.get("network_resume") or code_dirty():
        raise ValueError("network_resume_requires_clean_original_stage")
    plan = copy.deepcopy(original)
    lineage, cursor, cursor_path = [], original, Path(prior_path)
    while True:
        descriptor = {
            "path": str(cursor_path.resolve()),
            "sha256": dense.sha256_file(cursor_path),
            "digest": target.digest(cursor),
        }
        if descriptor["path"] in {p["path"] for p in lineage}:
            raise ValueError("plan_lineage_cycle")
        lineage.append(descriptor)
        for key in ("model", "endpoint", "embedding_model", "embedding_digest"):
            if cursor[key] != original[key]:
                raise ValueError("lineage_model_changed")
        if not cursor.get("parent_plan"):
            break
        parent = cursor["parent_plan"]
        cursor_path = Path(parent["path"])
        if dense.sha256_file(cursor_path) != parent["sha256"]:
            raise ValueError("lineage_plan_changed")
        cursor = dense.read_json(cursor_path)
        if target.digest(cursor) != parent["digest"]:
            raise ValueError("lineage_plan_digest_mismatch")
    failed = []
    for row in plan["rows"]:
        manifest_path = ROOT / row["output"] / "manifest.json"
        manifest = dense.read_json(manifest_path) if manifest_path.exists() else {}
        if manifest.get("status") == "completed":
            continue
        if manifest.get("status") not in (None, "failed"):
            raise ValueError("stage_must_be_stopped_before_network_resume")
        row["code_commit"] = git("rev-parse", "HEAD")
        if manifest.get("status") != "failed":
            continue
        if (row["method"], row["dataset"]) != ("hipporag2", "musique") or row.get(
            "prior_run"
        ):
            raise ValueError("network_resume_scope_is_first_Hippo_MuSiQue_failure")
        cache, errors, reference = verified_checkpoints(manifest_path)
        if len(errors) != 1:
            raise ValueError("network_resume_requires_one_error")
        started, finished, checkpoint = errors[0]
        if (
            started["kind"] != "llm"
            or started["provider"] != "target_api"
            or finished["error_code"] != "ConnectionError"
            or finished["usage_status"] != "unknown"
        ):
            raise ValueError("network_resume_requires_recorded_connection_error")
        bound = checkpoint.get("reserved_tokens")
        if type(bound) is not int or not 0 < bound <= PARAMETERS["target_context"]:
            raise ValueError("unknown_request_reservation_missing")
        known = sum(reference["summary"]["known_subtotal"].values())
        if known + bound >= row["token_limit"]:
            raise ValueError("no_remaining_network_resume_budget")
        row["prior_run"] = {
            "run_id": row["run_id"],
            "output": row["output"],
            "manifest_sha256": dense.sha256_file(manifest_path),
            "summary": reference["summary"],
            "unknown_reserved_upper_bound": bound,
            "reason": "Remote disconnected without response; preserve unknown, reuse verified successful responses, one bounded continuation with fresh target connections.",
        }
        row["resume_from"] = {
            key: row["prior_run"][key] for key in ("output", "manifest_sha256")
        }
        row["prior_budget_charge"] = known + bound
        row["token_limit"] -= known + bound
        row["run_id"] = str(uuid.uuid4())
        row["output"] += "-network1"
        row["verified_response_cache_count"] = len(cache)
        failed.append((manifest_path, row["run_id"]))
    if len(failed) != 1:
        raise ValueError("expected_one_failed_network_stage")
    manifest_path, child_id = failed[0]
    with (manifest_path.parent / "network-resume-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {
                "parent_plan_sha256": dense.sha256_file(prior_path),
                "child_run_id": child_id,
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan.update(
        parent_plan=lineage[0],
        lineage=lineage,
        network_resume=True,
        parameters=PARAMETERS,
        combined_token_limit=sum(r["token_limit"] for r in plan["rows"]),
        original_combined_token_limit=original.get(
            "original_combined_token_limit", original["combined_token_limit"]
        ),
    )
    return plan


def cycle_resume_plan(prior_path, passage_id):
    """Keep known cost and every ancestor; probe a single bounded cycle repair."""
    original = dense.read_json(prior_path)
    if (
        original.get("cycle_repair")
        or not original.get("network_resume")
        or code_dirty()
    ):
        raise ValueError("cycle_resume_requires_clean_network_stage")
    plan = copy.deepcopy(original)
    lineage = [
        {
            "path": str(prior_path.resolve()),
            "sha256": dense.sha256_file(prior_path),
            "digest": target.digest(original),
        },
        *original["lineage"],
    ]
    for ancestor in lineage:
        if dense.sha256_file(Path(ancestor["path"])) != ancestor["sha256"]:
            raise ValueError("cycle_ancestor_plan_changed")
    failed = []
    for row in plan["rows"]:
        path = ROOT / row["output"] / "manifest.json"
        manifest = dense.read_json(path) if path.exists() else {}
        if manifest.get("status") == "completed":
            continue
        if manifest.get("status") not in (None, "failed"):
            raise ValueError("cycle_stage_is_not_stopped")
        row["code_commit"] = git("rev-parse", "HEAD")
        if manifest.get("status") != "failed":
            continue
        if (row["method"], row["dataset"]) != ("hipporag2", "musique") or not row.get(
            "resume_from"
        ):
            raise ValueError("cycle_resume_scope_is_Hippo_MuSiQue")
        sources = [row["resume_from"]]
        cache = {}
        for source in sources:
            parent = ROOT / source["output"] / "manifest.json"
            if dense.sha256_file(parent) != source["manifest_sha256"]:
                raise ValueError("cycle_source_manifest_changed")
            cache, _, _ = verified_checkpoints(parent, inherited=cache)
        cache, unusable, reference = verified_checkpoints(
            path, inherited=cache, allow_length=True
        )
        if len(unusable) != 1:
            raise ValueError("cycle_resume_requires_one_incomplete_response")
        started, terminal, _ = unusable[0]
        body = dense.read_json(
            path.parent / "requests" / f"{started['object_id']}.response.json"
        )
        diagnostic = triple_cycle(body["choices"][0]["message"]["content"])
        if (
            started["operation"] != "openie_triples"
            or terminal["usage_status"] != "complete"
            or not diagnostic["cycle"]
        ):
            raise ValueError("cycle_resume_requires_known_usage_repeated_triples")
        corpus, _ = load_corpus(plan["data_root"], row["dataset"])
        if passage_id not in {r["id"] for r in corpus}:
            raise ValueError("cycle_probe_source_missing")
        known = sum(reference["summary"]["known_subtotal"].values())
        if known >= row["token_limit"]:
            raise ValueError("cycle_budget_exhausted")
        latest = {
            "run_id": row["run_id"],
            "output": row["output"],
            "manifest_sha256": dense.sha256_file(path),
            "summary": reference["summary"],
            "unknown_reserved_upper_bound": 0,
            "reason": "Known-cost length response repeats three triples; no partial acceptance.",
        }
        row["history_runs"] = [row["prior_run"], latest]
        row["prior_run"] = latest
        row["resume_from"] = {key: latest[key] for key in ("output", "manifest_sha256")}
        row["resume_sources"] = [*sources, row["resume_from"]]
        row["prior_budget_charge"] += known
        row["token_limit"] -= known
        row["run_id"] = str(uuid.uuid4())
        row["output"] = f"indexes/e1/{plan['batch_id']}/hipporag2/musique-cycle1"
        row.update(
            resume_kind="cycle",
            cycle_repair_request_key=started["object_id"],
            cycle_probe_source_id=passage_id,
            cycle_diagnostic=diagnostic,
            verified_response_cache_count=len(cache),
        )
        failed.append((path, row["run_id"]))
    if len(failed) != 1:
        raise ValueError("cycle_requires_one_failed_stage")
    path, child = failed[0]
    with (path.parent / "cycle-resume-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {
                "parent_plan_sha256": dense.sha256_file(prior_path),
                "child_run_id": child,
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan.update(
        parent_plan=lineage[0],
        lineage=lineage,
        cycle_repair=CYCLE_REPAIR,
        parameters=PARAMETERS,
        combined_token_limit=sum(r["token_limit"] for r in plan["rows"]),
    )
    return plan


def prepare_schema_probe(prior_path, source):
    """Reconstruct the two historical requests offline; never send or authorize HTTP."""
    from scripts.preflight_hipporag_repair_prompts import (
        verify_target_prompt_installation,
    )

    plan = dense.read_json(prior_path)
    workspace = Path(plan["workspace"])
    for item in plan.get("lineage", []):
        if dense.sha256_file(Path(item["path"])) != item["sha256"]:
            raise ValueError("lineage_plan_changed")
    row = next(
        r
        for r in plan["rows"]
        if (r["method"], r["dataset"]) == ("hipporag2", "musique")
    )
    directory = workspace / row["output"]
    manifest_path = directory / "manifest.json"
    manifest = dense.read_json(manifest_path)
    if manifest["status"] != "failed" or (directory / "running.lock").exists():
        raise ValueError("schema_probe_requires_stopped_cycle_run")
    cache, failures = {}, {}
    sources = [
        *row["resume_sources"],
        {"output": row["output"], "manifest_sha256": dense.sha256_file(manifest_path)},
    ]
    for entry in sources:
        path = workspace / entry["output"] / "manifest.json"
        if dense.sha256_file(path) != entry["manifest_sha256"]:
            raise ValueError("schema_probe_source_manifest_changed")
        cache, rejected, reference = verified_checkpoints(
            path, inherited=cache, allow_length=True
        )
        failures.update({r[0]["object_id"]: (path, *r) for r in rejected})
    repairs = dense.read_json(directory / "cycle-repairs.json")
    if len(repairs) != 2:
        raise ValueError("schema_probe_requires_exactly_two_cases")
    manager_type, verified_files = verify_target_prompt_installation(source)
    manager = manager_type(
        role_mapping={"system": "system", "user": "user", "assistant": "assistant"}
    )
    corpus, provenance = load_corpus(plan["data_root"], row["dataset"])
    if (
        provenance != row["corpus"]
        or dense.corpus_fingerprint(corpus) != row["corpus_fingerprint"]
    ):
        raise ValueError("schema_probe_corpus_changed")
    cases = {}
    for document in corpus:
        passage = f"{document['title']}\n{document['text']}"
        ner_payload = {
            **target.OPTIONS,
            "model": plan["model"],
            "messages": manager.render(name="ner", passage=passage),
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }
        ner_key = target.digest(
            {"payload": ner_payload, "kind": "llm", "operation": "openie_ner"}
        )
        if ner_key not in cache:
            continue
        ner_body = dense.read_json(cache[ner_key]["path"])
        entities = json.loads(ner_body["choices"][0]["message"]["content"])[
            "named_entities"
        ]
        if not isinstance(entities, list) or not all(
            isinstance(x, str) and x.strip() for x in entities
        ):
            raise ValueError("schema_probe_invalid_verified_ner")
        original = {
            **target.OPTIONS,
            "model": plan["model"],
            "messages": manager.render(
                name="triple_extraction",
                passage=passage,
                named_entity_json=json.dumps({"named_entities": entities}),
            ),
            "max_tokens": 3072,
            "response_format": {"type": "json_object"},
        }
        key = target.digest(
            {"payload": original, "kind": "llm", "operation": "openie_triples"}
        )
        if key not in repairs:
            continue
        if key in cases or key not in failures:
            raise ValueError("schema_probe_ambiguous_original_request")
        path, started, terminal, _ = failures[key]
        old_body = dense.read_json(path.parent / "requests" / f"{key}.response.json")
        if (
            terminal["usage_status"] != "complete"
            or old_body["choices"][0]["finish_reason"] != "length"
            or not triple_cycle(old_body["choices"][0]["message"]["content"])["cycle"]
        ):
            raise ValueError("schema_probe_requires_verified_known_cycle")
        payload, reserve = schema_probe_payload(original)
        cases[key] = {
            "source_id": document["id"],
            "original_request_sha256": started["object_id"],
            "ner_response_sha256": cache[ner_key]["sha256"],
            "ner_producer_run_id": cache[ner_key]["run_id"],
            "payload": payload,
            "request_sha256": target.digest(
                {"payload": payload, "kind": "llm", "operation": "openie_triples"}
            ),
            "reserved_tokens_upper_bound": reserve,
        }
    if set(cases) != set(repairs):
        raise ValueError("schema_probe_original_payload_sha_not_reconstructed")
    own_known = sum(reference["summary"]["known_subtotal"].values())
    remaining = row["token_limit"] - own_known
    reserve = sum(c["reserved_tokens_upper_bound"] for c in cases.values())
    if reserve > remaining:
        raise ValueError("schema_probe_budget_reservation_exceeded")
    return {
        "status": "prepared_offline_requires_approval",
        "max_new_posts": 2,
        "retry": 0,
        "stop_on_first_failure": True,
        "ner_posts": 0,
        "output_cap": 3072,
        "parent_plan_sha256": dense.sha256_file(prior_path),
        "failed_manifest_sha256": dense.sha256_file(manifest_path),
        "verified_sdk_files": verified_files,
        "remaining_hippo_budget_before_probe": remaining,
        "reserved_tokens_upper_bound": reserve,
        "server_usage_known": False,
        "unique_items_server_enforcement": "unverified",
        "cases": list(cases.values()),
    }


def execute_schema_probe(probe_path, prior_path, source, config, approved_sha256):
    """Two approved POSTs at most; a canonical claim survives failure or a crash."""
    if dense.sha256_file(probe_path) != approved_sha256 or code_dirty():
        raise ValueError("schema_probe_requires_approved_sha_and_clean_code")
    plan = dense.read_json(prior_path)
    if Path(plan["workspace"]).resolve() != ROOT.resolve():
        raise ValueError("schema_probe_requires_integrated_live_checkout")
    for row in plan["rows"]:
        directory = ROOT / row["output"]
        manifest = directory / "manifest.json"
        if (directory / "running.lock").exists() or (
            manifest.exists() and dense.read_json(manifest)["status"] == "running"
        ):
            raise ValueError("schema_probe_wait_for_index_workers")
    if (
        config.get("TARGET_API_MODEL") != plan["model"]
        or config.get("TARGET_API_BASE_URL", "").rstrip("/") != plan["endpoint"]
        or not config.get("LITELLM_API_KEY")
    ):
        raise ValueError("schema_probe_target_config_mismatch")
    prepared = dense.read_json(probe_path)
    if len(prepared.get("cases", [])) != 2 or prepared.get("max_new_posts") != 2:
        raise ValueError("schema_probe_requires_two_cases")
    if prepared != prepare_schema_probe(prior_path, source):
        raise ValueError("schema_probe_prepared_inputs_changed")
    row = next(
        r
        for r in plan["rows"]
        if (r["method"], r["dataset"]) == ("hipporag2", "musique")
    )
    prior = ROOT / row["output"]
    directory = prior.parent / "musique-schema-probe1"
    if directory.exists():
        raise ValueError("schema_probe_output_already_exists")
    run_id = str(uuid.uuid4())
    with (prior / "schema-probe-once.claim.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "approved_plan_sha256": approved_sha256,
                "run_id": run_id,
                "code_commit": git("rev-parse", "HEAD"),
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    directory.mkdir()
    requests_dir = directory / "requests"
    requests_dir.mkdir()
    journal = Journal(
        directory / "usage.jsonl", run_id=run_id, method="hipporag2", dataset="musique"
    )
    result = {
        "status": "running",
        "run_id": run_id,
        "approved_plan_sha256": approved_sha256,
        "parent_manifest_sha256": prepared["failed_manifest_sha256"],
        "max_new_posts": 2,
        "reserved_tokens_upper_bound": prepared["reserved_tokens_upper_bound"],
        "cases": [],
        "unique_items_server_enforcement": "unverified",
        "full_index_authorized": False,
    }
    dense.write_json_atomic(directory / "manifest.json", result)
    started = time.perf_counter()
    session = requests.Session()
    try:
        if any(a.max_retries.total for a in session.adapters.values()):
            raise ValueError("transport_retry_must_be_zero")
        for case in prepared["cases"]:
            body = target.checked_post(
                session,
                plan["endpoint"] + "/chat/completions",
                case["payload"],
                journal,
                phase="index",
                operation="openie_triples",
                provider="target_api",
                model=plan["model"],
                kind="llm",
                object_id=case["request_sha256"],
                headers={
                    "Authorization": f"Bearer {config['LITELLM_API_KEY']}",
                    "Connection": "close",
                },
                response_path=requests_dir / f"{case['request_sha256']}.response.json",
                token_limit=prepared["reserved_tokens_upper_bound"],
                timeout=(5, 300),
            )
            triples = validate_schema_probe_response(body)
            result["cases"].append(
                {
                    "source_id": case["source_id"],
                    "request_sha256": case["request_sha256"],
                    "triples": len(triples),
                    "format_status": "passed",
                    "semantic_support": "not_reviewed",
                }
            )
        result["status"] = "completed"
    except BaseException as exc:
        result.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        result["seconds"] = round(time.perf_counter() - started, 3)
        result["token_accounting"] = journal.reference()
        records = read_records(journal.path)
        finished = {r["attempt_id"]: r for r in records if r["event"] == "finished"}
        reserves = {
            c["request_sha256"]: c["reserved_tokens_upper_bound"]
            for c in prepared["cases"]
        }
        result["unknown_reserved_upper_bound"] = sum(
            reserves[r["object_id"]]
            for r in records
            if r["event"] == "started"
            and finished.get(r["attempt_id"], {}).get("usage_status") != "complete"
        )
        result["artifacts"] = {
            p.relative_to(directory).as_posix(): dense.sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        }
        dense.write_json_atomic(directory / "manifest.json", result)
        session.close()
    return directory


def raptor_batch_plan(prior_path):
    """Reserve one inspected continuation and the untouched second RAPTOR row."""
    original = dense.read_json(prior_path)
    if (
        code_dirty()
        or not original.get("independent_raptor")
        or original.get("raptor_batch_resume")
        or original.get("workspace") != str(ROOT.resolve())
    ):
        raise ValueError("raptor_batch_requires_clean_independent_prior")
    parent = {
        "path": str(prior_path.resolve()),
        "sha256": dense.sha256_file(prior_path),
        "digest": target.digest(original),
    }
    plan = copy.deepcopy(original)
    plan.update(
        parent_plan=parent,
        lineage=[parent, *original.get("lineage", [])],
        raptor_batch_resume=True,
    )
    for item in plan["lineage"]:
        if dense.sha256_file(Path(item["path"])) != item["sha256"]:
            raise ValueError("lineage_plan_changed")
    inspected = []
    for row in plan["rows"]:
        directory = ROOT / row["output"]
        path = directory / "manifest.json"
        if (directory / "running.lock").exists() or (
            path.exists() and dense.read_json(path)["status"] == "running"
        ):
            raise ValueError("raptor_batch_requires_stopped_workers")
        if row["method"] != "raptor":
            continue
        # Validate the exact Dense vectors used for all leaf cache hits.
        leaf_scope = verified_raptor_leaf_scope(plan, row)
        row["code_commit"] = git("rev-parse", "HEAD")
        row["embedding_options"] = dict(RAPTOR_EMBEDDING_OPTIONS)
        if row["dataset"] == "hotpotqa":
            if directory.exists() and any(directory.iterdir()):
                raise ValueError("raptor_hotpot_must_be_untouched")
            continue
        manifest = dense.read_json(path)
        if manifest["status"] != "failed" or row.get("history_runs"):
            raise ValueError("raptor_batch_requires_original_failed_run")
        cache, failures, reference = verified_checkpoints(
            path, leaf_producer=leaf_scope
        )
        if (
            len(failures) != 1
            or failures[0][0]["kind"] != "embedding"
            or failures[0][1]["usage_status"] != "unknown"
        ):
            raise ValueError("raptor_batch_requires_one_unknown_embedding")
        bound = current_unknown_reservation(directory)
        if type(bound) is not int or bound <= 0:
            raise ValueError("raptor_batch_requires_saved_unknown_reserve")
        probe_path = directory.parent / "musique-embedding-probe1/manifest.json"
        probe = dense.read_json(probe_path)
        if (
            probe["status"] != "completed"
            or probe["parent_manifest_sha256"] != dense.sha256_file(path)
            or probe.get("embedding_options") != RAPTOR_EMBEDDING_OPTIONS
            or probe.get("full_index_authorized") is not False
        ):
            raise ValueError("raptor_batch_requires_successful_exact_probe")
        cache, probe_errors, probe_reference = verified_checkpoints(
            probe_path, inherited=cache, leaf_producer=leaf_scope
        )
        if (
            probe_errors
            or not probe_reference["summary"]["complete"]
            or probe_reference["summary"]["attempts"] != 1
        ):
            raise ValueError("raptor_batch_probe_cost_not_complete")
        repaired = []
        for item in cache.values():
            if item["operation"] != "summary" or item["kind"] != "llm":
                continue
            text = dense.read_json(item["path"])["choices"][0]["message"]["content"]
            payload = {
                "model": plan["embedding_model"],
                "input": [text],
                "truncate": False,
            }
            old_key = target.digest(
                {
                    "payload": payload,
                    "kind": "embedding",
                    "operation": "index_embedding",
                }
            )
            if old_key != failures[0][0]["object_id"]:
                continue
            payload["options"] = dict(RAPTOR_EMBEDDING_OPTIONS)
            new_key = target.digest(
                {
                    "payload": payload,
                    "kind": "embedding",
                    "operation": "index_embedding",
                }
            )
            if new_key not in cache or cache[new_key]["run_id"] != probe["run_id"]:
                raise ValueError("raptor_batch_probe_does_not_repair_failed_input")
            repaired.append(new_key)
        if len(repaired) != 1:
            raise ValueError("raptor_batch_failed_input_not_reconstructed")
        history = []
        for source_path, source_manifest, ref, reserved in [
            (path, manifest, reference, bound),
            (probe_path, probe, probe_reference, 0),
        ]:
            history.append(
                {
                    "output": source_path.parent.relative_to(ROOT).as_posix(),
                    "run_id": source_manifest["run_id"],
                    "manifest_sha256": dense.sha256_file(source_path),
                    "summary": ref["summary"],
                    "unknown_reserved_upper_bound": reserved,
                }
            )
        charge = sum(
            sum(h["summary"]["known_subtotal"].values())
            + h["unknown_reserved_upper_bound"]
            for h in history
        )
        if charge >= row["token_limit"]:
            raise ValueError("raptor_batch_budget_exhausted")
        row.update(
            history_runs=history,
            prior_run=history[-1],
            resume_sources=[
                {k: h[k] for k in ("output", "manifest_sha256")} for h in history
            ],
            diagnostics_in_history=True,
            resume_kind="embedding_batch",
            prior_budget_charge=charge,
            token_limit=row["token_limit"] - charge,
            run_id=str(uuid.uuid4()),
            output=row["output"] + "-batch1",
            verified_response_cache_count=len(cache),
        )
        row["resume_from"] = row["resume_sources"][-1]
        if (ROOT / row["output"]).exists():
            raise ValueError("raptor_batch_output_must_be_new")
        inspected.append((directory, row["run_id"]))
    if len(inspected) != 1:
        raise ValueError("raptor_batch_requires_one_failed_stage")
    directory, child = inspected[0]
    with (directory / "embedding-resume-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {"parent_plan_sha256": parent["sha256"], "child_run_id": child}, stream
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan["combined_token_limit"] = sum(r["token_limit"] for r in plan["rows"])
    return plan


SUMMARY_PROBE_POLICY = {
    "version": "raptor_summary_300_words_v1",
    "max_words": 300,
    "max_output_tokens": 1536,
    "max_utf8_bytes": 4000,
}


def summary_probe_payload(original):
    """Keep the original context intact; constrain only the diagnostic summary."""
    messages = original.get("messages", [])
    if (
        len(messages) != 2
        or messages[0] != {"role": "system", "content": "You are a helpful assistant."}
        or messages[1].get("role") != "user"
        or not isinstance(messages[1].get("content"), str)
        or not messages[1]["content"].startswith("Write a summary of the following,")
        or original
        != {
            **target.OPTIONS,
            "model": original.get("model"),
            "messages": messages,
            "max_tokens": PARAMETERS["summary_max_tokens"],
        }
    ):
        raise ValueError("summary_probe_original_payload_invalid")
    payload = copy.deepcopy(original)
    payload["max_tokens"] = SUMMARY_PROBE_POLICY["max_output_tokens"]
    payload["messages"][0]["content"] += (
        " Summarize in at most 300 words of compact prose. Preserve the key entities"
        " and relationships supported by the supplied text. Do not expand into"
        " catalogs, repeat facts, or add facts. End the summary within this limit."
    )
    return payload


def validate_summary_probe(body):
    choice = body["choices"][0]
    text = choice["message"]["content"]
    usage = extract_usage(body, "llm", "target_api")
    if (
        choice["finish_reason"] != "stop"
        or type(usage["llm_input_tokens"]) is not int
        or type(usage["llm_output_tokens"]) is not int
        or not 0
        <= usage["llm_output_tokens"]
        <= SUMMARY_PROBE_POLICY["max_output_tokens"]
        or not isinstance(text, str)
        or not text.strip()
        or len(text.split()) > SUMMARY_PROBE_POLICY["max_words"]
        or len(text.encode("utf-8")) > SUMMARY_PROBE_POLICY["max_utf8_bytes"]
    ):
        raise ValueError("summary_probe_output_not_compact_complete_text")
    return {
        "words": len(text.split()),
        "utf8_bytes": len(text.encode("utf-8")),
        "semantic_support": "not_reviewed",
    }


def prepare_summary_probe(prior_path, recovered_path):
    """Verify one length failure and prepare one POST; never reuse partial text."""
    plan = dense.read_json(prior_path)
    if code_dirty() or plan.get("workspace") != str(ROOT.resolve()):
        raise ValueError("summary_probe_requires_clean_live_checkout")
    for item in plan["rows"]:
        folder = ROOT / item["output"]
        mp = folder / "manifest.json"
        if (folder / "running.lock").exists() or (
            mp.exists() and dense.read_json(mp)["status"] == "running"
        ):
            raise ValueError("summary_probe_requires_stopped_workers")
    row = next(
        r for r in plan["rows"] if (r["method"], r["dataset"]) == ("raptor", "hotpotqa")
    )
    folder = ROOT / row["output"]
    mp = folder / "manifest.json"
    manifest = dense.read_json(mp)
    if manifest["status"] != "failed" or row.get("history_runs"):
        raise ValueError("summary_probe_requires_first_failed_hotpot_run")
    _, failures, reference = verified_checkpoints(
        mp,
        allow_summary_length=True,
        leaf_producer=verified_raptor_leaf_scope(plan, row),
    )
    if len(failures) != 1 or not reference["summary"]["complete"]:
        raise ValueError("summary_probe_requires_one_length_and_complete_usage")
    failed, terminal, _ = failures[0]
    original = dense.read_json(recovered_path)
    if (
        failed["operation"] != "summary"
        or terminal["status"] != "success"
        or original.get("model") != plan["model"]
        or target.digest({"payload": original, "kind": "llm", "operation": "summary"})
        != failed["object_id"]
    ):
        raise ValueError("summary_probe_recovered_payload_mismatch")
    payload = summary_probe_payload(original)
    reserve = (
        len(json.dumps(payload, ensure_ascii=False).encode())
        + 2048
        + payload["max_tokens"]
    )
    known = sum(reference["summary"]["known_subtotal"].values())
    if (
        type(row["token_limit"]) is not int
        or not 0 < row["token_limit"] <= LIMITS["raptor"]
    ):
        raise ValueError("summary_probe_invalid_prior_budget")
    remaining = row["token_limit"] - known
    if reserve > remaining or reserve > PARAMETERS["target_context"]:
        raise ValueError("summary_probe_budget_or_context_exceeded")
    return {
        "kind": "E1_raptor_summary_diagnostic",
        "workspace": str(ROOT.resolve()),
        "code_commit": git("rev-parse", "HEAD"),
        "policy": SUMMARY_PROBE_POLICY,
        "prior_plan": {
            "path": str(prior_path.resolve()),
            "sha256": dense.sha256_file(prior_path),
        },
        "recovered_payload": {
            "path": str(recovered_path.resolve()),
            "sha256": dense.sha256_file(recovered_path),
        },
        "parent_manifest_sha256": dense.sha256_file(mp),
        "original_request_sha256": failed["object_id"],
        "payload": payload,
        "request_sha256": target.digest(
            {"payload": payload, "kind": "llm", "operation": "summary"}
        ),
        "remaining_before_probe": remaining,
        "reserved_tokens_upper_bound": reserve,
        "max_new_posts": 1,
        "full_index_authorized": False,
    }


def execute_summary_probe(probe_path, config, approved_sha256):
    if dense.sha256_file(probe_path) != approved_sha256:
        raise ValueError("summary_probe_requires_exact_approved_sha")
    prepared = dense.read_json(probe_path)
    prior_path = Path(prepared["prior_plan"]["path"])
    recovered = Path(prepared["recovered_payload"]["path"])
    if prepared != prepare_summary_probe(prior_path, recovered):
        raise ValueError("summary_probe_prepared_inputs_changed")
    plan = dense.read_json(prior_path)
    if (
        config.get("TARGET_API_MODEL") != plan["model"]
        or config.get("TARGET_API_BASE_URL", "").rstrip("/") != plan["endpoint"]
        or not config.get("LITELLM_API_KEY")
    ):
        raise ValueError("summary_probe_target_config_mismatch")
    parent_row = next(
        r for r in plan["rows"] if (r["method"], r["dataset"]) == ("raptor", "hotpotqa")
    )
    parent = ROOT / parent_row["output"]
    directory = parent.parent / "hotpotqa-summary-probe1"
    if directory.exists():
        raise ValueError("summary_probe_output_exists")
    run_id = str(uuid.uuid4())
    with (parent / "summary-probe-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump({"approved_plan_sha256": approved_sha256, "run_id": run_id}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    directory.mkdir()
    journal = Journal(
        directory / "usage.jsonl", run_id=run_id, method="raptor", dataset="hotpotqa"
    )
    row = {
        "method": "raptor",
        "dataset": "hotpotqa",
        "run_id": run_id,
        "token_limit": prepared["reserved_tokens_upper_bound"],
    }
    runner = Transport(plan, row, config, directory, journal)
    result = {
        "status": "running",
        "run_id": run_id,
        "code_commit": prepared["code_commit"],
        "parent_manifest_sha256": prepared["parent_manifest_sha256"],
        "approved_plan_sha256": approved_sha256,
        "max_new_posts": 1,
        "reserved_tokens_upper_bound": prepared["reserved_tokens_upper_bound"],
        "policy": SUMMARY_PROBE_POLICY,
        "full_index_authorized": False,
        "cases": [],
    }
    started = time.perf_counter()
    dense.write_json_atomic(directory / "manifest.json", result)
    try:
        body = runner.call(prepared["payload"], kind="llm", operation="summary")
        stats = validate_summary_probe(body)
        result["cases"] = [{"request_sha256": prepared["request_sha256"], **stats}]
        result["status"] = "completed"
    except BaseException as exc:
        result.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        result["seconds"] = round(time.perf_counter() - started, 3)
        result["token_accounting"] = journal.reference()
        result["unknown_reserved_upper_bound"] = (
            0
            if journal.summary()["complete"]
            else prepared["reserved_tokens_upper_bound"]
        )
        result["artifacts"] = {
            p.relative_to(directory).as_posix(): dense.sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        }
        dense.write_json_atomic(directory / "manifest.json", result)
        runner.session.close()
        export(plan, prior_path)
    return directory


def raptor_clustering_plan(prior_path):
    """One new RAPTOR continuation after a fully accounted local clustering failure."""
    original = dense.read_json(prior_path)
    if (
        code_dirty()
        or not original.get("raptor_batch_resume")
        or original.get("raptor_clustering_resume")
        or original.get("workspace") != str(ROOT.resolve())
    ):
        raise ValueError("clustering_resume_requires_clean_batch_prior")
    parent = {
        "path": str(prior_path.resolve()),
        "sha256": dense.sha256_file(prior_path),
        "digest": target.digest(original),
    }
    plan = copy.deepcopy(original)
    plan.update(
        parent_plan=parent,
        lineage=[parent, *original.get("lineage", [])],
        raptor_clustering_resume=True,
        raptor_clustering_policy=RAPTOR_CLUSTERING_POLICY,
    )
    for item in plan["lineage"]:
        if dense.sha256_file(Path(item["path"])) != item["sha256"]:
            raise ValueError("lineage_plan_changed")
    inspected = []
    for row in plan["rows"]:
        directory = ROOT / row["output"]
        path = directory / "manifest.json"
        if (directory / "running.lock").exists() or (
            path.exists() and dense.read_json(path)["status"] == "running"
        ):
            raise ValueError("clustering_resume_requires_stopped_workers")
        if row["method"] != "raptor":
            continue
        leaf_scope = verified_raptor_leaf_scope(plan, row)
        row["code_commit"] = git("rev-parse", "HEAD")
        if row.get("embedding_options") != RAPTOR_EMBEDDING_OPTIONS:
            raise ValueError("clustering_resume_embedding_options_changed")
        if row["dataset"] == "hotpotqa":
            if directory.exists() and any(directory.iterdir()):
                raise ValueError("raptor_hotpot_must_be_untouched")
            continue
        manifest = dense.read_json(path)
        if (
            row.get("resume_kind") != "embedding_batch"
            or manifest["status"] != "failed"
            or manifest.get("error_type") != "ValueError"
            or (directory / "tree.json").exists()
        ):
            raise ValueError("clustering_resume_requires_failed_batch")
        cache = {}
        for source in row["resume_sources"]:
            source_path = ROOT / source["output"] / "manifest.json"
            if dense.sha256_file(source_path) != source["manifest_sha256"]:
                raise ValueError("resume_manifest_changed")
            cache, _, _ = verified_checkpoints(
                source_path, inherited=cache, leaf_producer=leaf_scope
            )
        cache, failures, ref = verified_checkpoints(
            path, inherited=cache, leaf_producer=leaf_scope
        )
        if failures or not ref["summary"]["complete"]:
            raise ValueError("clustering_resume_requires_complete_current_usage")
        current = {
            "output": row["output"],
            "run_id": manifest["run_id"],
            "manifest_sha256": dense.sha256_file(path),
            "summary": ref["summary"],
            "unknown_reserved_upper_bound": 0,
        }
        history = [*row["history_runs"], current]
        # Reverify all historical manifests and their saved reservations too.
        for h in history:
            hp = ROOT / h["output"] / "manifest.json"
            if dense.sha256_file(hp) != h["manifest_sha256"]:
                raise ValueError("clustering_history_manifest_changed")
            actual = verified_reference(dense.read_json(hp), hp)
            reserved = current_unknown_reservation(hp.parent)
            if (
                actual["status"] != "verified"
                or actual["summary"] != h["summary"]
                or type(reserved) is not int
                or reserved != h["unknown_reserved_upper_bound"]
            ):
                raise ValueError("clustering_history_cost_changed")
        charge = sum(
            sum(h["summary"]["known_subtotal"].values())
            + h["unknown_reserved_upper_bound"]
            for h in history
        )
        if charge >= LIMITS["raptor"]:
            raise ValueError("clustering_resume_budget_exhausted")
        row.update(
            history_runs=history,
            prior_run=current,
            resume_sources=[
                *row["resume_sources"],
                {k: current[k] for k in ("output", "manifest_sha256")},
            ],
            resume_from={k: current[k] for k in ("output", "manifest_sha256")},
            resume_kind="clustering",
            prior_budget_charge=charge,
            token_limit=LIMITS["raptor"] - charge,
            run_id=str(uuid.uuid4()),
            output=f"indexes/e1/{plan['batch_id']}/raptor/musique-cluster1",
            verified_response_cache_count=len(cache),
        )
        if (ROOT / row["output"]).exists():
            raise ValueError("clustering_resume_output_must_be_new")
        inspected.append((directory, row["run_id"]))
    if len(inspected) != 1:
        raise ValueError("clustering_resume_requires_one_failed_stage")
    directory, child = inspected[0]
    with (directory / "clustering-resume-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {"parent_plan_sha256": parent["sha256"], "child_run_id": child}, stream
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan["combined_token_limit"] = sum(r["token_limit"] for r in plan["rows"])
    return plan


def independent_raptor_plan(prior_path):
    """Freeze stopped HippoRAG; bind only untouched RAPTOR rows to new code."""
    if code_dirty():
        raise ValueError("independent_raptor_requires_clean_code")
    original = dense.read_json(prior_path)
    plan = copy.deepcopy(original)
    parent = {
        "path": str(prior_path.resolve()),
        "sha256": dense.sha256_file(prior_path),
        "digest": target.digest(original),
    }
    lineage = [parent, *original.get("lineage", [])]
    for item in lineage:
        if dense.sha256_file(Path(item["path"])) != item["sha256"]:
            raise ValueError("lineage_plan_changed")
    stopped, pending = False, 0
    for row in plan["rows"]:
        directory = ROOT / row["output"]
        path = directory / "manifest.json"
        if (directory / "running.lock").exists():
            raise ValueError("independent_raptor_requires_stopped_workers")
        if path.exists():
            manifest = dense.read_json(path)
            if manifest["status"] not in ("completed", "failed"):
                raise ValueError("independent_raptor_requires_terminal_runs")
            if verified_reference(manifest, path)["status"] != "verified":
                raise ValueError("prior_journal_not_intact")
            for name, sha in manifest["artifacts"].items():
                if dense.sha256_file(directory / name) != sha:
                    raise ValueError("saved_E1_artifact_changed")
            stopped |= row["method"] == "hipporag2" and manifest["status"] == "failed"
        if row["method"] != "raptor":
            continue
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("independent_raptor_requires_untouched_output")
        producer = next(
            r
            for r in plan["rows"]
            if r["method"] == "dense" and r["dataset"] == row["dataset"]
        )
        if (
            dense.read_json(ROOT / producer["output"] / "manifest.json")["status"]
            != "completed"
        ):
            raise ValueError("raptor_requires_completed_dense")
        row["code_commit"] = git("rev-parse", "HEAD")
        pending += 1
    if not stopped or pending != 2:
        raise ValueError(
            "independent_raptor_requires_failed_hippo_and_two_pending_rows"
        )
    # Shared canonical prior: two worktrees cannot independently reserve this block.
    with prior_path.with_suffix(".raptor-once.claim.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {
                "parent_plan_sha256": parent["sha256"],
                "code_commit": git("rev-parse", "HEAD"),
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    plan.update(parent_plan=parent, lineage=lineage, independent_raptor=True)
    return plan


def seal_unstarted_plan(path):
    """Rebind a rejected preflight to clean code before any new HTTP."""
    plan = dense.read_json(path)
    if not plan.get("parent_plan") or code_dirty():
        raise ValueError("only_clean_unstarted_continuation_can_be_sealed")
    original = dense.read_json(Path(plan["parent_plan"]["path"]))
    for row in plan["rows"]:
        directory = ROOT / row["output"]
        manifest = directory / "manifest.json"
        original_row = next(
            r
            for r in original["rows"]
            if (r["method"], r["dataset"]) == (row["method"], row["dataset"])
        )
        if (
            row["code_commit"] == original_row["code_commit"]
            and manifest.exists()
            and dense.read_json(manifest)["status"] == "completed"
        ):
            continue
        if (directory / "usage.jsonl").exists() or (
            directory / "running.lock"
        ).exists():
            raise ValueError("cannot_change_started_plan")
        row["code_commit"] = git("rev-parse", "HEAD")
    old_sha = dense.sha256_file(path)
    backup = path.with_name(f"{path.stem}.preflight-{old_sha[:12]}.json")
    with backup.open("xb") as stream:
        stream.write(path.read_bytes())
    plan.setdefault("preflight_revisions", []).append(
        {
            "sha256": old_sha,
            "file": backup.name,
            "reason": "Rejected before new HTTP; fix Path type in parent-plan verification.",
        }
    )
    dense.write_json_atomic(path, plan)
    return plan


def execute(plan, row, config, source=None):
    corpus = verify_plan(plan, row, config)
    directory = ROOT / row["output"]
    directory.mkdir(parents=True, exist_ok=True)
    with exclusive(directory):
        path = directory / "manifest.json"
        manifest = (
            dense.read_json(path)
            if path.exists()
            else {"status": "pending", "seconds": 0}
        )
        if path.exists():
            for name, sha in manifest.get("artifacts", {}).items():
                if dense.sha256_file(directory / name) != sha:
                    raise ValueError("saved_E1_artifact_changed")
        if manifest["status"] in ("failed", "completed"):
            raise ValueError("terminal_run_cannot_repeat")
        journal_path = directory / "usage.jsonl"
        resume = journal_path.exists() and bool(journal_path.stat().st_size)
        if journal_path.exists() and not resume:
            journal_path.unlink()  # Empty journal means no request was started.
        journal = Journal(
            journal_path,
            run_id=row["run_id"],
            method=row["method"],
            dataset=row["dataset"],
            resume=resume,
        )
        transport = Transport(plan, row, config, directory, journal)
        started = time.perf_counter()
        manifest.update(
            status="running", run_id=row["run_id"], plan_sha256=target.digest(plan)
        )
        dense.write_json_atomic(path, manifest)
        try:
            if row["method"] == "dense":
                validation = dense_index(corpus, transport, directory)
            else:
                from scripts.e1_indexers import hipporag_index, raptor_index

                builder = (
                    hipporag_index if row["method"] == "hipporag2" else raptor_index
                )
                validation = builder(corpus, transport, directory, source)
            manifest.update(status="completed", validation=validation)
        except BaseException as exc:
            manifest.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            manifest["seconds"] += round(time.perf_counter() - started, 3)
            manifest["token_accounting"] = journal.reference()
            operations = {}
            records = read_records(journal.path)
            for started_row in (r for r in records if r["event"] == "started"):
                operation = started_row["operation"]
                operations.setdefault(operation, set()).add(started_row["attempt_id"])
            from scripts.token_accounting import summarize

            manifest["operations"] = {
                operation: summarize([r for r in records if r["attempt_id"] in ids])
                for operation, ids in operations.items()
            }
            manifest["artifacts"] = {
                p.relative_to(directory).as_posix(): dense.sha256_file(p)
                for p in directory.rglob("*")
                if p.is_file() and p.name not in ("manifest.json", "running.lock")
            }
            dense.write_json_atomic(path, manifest)
            transport.session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "prepare",
            "continue",
            "network-resume",
            "cycle-resume",
            "independent-raptor",
            "raptor-batch-resume",
            "raptor-clustering-resume",
            "prepare-summary-probe",
            "run-summary-probe",
            "prepare-schema-probe",
            "run-schema-probe",
            "seal",
            "run",
            "report",
            "verify",
        ),
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--method", choices=METHODS)
    parser.add_argument("--dataset", choices=DATASETS)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--prior-plan", type=Path)
    parser.add_argument("--passage-id")
    parser.add_argument("--approved-probe-sha256")
    parser.add_argument("--recovered-payload", type=Path)
    args = parser.parse_args()
    config = dotenv_values(args.env_file) if args.env_file else {}
    if args.command == "prepare":
        canonical = args.data_root.resolve() / "indexes/e1/issue13-plan.json"
        if args.plan.resolve() != canonical:
            raise ValueError("prepare_requires_canonical_data_root_plan")
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        response.raise_for_status()
        model = next(
            m for m in response.json()["models"] if m["name"] == "bge-m3:latest"
        )
        plan = make_plan(args.data_root, config, model["digest"])
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "continue":
        canonical = (
            Path(dense.read_json(args.prior_plan)["data_root"])
            / "indexes/e1/issue13-continuation-plan.json"
        )
        if args.plan.resolve() != canonical.resolve() or args.plan.exists():
            raise ValueError("continuation_requires_unused_canonical_plan")
        plan = continuation_plan(args.prior_plan)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "network-resume":
        canonical = (
            Path(dense.read_json(args.prior_plan)["data_root"])
            / "indexes/e1/issue13-network-plan.json"
        )
        if args.plan.resolve() != canonical.resolve() or args.plan.exists():
            raise ValueError("network_resume_requires_unused_canonical_plan")
        plan = network_resume_plan(args.prior_plan)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "cycle-resume":
        canonical = (
            Path(dense.read_json(args.prior_plan)["data_root"])
            / "indexes/e1/issue13-cycle-plan.json"
        )
        if args.plan.resolve() != canonical.resolve() or args.plan.exists():
            raise ValueError("cycle_resume_requires_unused_canonical_plan")
        plan = cycle_resume_plan(args.prior_plan, args.passage_id)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "independent-raptor":
        canonical = (
            Path(dense.read_json(args.prior_plan)["data_root"])
            / "indexes/e1/issue13-raptor-plan.json"
        )
        if args.plan.resolve() != canonical.resolve() or args.plan.exists():
            raise ValueError("independent_raptor_requires_unused_canonical_plan")
        plan = independent_raptor_plan(args.prior_plan)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "raptor-batch-resume":
        canonical = (
            Path(dense.read_json(args.prior_plan)["data_root"])
            / "indexes/e1/issue13-raptor-batch-plan.json"
        )
        if args.plan.resolve() != canonical.resolve() or args.plan.exists():
            raise ValueError("raptor_batch_requires_unused_canonical_plan")
        plan = raptor_batch_plan(args.prior_plan)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "raptor-clustering-resume":
        canonical = (
            Path(dense.read_json(args.prior_plan)["data_root"])
            / "indexes/e1/issue13-raptor-clustering-plan.json"
        )
        if args.plan.resolve() != canonical.resolve() or args.plan.exists():
            raise ValueError("clustering_resume_requires_unused_canonical_plan")
        plan = raptor_clustering_plan(args.prior_plan)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
    elif args.command == "prepare-summary-probe":
        prepared = prepare_summary_probe(args.prior_plan, args.recovered_payload)
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(prepared, stream, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    k: prepared[k]
                    for k in (
                        "max_new_posts",
                        "remaining_before_probe",
                        "reserved_tokens_upper_bound",
                    )
                }
            )
        )
        return
    elif args.command == "run-summary-probe":
        directory = execute_summary_probe(args.plan, config, args.approved_probe_sha256)
        print(
            json.dumps(
                {"status": dense.read_json(directory / "manifest.json")["status"]}
            )
        )
        return
    elif args.command == "prepare-schema-probe":
        if args.plan.exists():
            raise ValueError("schema_probe_prepare_requires_unused_output")
        probe = prepare_schema_probe(args.prior_plan, args.source)
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        with args.plan.open("x", encoding="utf-8") as stream:
            json.dump(probe, stream, ensure_ascii=False, indent=2)
        print(json.dumps({k: v for k, v in probe.items() if k != "cases"}))
        return
    elif args.command == "run-schema-probe":
        directory = execute_schema_probe(
            args.plan, args.prior_plan, args.source, config, args.approved_probe_sha256
        )
        print(
            json.dumps(
                {
                    "probe_status": dense.read_json(directory / "manifest.json")[
                        "status"
                    ],
                    "full_index_authorized": False,
                }
            )
        )
        return
    elif args.command == "seal":
        plan = seal_unstarted_plan(args.plan)
    else:
        plan = dense.read_json(args.plan)
        if args.command == "verify":
            from scripts.token_accounting import verified_reference

            for row in plan["rows"]:
                path = ROOT / row["output"] / "manifest.json"
                manifest = dense.read_json(path)
                if (
                    manifest["status"] != "completed"
                    or verified_reference(manifest, path)["status"] != "verified"
                ):
                    raise ValueError("index_not_completed_or_journal_invalid")
                for name, sha in manifest["artifacts"].items():
                    if dense.sha256_file(path.parent / name) != sha:
                        raise ValueError("index_artifact_changed")
        if args.command == "run":
            row = next(
                r
                for r in plan["rows"]
                if (r["method"], r["dataset"]) == (args.method, args.dataset)
            )
            try:
                execute(plan, row, config, args.source)
            finally:
                export(plan, args.plan)
    report = export(plan, args.plan)
    print(json.dumps({"batch_id": plan["batch_id"], "complete": report["complete"]}))


if __name__ == "__main__":
    main()
