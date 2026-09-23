import json
from pathlib import Path
import tempfile
import unittest

from scripts.track_dense import prepare_payload


class DenseTrackingPayloadTests(unittest.TestCase):
    def test_payload_links_run_metrics_manifest_and_full_retrieved_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id = "run-123"
            run_path = root / "run.jsonl"
            metrics_path = root / "metrics.json"
            manifest_path = root / "manifest.json"
            corpus_path = root / "corpus.json"
            row = {"run_id": run_id, "dataset": "musique", "question_id": "q1",
                   "question": "Who?", "retrieved": [{"id": "p1", "score": 0.9}]}
            run_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            metrics_path.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
            manifest_path.write_text(json.dumps({"run_id": run_id, "status": "completed"}),
                                     encoding="utf-8")
            corpus_path.write_text(json.dumps([{"id": "p1", "title": "A", "text": "Full passage"}]),
                                   encoding="utf-8")

            payload = prepare_payload(run_path, metrics_path, manifest_path, corpus_path)
            self.assertEqual(payload["run_id"], run_id)
            self.assertEqual(payload["questions"][0]["retrieved_passages"][0]["text"], "Full passage")
            self.assertEqual(payload["questions"][0]["retrieved_passages"][0]["score"], 0.9)

    def test_rejects_run_id_mismatch_and_unfinished_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_path = root / "run.jsonl"
            metrics_path = root / "metrics.json"
            manifest_path = root / "manifest.json"
            corpus_path = root / "corpus.json"
            run_path.write_text(json.dumps({"run_id": "one", "dataset": "musique"}) + "\n",
                                encoding="utf-8")
            metrics_path.write_text(json.dumps({"run_id": "two"}), encoding="utf-8")
            manifest_path.write_text(json.dumps({"run_id": "one", "status": "completed"}),
                                     encoding="utf-8")
            corpus_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "share one run_id"):
                prepare_payload(run_path, metrics_path, manifest_path, corpus_path)
            metrics_path.write_text(json.dumps({"run_id": "one"}), encoding="utf-8")
            manifest_path.write_text(json.dumps({"run_id": "one", "status": "running"}),
                                     encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "completed runs"):
                prepare_payload(run_path, metrics_path, manifest_path, corpus_path)


if __name__ == "__main__":
    unittest.main()
