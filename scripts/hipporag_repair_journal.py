"""Private, single-writer checkpoint for bounded OpenIE repair."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import os


class RepairJournal:
    """Persist one request-at-a-time checkpoints without silent replay."""

    def __init__(self, path, *, plan_sha256, source_hashes, protocol,
                 expected_task_keys):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._lock_stream = None
        self._lock_held = False
        if not re.fullmatch(r"[0-9a-f]{64}", str(plan_sha256)):
            raise ValueError("A plan SHA-256 is required")
        if not isinstance(source_hashes, dict) or not source_hashes:
            raise ValueError("Source artifact hashes are required")
        if any(not re.fullmatch(r"[0-9a-f]{64}", str(value))
               for value in source_hashes.values()):
            raise ValueError("Every source artifact hash must be SHA-256")
        if not isinstance(protocol, dict) or not protocol:
            raise ValueError("A frozen repair protocol is required")
        if (not isinstance(expected_task_keys, list) or not expected_task_keys
                or any(not isinstance(key, str) or not key for key in expected_task_keys)
                or len(expected_task_keys) != len(set(expected_task_keys))):
            raise ValueError("An exact ordered task schedule is required")
        self.expected_task_keys = list(expected_task_keys)
        schedule_bytes = json.dumps(
            self.expected_task_keys, separators=(",", ":")
        ).encode("utf-8")
        self.identity = {
            "plan_sha256": plan_sha256,
            "source_hashes": deepcopy(source_hashes),
            "protocol": deepcopy(protocol),
            "schedule_sha256": hashlib.sha256(schedule_bytes).hexdigest(),
            "schedule_size": len(self.expected_task_keys),
        }
        self._validate_safe_fields(self.identity)
        try:
            self._lock_stream = self._lock_path.open("a+b")
            self._lock_stream.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(self._lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise FileExistsError("Another repair writer is active") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise FileExistsError("Another repair writer is active") from exc
            self._lock_held = True
            self._open()
        except BaseException:
            self.close()
            raise

    def _open(self):
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if self.data.get("identity") != self.identity:
                raise ValueError("Existing repair journal belongs to different inputs")
            if self.data.get("in_flight") is not None:
                raise RuntimeError(
                    "A request was in flight at interruption; reconcile it before resuming"
                )
            self._validate_attempts()
        else:
            self.data = {
                "schema_version": 1,
                "status": "planned",
                "identity": self.identity,
                "attempts": [],
                "completed_task_keys": [],
                "next_task_index": 0,
                "in_flight": None,
            }
            self._save()

    def close(self):
        if self._lock_stream is not None:
            if self._lock_held and os.name == "nt":
                import msvcrt
                self._lock_stream.seek(0)
                msvcrt.locking(self._lock_stream.fileno(), msvcrt.LK_UNLCK, 1)
            elif self._lock_held:
                import fcntl
                fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_UN)
            self._lock_stream.close()
            self._lock_stream = None
            self._lock_held = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def task_key(task):
        required = ("passage_id", "stage", "attempt")
        if any(key not in task for key in required):
            raise ValueError("Repair task is missing its stable identity")
        return f"{task['passage_id']}|{task['stage']}|{task['attempt']}"

    @classmethod
    def _validate_safe_fields(cls, value):
        forbidden = {
            "prompt", "response", "passage", "raw_response", "raw_prompt",
            "secret", "secret_key", "api_key", "access_token", "password",
            "authorization",
        }
        if isinstance(value, dict):
            if any(str(key).lower() in forbidden for key in value):
                raise ValueError("Repair journal cannot persist prompts, source text, or secrets")
            for nested in value.values():
                cls._validate_safe_fields(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                cls._validate_safe_fields(nested)

    def _validate_attempts(self):
        attempts = self.data.get("attempts")
        completed = self.data.get("completed_task_keys")
        if (not isinstance(attempts, list) or not isinstance(completed, list)
                or len(completed) != len(set(completed))
                or len(attempts) != len(completed)
                or self.data.get("next_task_index") != len(completed)
                or completed != self.expected_task_keys[:len(completed)]):
            raise ValueError("Repair journal attempt ledger is inconsistent")
        if [self.task_key(row.get("task", {})) for row in attempts] != completed:
            raise ValueError("Repair journal task order does not match its ledger")
        for row in attempts:
            attempt = row.get("attempt")
            task = row.get("task")
            if (not isinstance(attempt, dict)
                    or any(attempt.get(key) != task.get(key)
                           for key in ("passage_id", "stage", "attempt"))):
                raise ValueError("Repair journal attempt metadata does not match its task")
            self._validate_output(row)
        self._validate_safe_fields(self.data)

    @staticmethod
    def _output_sha(values):
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def _validate_output(cls, row):
        attempt, values = row["attempt"], row.get("values")
        status, stage = attempt.get("status"), attempt.get("stage")
        if status in ("valid_empty", "valid_nonempty"):
            if not isinstance(values, list) or (status == "valid_empty") != (len(values) == 0):
                raise ValueError("Successful repair output is missing or inconsistent")
            if stage == "openie_ner":
                valid = all(isinstance(v, str) and v.strip() for v in values)
            else:
                valid = stage == "openie_triples" and all(
                    isinstance(v, list) and len(v) == 3 and
                    all(isinstance(x, str) and x.strip() for x in v) for v in values)
            if not valid or row.get("values_sha256") != cls._output_sha(values):
                raise ValueError("Successful repair output is corrupt")
        elif values is not None or row.get("values_sha256") is not None:
            raise ValueError("Unsuccessful repair must not store accepted output")

    def _save(self):
        if self._lock_stream is None:
            raise RuntimeError("Repair journal writer is closed")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".part")
        payload = json.dumps(self.data, ensure_ascii=False, indent=2) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        temporary.replace(self.path)

    def begin(self, task):
        self._validate_safe_fields(task)
        allowed = {"passage_id", "stage", "attempt", "retry_of_attempt",
                   "remedial_retry", "operation", "dependency_stage",
                   "dependency_attempt", "dependency_attempt_pending"}
        if not isinstance(task, dict) or set(task) - allowed:
            raise ValueError("Repair task contains unplanned fields")
        key = self.task_key(task)
        if key in self.data["completed_task_keys"]:
            raise ValueError("Repair task is already recorded as completed")
        if self.data["in_flight"] is not None:
            raise RuntimeError("Another repair task is already in flight")
        index = self.data["next_task_index"]
        if index >= len(self.expected_task_keys) or key != self.expected_task_keys[index]:
            raise ValueError("Repair task is not next in the frozen schedule")
        updated = deepcopy(self.data)
        updated["status"] = "running"
        updated["in_flight"] = {
            "task": deepcopy(task),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._commit(updated)

    def complete(self, task, attempt, values=None):
        key = self.task_key(task)
        in_flight = self.data["in_flight"]
        if in_flight is None or in_flight.get("task") != task:
            raise ValueError("Completed task does not match the durable in-flight checkpoint")
        if not isinstance(attempt, dict) or attempt.get("passage_id") != task["passage_id"]:
            raise ValueError("Attempt metadata does not match the task passage")
        if attempt.get("stage") != task["stage"] or attempt.get("attempt") != task["attempt"]:
            raise ValueError("Attempt metadata does not match the task stage/number")
        safe_attempt = deepcopy(attempt)
        self._validate_safe_fields(safe_attempt)
        updated = deepcopy(self.data)
        row = {
            "task": deepcopy(task),
            "attempt": safe_attempt,
            "values": deepcopy(values),
            "values_sha256": self._output_sha(values) if values is not None else None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._validate_output(row)
        updated["attempts"].append(row)
        updated["completed_task_keys"].append(key)
        updated["next_task_index"] += 1
        updated["in_flight"] = None
        updated["status"] = "running"
        self._commit(updated)

    def _commit(self, updated):
        previous = self.data
        self.data = updated
        try:
            self._save()
        except BaseException:
            self.data = previous
            self.close()
            raise

    def finish(self, *, expected_task_keys):
        if self.data["in_flight"] is not None:
            raise RuntimeError("Cannot finish while a task is in flight")
        if (list(expected_task_keys) != self.expected_task_keys
                or self.data["completed_task_keys"] != self.expected_task_keys):
            raise ValueError("Cannot finish before all tasks complete in planned order")
        updated = deepcopy(self.data)
        updated["status"] = "complete"
        self._commit(updated)

    def stop(self, reason):
        """Durably halt this schedule so a later process cannot auto-resume it."""
        allowed = {"unresolved_extraction", "context_overflow", "request_outcome_unknown",
                   "deadline", "checkpoint_error"}
        if reason not in allowed:
            raise ValueError("Unknown repair stop reason")
        if self.data["in_flight"] is not None:
            raise RuntimeError("Cannot mark stopped while a request is in flight")
        updated = deepcopy(self.data)
        updated["status"] = "stopped"
        updated["stop_reason"] = reason
        self._commit(updated)
