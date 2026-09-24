import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from scripts.track_dense import prepare_payload, verify_langfuse_trace


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

    def test_langfuse_verification_checks_run_id_full_text_and_known_usage(self):
        payload = {"run_id": "one", "rows": [{"prompt_tokens": 10,
                                                "completion_tokens": 3}],
                   "questions": [{"retrieved_passages": [{"text": "passage"}]}],
                   "manifest": {"retrieval": {"context_source_run_id": "source-run"}}}
        observations = [
            SimpleNamespace(name="dense-rag-run", metadata={"run_id": "one",
                                                              "context_source_run_id": "source-run"},
                            input={"run_id": "one"}, output={"metrics": {}}),
            SimpleNamespace(name="question", input={"question_id": "q1"},
                            output={"answer": "Paris"}),
            SimpleNamespace(name="query-embedding"),
            SimpleNamespace(name="retrieval", output={"documents": [{"text": "passage"}]}),
            SimpleNamespace(name="generation", input={"question": "Who?"},
                            output={"answer": "Paris"},
                            usage_details={"input": 10, "output": 3}),
        ]
        result = verify_langfuse_trace(observations, payload)
        self.assertEqual(result["retrieved_passages"], 1)
        self.assertEqual(result["generation_usage"], {"input": 10, "output": 3})
        observations[0].metadata = {"run_id": "one", "context_source_run_id": "wrong-source"}
        with self.assertRaisesRegex(RuntimeError, "context source run_id"):
            verify_langfuse_trace(observations, payload)
        observations[0].metadata = {"run_id": "other"}
        with self.assertRaisesRegex(RuntimeError, "run_id"):
            verify_langfuse_trace(observations, payload)


if __name__ == "__main__":
    unittest.main()
