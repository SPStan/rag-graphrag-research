import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from scripts.track_dense import (get_all_langfuse_observations, prepare_payload,
                                 select_mlflow_trace_for_run, verify_langfuse_trace)


class DenseTrackingPayloadTests(unittest.TestCase):
    def test_langfuse_observation_reader_follows_cursors(self):
        first = SimpleNamespace(data=["a"], meta=SimpleNamespace(next_cursor="next"))
        second = SimpleNamespace(data=["b"], meta=SimpleNamespace(next_cursor=None))

        class Observations:
            def __init__(self):
                self.cursors = []

            def get_many(self, **kwargs):
                self.cursors.append(kwargs["cursor"])
                return first if len(self.cursors) == 1 else second

        observations = Observations()
        client = SimpleNamespace(api=SimpleNamespace(observations=observations))
        self.assertEqual(get_all_langfuse_observations(client, "trace"), ["a", "b"])
        self.assertEqual(observations.cursors, [None, "next"])

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
            run_hash = __import__("hashlib").sha256(run_path.read_bytes()).hexdigest()
            metrics_path.write_text(json.dumps({"run_id": run_id, "dataset": "musique",
                                                 "questions_evaluated": 1, "top_k": 5}), encoding="utf-8")
            manifest_path.write_text(json.dumps({"run_id": run_id, "status": "completed",
                "dataset": "musique", "expected_question_ids": ["q1"], "results_sha256": run_hash,
                "generation": {"model": {"name": "g"}}, "embedding": {"model": {"name": "e"}},
                "retrieval": {"method": "cosine", "top_k": 5}}), encoding="utf-8")
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

    def test_mlflow_trace_selection_uses_exact_run_id(self):
        def trace(trace_id, run_id):
            return SimpleNamespace(data=SimpleNamespace(spans=[
                SimpleNamespace(name="dense-rag-run", attributes={"rag.run_id": run_id}),
                SimpleNamespace(name="generation", attributes={}),
            ]))

        class FakeMlflow:
            def search_traces(self, **_kwargs):
                return {"trace_id": SimpleNamespace(tolist=lambda: ["old", "wanted"])}

            def get_trace(self, trace_id):
                return trace(trace_id, "old-run" if trace_id == "old" else "wanted-run")

        selected = select_mlflow_trace_for_run(FakeMlflow(), "1", "dense-rag-run", "wanted-run")
        self.assertEqual(selected["trace_id"], "wanted")

    def test_payload_rejects_manifest_question_sequence_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_path = root / "run.jsonl"
            run_path.write_text(json.dumps({"run_id": "one", "dataset": "musique",
                                             "question_id": "q1", "retrieved": []}) + "\n",
                                encoding="utf-8")
            (root / "metrics.json").write_text(json.dumps({"run_id": "one", "dataset": "musique",
                "questions_evaluated": 1, "top_k": 5}), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({
                "run_id": "one", "status": "completed", "dataset": "musique",
                "expected_question_ids": ["other"],
                "results_sha256": __import__("hashlib").sha256(run_path.read_bytes()).hexdigest(),
                "generation": {"model": {"name": "g"}}, "embedding": {"model": {"name": "e"}},
                "retrieval": {"method": "cosine", "top_k": 5},
            }), encoding="utf-8")
            (root / "corpus.json").write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "question_id sequence"):
                prepare_payload(run_path, root / "metrics.json", root / "manifest.json",
                                root / "corpus.json")

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

    def test_langfuse_verification_accepts_hipporag_run_with_indexing_observations(self):
        payload = {
            "run_id": "hippo-1", "system": "hipporag2",
            "trace_name": "hipporag2-rag-run",
            "rows": [{"prompt_tokens": 10, "completion_tokens": 2}],
            "questions": [{"retrieved_passages": [{"text": "full passage"}]}],
            "manifest": {"index": {"usage": {"phases": {
                "openie_ner": {"api_prompt_tokens": 3},
            }}}},
        }
        observations = [
            SimpleNamespace(name="hipporag2-rag-run", metadata={"run_id": "hippo-1"},
                            input={"run_id": "hippo-1"}, output={"metrics": {}}),
            SimpleNamespace(name="indexing", metadata={}, input={"model": "bge-m3"},
                            output={"cache": {}}),
            SimpleNamespace(name="openie-extraction", metadata={}, input={"commit": "abc"},
                            output={"phases": {}}),
            SimpleNamespace(name="question", metadata={}, input={"id": "q1"},
                            output={"answer": "Alice"}),
            SimpleNamespace(name="query-embedding", metadata={}, input={"question": "Who?"},
                            output={"prompt_tokens": 1}),
            SimpleNamespace(name="retrieval", metadata={}, input={"question": "Who?"},
                            output={"documents": [{"text": "full passage"}]}),
            SimpleNamespace(name="generation", metadata={}, input={"question": "Who?"},
                            output={"answer": "Alice"},
                            usage_details={"input": 10, "output": 2}),
        ]
        result = verify_langfuse_trace(observations, payload)
        self.assertIn("hipporag2-rag-run", result["observation_names"])
        self.assertIn("indexing", result["observation_names"])
        self.assertEqual(result["generation_usage"], {"input": 10, "output": 2})


if __name__ == "__main__":
    unittest.main()
