"""Offline repair and process-boundary checkpoint tests; no model is loaded."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.hipporag_repair import plan_openie_repairs
from scripts.hipporag_repair_journal import RepairJournal
from scripts.run_hipporag_repair_offline import run_repair_pass


class OfflineRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "results" / "raw" / "checkpoint.json"
        self.source = [
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
             "status": "truncated", "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
             "status": "valid_nonempty", "source_provenance_complete": True},
        ]
        self.targets = plan_openie_repairs(["p1"], self.source)["targets"]
        self.state = {"docs": [{"idx": 0, "extracted_entities": ["old"],
                                "extracted_triples": [["old", "is", "old"]]}]}

    def journal(self):
        return RepairJournal(self.path, plan_sha256="a" * 64,
                             source_hashes={"manifest": "b" * 64},
                             protocol={"model_digest": "fake", "num_ctx": 4096},
                             expected_task_keys=[RepairJournal.task_key(t) for t in self.targets])

    def test_resume_uses_saved_entities_and_finishes_ledger(self):
        calls = []
        with self.journal() as journal:
            ner = self.targets[0]
            journal.begin(ner)
            journal.complete(ner, {**ner, "status": "valid_nonempty",
                                   "source_provenance_complete": True}, ["new"])
        with self.journal() as journal:
            def fake(task, entities):
                calls.append((task, entities))
                return {"attempt": {**task, "status": "valid_nonempty",
                                    "source_provenance_complete": True},
                        "values": [["new", "is", "fresh"]]}
            result = run_repair_pass(journal, self.targets, self.source,
                                     self.state, {"p1": 0}, fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], ["new"])
        self.assertEqual(calls[0][0]["dependency_attempt"], 2)
        self.assertEqual(result["state"]["docs"][0]["extracted_entities"], ["new"])
        self.assertEqual(result["state"]["docs"][0]["extracted_triples"],
                         [["new", "is", "fresh"]])
        self.assertEqual(len(result["ledger"]), 4)
        self.assertEqual(json.loads(self.path.read_text())["status"], "complete")

    def test_corruption_and_unknown_request_refuse_resume(self):
        with self.journal() as journal:
            ner = self.targets[0]
            journal.begin(ner)
            journal.complete(ner, {**ner, "status": "valid_nonempty"}, ["new"])
        data = json.loads(self.path.read_text())
        data["attempts"][0]["values"] = ["tampered"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            self.journal()
        self.path.unlink()
        with self.journal() as journal:
            journal.begin(self.targets[0])
        with self.assertRaisesRegex(RuntimeError, "in flight"):
            self.journal()

    def test_writer_and_task_content_guards(self):
        with self.journal() as journal:
            with self.assertRaises(FileExistsError):
                self.journal()
            with self.assertRaisesRegex(ValueError, "cannot persist"):
                journal.begin({**self.targets[0], "prompt": "secret passage"})
            self.assertIsNone(journal.data["in_flight"])

    def test_failed_ner_stops_before_dependent_triple(self):
        with self.journal() as journal:
            ner = self.targets[0]
            journal.begin(ner)
            journal.complete(ner, {**ner, "status": "truncated"}, None)
        with self.journal() as journal:
            with self.assertRaisesRegex(RuntimeError, "successful repaired NER"):
                run_repair_pass(journal, self.targets, self.source,
                                self.state, {"p1": 0},
                                lambda *_: self.fail("No triple request is allowed"))


if __name__ == "__main__":
    unittest.main()
