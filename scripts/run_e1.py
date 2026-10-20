"""Bounded full-corpus E1 indexing; private checkpoints, public cost summaries."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import numpy as np
import requests
from dotenv import dotenv_values

from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts.token_accounting import Journal, read_records

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("dense", "hipporag2", "raptor")
DATASETS = ("musique", "hotpotqa")
# Independent, disjoint allocations: no caller can spend another row's allowance.
LIMITS = {"dense": 2_000_000, "hipporag2": 20_000_000, "raptor": 12_000_000}
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
    combinations = [(r["method"], r["dataset"]) for r in plan["rows"]]
    if (
        plan["kind"] != "E1_full_corpus_indexing"
        or plan["parameters"] != PARAMETERS
        or plan["workspace"] != str(ROOT.resolve())
        or row["method"] not in METHODS
        or row["dataset"] not in DATASETS
        or row["token_limit"] != LIMITS[row["method"]]
        or plan["combined_token_limit"] != sum(r["token_limit"] for r in plan["rows"])
        or row["code_commit"] != git("rev-parse", "HEAD")
        or code_dirty()
        or plan["model"] != config["TARGET_API_MODEL"]
        or plan["endpoint"] != config["TARGET_API_BASE_URL"].rstrip("/")
        or sorted(combinations) != sorted((m, d) for m in METHODS for d in DATASETS)
        or row["output"]
        != f"indexes/e1/{plan['batch_id']}/{row['method']}/{row['dataset']}"
    ):
        raise ValueError("E1_plan_or_code_mismatch")
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

    def call(self, payload, *, kind, operation):
        key = target.digest({"payload": payload, "kind": kind, "operation": operation})
        checkpoint = self.calls / f"{key}.json"
        response = self.calls / f"{key}.response.json"
        summary = self.journal.summary()
        if not summary["complete"] or any(p["errors"] for p in summary["phases"]):
            raise ValueError("incomplete_or_failed_journal_cannot_continue")
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
                producer_usage_complete=True,
            )
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
        dense.write_json_atomic(checkpoint, saved)
        remote = kind == "llm"
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
            headers={"Authorization": f"Bearer {self.config['LITELLM_API_KEY']}"}
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
        vectors = []
        for offset in range(0, len(texts), 32):
            body = self.call(
                {
                    "model": self.plan["embedding_model"],
                    "input": texts[offset : offset + 32],
                    "truncate": False,
                },
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
        body = self.call(payload, kind="llm", operation=operation)
        return body["choices"][0]["message"]["content"], {
            **body["usage"],
            "finish_reason": body["choices"][0]["finish_reason"],
        }


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


def export(plan, plan_path):
    rows = []
    for row in plan["rows"]:
        manifest = ROOT / row["output"] / "manifest.json"
        result = (
            dense.read_json(manifest) if manifest.exists() else {"status": "pending"}
        )
        public = {key: value for key, value in result.items() if key != "artifacts"}
        if manifest.exists():
            public["artifact_manifest_sha256"] = dense.sha256_file(manifest)
        rows.append({**row, **public})
    report = {
        "batch_id": plan["batch_id"],
        "plan_sha256": dense.sha256_file(plan_path),
        "models": {
            key: plan[key] for key in ("model", "embedding_model", "embedding_digest")
        },
        "parameters": plan["parameters"],
        "rows": rows,
        "combined_token_limit": plan["combined_token_limit"],
        "complete": all(r["status"] == "completed" for r in rows),
        "limitations": "E1 measures indexing cost/coverage, not retrieval or answer quality. Historical smoke unknowns are preserved outside these new runs.",
    }
    report["physical_known_tokens"] = sum(
        sum(
            r.get("token_accounting", {})
            .get("summary", {})
            .get("known_subtotal", {})
            .values()
        )
        for r in rows
    )
    for row in rows:
        row["cost_semantics"] = "Physical new cost; replay is not charged twice."
        if row["method"] == "raptor" and row.get("validation", {}).get(
            "leaf_producer_run_id"
        ):
            producer = next(
                r
                for r in rows
                if r["run_id"] == row["validation"]["leaf_producer_run_id"]
            )
            row["reused_leaf_build_cost"] = producer["token_accounting"]["summary"][
                "known_subtotal"
            ]
            row["cost_semantics"] += (
                " Add reused_leaf_build_cost for standalone method cost; exclude it from batch physical total."
            )
    dense.write_json_atomic(ROOT / "results/summary/e1-indexing.json", report)
    lines = [
        "# E1: индексация",
        "",
        "| Метод | Датасет | Статус | LLM in/out | Embed | POST | Секунды | Полнота | Run ID / index |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        usage = row.get("token_accounting", {}).get("summary", {})
        known = usage.get("known_subtotal", {})
        completeness = usage.get("complete", False) and usage.get(
            "historical_cache_cost_complete", False
        )
        lines.append(
            f"| {row['method']} | {row['dataset']} | {row['status']} | {known.get('llm_input_tokens', '—')}/{known.get('llm_output_tokens', '—')} | {known.get('embedding_input_tokens', '—')} (+cache {row.get('reused_leaf_build_cost', {}).get('embedding_input_tokens', 0)}) | {usage.get('attempts', '—')} | {row.get('seconds', '—')} | {completeness} | {row['run_id']} / `{row['output']}` |"
        )
    (ROOT / "results/summary/e1-indexing.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return report


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
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--method", choices=METHODS)
    parser.add_argument("--dataset", choices=DATASETS)
    parser.add_argument("--source", type=Path)
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
    else:
        plan = dense.read_json(args.plan)
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
