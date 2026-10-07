"""Durable, per-request token accounting for experiment transports.

The journal contains metadata only. A started record is fsynced before transport.
Terminal records are fsynced before a caller validates response content.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid


TOKEN_FIELDS = ("llm_input_tokens", "llm_output_tokens", "embedding_input_tokens")
PHASES = {
    "index_embedding": "index",
    "openie_ner": "index",
    "openie_triples": "index",
    "graph_retrieval": "retrieval",
    "query_embedding": "retrieval",
    "retrieval_embedding": "retrieval",
    "filter": "retrieval",
    "qa": "reader",
    "reader": "reader",
    "generation": "reader",
}


def token(value):
    return value if type(value) is int and value >= 0 else None


def extract_usage(payload, kind, provider):
    """Read only reported usage; never derive it from text length or total_tokens."""
    if not isinstance(payload, dict):
        payload = {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else payload
    if provider == "local_ollama" and "prompt_eval_count" in payload:
        incoming = token(payload.get("prompt_eval_count"))
        outgoing = token(payload.get("eval_count"))
    elif provider == "hipporag_sdk":
        incoming = token(usage.get("prompt_tokens"))
        outgoing = token(usage.get("completion_tokens"))
    else:
        incoming = token(usage.get("prompt_tokens"))
        outgoing = token(usage.get("completion_tokens"))
    return {
        "llm_input_tokens": incoming if kind == "llm" else None,
        "llm_output_tokens": outgoing if kind == "llm" else None,
        "embedding_input_tokens": incoming if kind == "embedding" else None,
    }


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, path, *, run_id, method, dataset, resume=False):
        self.path = Path(path)
        self.run_id, self.method, self.dataset = run_id, method, dataset
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if resume:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            records = read_records(self.path)
            if not records or any(
                row.get("run_id") != run_id
                or row.get("method") != method
                or row.get("dataset") != dataset
                for row in records
            ):
                raise ValueError("journal_run_mismatch")
        else:
            with self.path.open("x", encoding="utf-8") as stream:
                stream.flush()
                os.fsync(stream.fileno())

    def _append(self, record):
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self.lock, self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

    def start(
        self,
        *,
        phase,
        operation,
        provider,
        model,
        kind,
        object_id=None,
        operation_id=None,
        attempt_no=1,
    ):
        if phase not in PHASES.values() or kind not in ("llm", "embedding"):
            raise ValueError("invalid_accounting_phase_or_kind")
        if type(attempt_no) is not int or attempt_no < 1:
            raise ValueError("invalid_attempt_no")
        attempt_id = str(uuid.uuid4())
        row = {
            "schema_version": 1,
            "event": "started",
            "run_id": self.run_id,
            "method": self.method,
            "dataset": self.dataset,
            "operation_id": operation_id or str(uuid.uuid4()),
            "attempt_id": attempt_id,
            "attempt_no": attempt_no,
            "phase": phase,
            "operation": operation,
            "provider": provider,
            "model": model,
            "kind": kind,
            "object_id": object_id,
            "started_at": _timestamp(),
        }
        self._append(row)
        return row

    def finish(
        self,
        started,
        *,
        status,
        usage=None,
        request_id=None,
        error_code=None,
        wall_seconds=None,
        cache_hit=False,
        producer_run_id=None,
    ):
        if status not in ("success", "error", "unknown", "cache_hit"):
            raise ValueError("invalid_attempt_status")
        values = {key: token((usage or {}).get(key)) for key in TOKEN_FIELDS}
        applicable = (
            ("embedding_input_tokens",)
            if started["kind"] == "embedding"
            else TOKEN_FIELDS[:2]
        )
        known = sum(values[key] is not None for key in applicable)
        row = {
            **started,
            "event": "finished",
            "status": status,
            "finished_at": _timestamp(),
            "wall_seconds": wall_seconds,
            "request_id": request_id if isinstance(request_id, str) else None,
            "error_code": error_code if isinstance(error_code, str) else None,
            "cache_hit": bool(cache_hit),
            "producer_run_id": producer_run_id,
            **values,
            "usage_status": "complete"
            if known == len(applicable)
            else "partial"
            if known
            else "unknown",
        }
        self._append(row)
        return row

    def summary(self):
        return summarize(read_records(self.path))

    def cache_hit(
        self,
        *,
        phase,
        operation,
        provider,
        model,
        kind,
        object_id=None,
        producer_run_id=None,
    ):
        started = self.start(
            phase=phase,
            operation=operation,
            provider=provider,
            model=model,
            kind=kind,
            object_id=object_id,
        )
        return self.finish(
            started, status="cache_hit", cache_hit=True, producer_run_id=producer_run_id
        )

    def reference(self):
        return {
            "journal_file": self.path.name,
            "journal_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "summary": self.summary(),
        }


def read_records(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def verified_reference(manifest, manifest_path):
    """Verify new journals; old manifests remain explicitly legacy/unknown."""
    reference = manifest.get("token_accounting")
    if reference is None:
        return {"status": "legacy_unknown", "summary": None, "path": None}
    name = reference.get("journal_file")
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError("invalid_token_journal_name")
    path = Path(manifest_path).parent / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference.get("journal_sha256"):
        raise ValueError("token_journal_hash_mismatch")
    records = read_records(path)
    if any(row.get("run_id") != manifest.get("run_id") for row in records):
        raise ValueError("token_journal_run_mismatch")
    summary = summarize(records)
    if summary != reference.get("summary"):
        raise ValueError("token_journal_summary_mismatch")
    return {"status": "verified", "summary": summary, "path": path}


def summarize(records):
    attempts = {}
    for row in records:
        key = row["attempt_id"]
        prior = attempts.setdefault(key, {})
        event = row["event"]
        if event in prior and prior[event] != row:
            raise ValueError("conflicting_attempt_event")
        prior[event] = row
    phases = {}
    for pair in attempts.values():
        started = pair.get("started")
        if started is None:
            raise ValueError("terminal_without_started")
        finished = pair.get("finished")
        phase_key = (started["phase"], started["provider"])
        item = phases.setdefault(
            phase_key,
            {
                "phase": phase_key[0],
                "provider": phase_key[1],
                "attempts": 0,
                "errors": 0,
                "unfinished": 0,
                "cache_hits": 0,
                "cache_provenance_unknown": 0,
                "known_subtotal": {key: 0 for key in TOKEN_FIELDS},
                "unknown_fields": {key: 0 for key in TOKEN_FIELDS},
            },
        )
        if finished and finished["status"] == "cache_hit":
            item["cache_hits"] += 1
            if not finished.get("producer_run_id"):
                item["cache_provenance_unknown"] += 1
            continue
        item["attempts"] += 1
        if finished is None:
            item["unfinished"] += 1
        elif finished["status"] != "success":
            item["errors"] += 1
        applicable = (
            ("embedding_input_tokens",)
            if started["kind"] == "embedding"
            else TOKEN_FIELDS[:2]
        )
        for key in applicable:
            value = finished.get(key) if finished else None
            if value is None:
                item["unknown_fields"][key] += 1
            else:
                item["known_subtotal"][key] += value
    ordered = [phases[key] for key in sorted(phases)]
    for item in ordered:
        item["complete"] = not any(item["unknown_fields"].values())
        item["total"] = item["known_subtotal"] if item["complete"] else None
    return {
        "schema_version": 1,
        "phases": ordered,
        "known_subtotal": {
            key: sum(p["known_subtotal"][key] for p in ordered) for key in TOKEN_FIELDS
        },
        "complete": all(p["complete"] for p in ordered),
        "attempts": sum(p["attempts"] for p in ordered),
        "historical_cache_cost_complete": not any(
            p["cache_provenance_unknown"] for p in ordered
        ),
    }


def recorded_call(
    journal,
    send,
    *,
    phase,
    operation,
    provider,
    model,
    kind,
    object_id=None,
    operation_id=None,
    attempt_no=1,
):
    """Record the transport result before its caller inspects response content."""
    started = journal.start(
        phase=phase,
        operation=operation,
        provider=provider,
        model=model,
        kind=kind,
        object_id=object_id,
        operation_id=operation_id,
        attempt_no=attempt_no,
    )
    begun = time.perf_counter()
    try:
        payload = send()
    except Exception as exc:
        journal.finish(
            started,
            status="unknown"
            if type(exc).__name__ in ("Timeout", "ReadTimeout", "ConnectTimeout")
            else "error",
            error_code=type(exc).__name__,
            wall_seconds=time.perf_counter() - begun,
        )
        raise
    journal.finish(
        started,
        status="success",
        usage=extract_usage(payload, kind, provider),
        request_id=payload.get("id") if isinstance(payload, dict) else None,
        wall_seconds=time.perf_counter() - begun,
    )
    return payload
