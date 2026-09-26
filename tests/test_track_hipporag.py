import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.track_hipporag import load_payload


class HippoRAGTrackingPayloadTests(unittest.TestCase):
    def _write_inputs(self, root):
        run_id = "hippo-run-1"
        run_path = root / "run.jsonl"
        row = {
            "run_id": run_id, "dataset": "sample", "question_id": "q1",
            "question": "Who?", "answer": "Alice", "raw_answer": "Answer: Alice",
            "reader_prompt_version": "hipporag-upstream-v1", "done": True,
            "done_reason": "stop", "top_k": 1, "prompt_tokens": 10,
            "completion_tokens": 2, "retrieved": [{"id": "p1", "title": "A",
                                                         "text": "Full text", "score": 0.9}],
        }
        content = (json.dumps(row) + "\n").encode("utf-8")
        run_path.write_bytes(content)
        metrics_path = root / "run.metrics.json"
        metrics_path.write_text(json.dumps({
            "run_id": run_id, "dataset": "sample", "questions_evaluated": 1,
            "top_k": 1, "em": 1.0, "token_f1": 1.0, "recall_at_k": 1.0,
        }), encoding="utf-8")
        manifest_path = root / "run.manifest.json"
        manifest_path.write_text(json.dumps({
            "run_id": run_id, "dataset": "sample", "status": "completed",
            "results_sha256": hashlib.sha256(content).hexdigest(),
            "expected_question_ids": ["q1"], "generation": {},
            "embedding": {"model": {"name": "bge-m3", "digest": "embed-digest"}},
        }), encoding="utf-8")
        return run_path, metrics_path, manifest_path

    def test_payload_preserves_full_retrieved_text_and_prompt_version(self):
        with tempfile.TemporaryDirectory() as temp:
            run_path, metrics_path, manifest_path = self._write_inputs(Path(temp))
            payload = load_payload(run_path, metrics_path, manifest_path)
            self.assertEqual(payload["system"], "hipporag2")
            self.assertEqual(payload["trace_name"], "hipporag2-rag-run")
            self.assertEqual(payload["questions"][0]["retrieved_passages"][0]["text"], "Full text")
            self.assertEqual(payload["manifest"]["generation"]["reader_prompt_version"],
                             "hipporag-upstream-v1")

    def test_payload_rejects_partial_or_hash_mismatched_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_path, metrics_path, manifest_path = self._write_inputs(root)
            run_path.write_text(run_path.read_text(encoding="utf-8").replace("Alice", "Bob"),
                                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest hash"):
                load_payload(run_path, metrics_path, manifest_path)
            run_path, metrics_path, manifest_path = self._write_inputs(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["expected_question_ids"] = ["q1", "q2"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "planned IDs"):
                load_payload(run_path, metrics_path, manifest_path)


if __name__ == "__main__":
    unittest.main()
