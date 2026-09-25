"""Synthetic persistence and crash-safety tests for the repair journal."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.hipporag_repair_journal import RepairJournal


HASH_A = "a" * 64
HASH_B = "b" * 64
IDENTITY = {
    "plan_sha256": HASH_A,
    "source_hashes": {"manifest": HASH_B},
    "protocol": {"model_digest": "sha256:local-test", "num_ctx": 4096},
}


class RepairJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "repair-journal.json"

    def open_journal(self, *, schedule=None, **changes):
        values = dict(IDENTITY)
        values.update(changes)
        values["expected_task_keys"] = schedule or ["p1|openie_ner|2"]
        journal = RepairJournal(self.path, **values)
        self.addCleanup(journal.close)
        return journal

    def test_checkpoint_then_completion_persists_safe_attempt(self):
        schedule = ["p1|openie_ner|2", "p1|openie_triples|2"]
        journal = self.open_journal(schedule=schedule)
        task = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2}
        journal.begin(task)
        # An in-flight task is deliberately not resumable without reconciliation.
        with self.assertRaises(FileExistsError):
            self.open_journal(schedule=schedule)

        journal.complete(task, {
            "passage_id": "p1", "stage": "openie_ner", "attempt": 2,
            "status": "valid_nonempty", "usage": {"prompt_tokens": None},
        }, ["new entity"])
        journal.close()
        resumed = self.open_journal(schedule=schedule)
        self.assertEqual(resumed.data["completed_task_keys"], ["p1|openie_ner|2"])
        self.assertIsNone(resumed.data["in_flight"])
        resumed.close()

    def test_identity_mismatch_refuses_to_reuse_journal(self):
        self.open_journal().close()
        with self.assertRaisesRegex(ValueError, "different inputs"):
            self.open_journal(plan_sha256=HASH_B)

    def test_attempt_cannot_include_prompt_or_response(self):
        journal = self.open_journal()
        task = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2}
        journal.begin(task)
        with self.assertRaisesRegex(ValueError, "cannot persist"):
            journal.complete(task, {
                "passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                "response": "private text",
            })

    def test_finish_requires_exact_ordered_schedule(self):
        journal = self.open_journal()
        task = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2}
        journal.begin(task)
        journal.complete(task, {
            "passage_id": "p1", "stage": "openie_ner", "attempt": 2,
            "status": "valid_empty",
        }, [])
        with self.assertRaisesRegex(ValueError, "planned order"):
            journal.finish(expected_task_keys=["p2|openie_ner|2"])
        journal.finish(expected_task_keys=["p1|openie_ner|2"])
        self.assertEqual(json.loads(self.path.read_text())["status"], "complete")

    def test_corrupt_ledger_is_rejected(self):
        journal = self.open_journal()
        journal.data["completed_task_keys"].append("orphan")
        journal._save()
        journal.close()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.open_journal()

    def test_begin_requires_next_frozen_task(self):
        journal = self.open_journal(schedule=[
            "p1|openie_ner|2", "p1|openie_triples|2",
        ])
        with self.assertRaisesRegex(ValueError, "next in the frozen schedule"):
            journal.begin({
                "passage_id": "p1", "stage": "openie_triples", "attempt": 2,
            })

    def test_failed_completion_write_keeps_durable_in_flight(self):
        journal = self.open_journal()
        task = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2}
        journal.begin(task)
        with patch.object(journal, "_save", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                journal.complete(task, {**task, "status": "valid_empty"}, [])
        self.assertEqual(journal.data["completed_task_keys"], [])
        with self.assertRaisesRegex(RuntimeError, "in flight"):
            self.open_journal()


if __name__ == "__main__":
    unittest.main()
