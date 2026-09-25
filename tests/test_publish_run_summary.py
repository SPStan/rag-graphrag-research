import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_run_summary import public_summary


class PublishRunSummaryTests(unittest.TestCase):
    def write_artifacts(self, root, *, status="completed", result_id="q1"):
        run = root / "run.jsonl"
        run.write_text(json.dumps({"question_id": result_id, "answer": "private answer", "passage": "private passage"}) + "\n", encoding="utf-8")
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "run_id": "run-1", "status": status, "dataset": "musique", "mode": "local-poc",
            "expected_question_ids": ["q1"],
            "results_sha256": hashlib.sha256(run.read_bytes()).hexdigest(),
            "generation": {"model": {"name": "local-model"}, "options": {"temperature": 0}},
            "retrieval": {"method": "cosine", "top_k": 5},
            "inputs": {"queries_sha256": "a" * 64},
        }), encoding="utf-8")
        metrics = root / "metrics.json"
        metrics.write_text(json.dumps({"run_id": "run-1", "dataset": "musique", "top_k": 5, "em": 0.5}), encoding="utf-8")
        return run, metrics, manifest

    def test_summary_excludes_raw_result_text_and_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, metrics, manifest = self.write_artifacts(root)
            summary = public_summary(run, metrics, manifest, ["local diagnostic"])
            encoded = json.dumps(summary)
            self.assertEqual(summary["run"]["run_id"], "run-1")
            self.assertNotIn("private answer", encoded)
            self.assertNotIn("private passage", encoded)
            self.assertNotIn(str(root), encoded)

    def test_rejects_hash_id_and_status_mismatches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, metrics, manifest = self.write_artifacts(root)
            run.write_text(json.dumps({"question_id": "wrong"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "results_sha256"):
                public_summary(run, metrics, manifest, [])

            run, metrics, manifest = self.write_artifacts(root, status="running")
            with self.assertRaisesRegex(ValueError, "completed"):
                public_summary(run, metrics, manifest, [])

            run, metrics, manifest = self.write_artifacts(root, result_id="wrong")
            with self.assertRaisesRegex(ValueError, "question_id sequence"):
                public_summary(run, metrics, manifest, [])


if __name__ == "__main__":
    unittest.main()
