import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.replay_reader import run, validate_replay_source
from scripts.run_dense import GENERATION_OPTIONS, READER_PROMPT_VERSION, build_reader_messages


def replay_payload():
    row = {
        "run_id": "source-run", "dataset": "musique", "question_id": "q1",
        "planned_question_ids": ["q1"], "question": "Who is the person?",
        "embedding_model": {"name": "bge-m3:latest", "digest": "embedding-digest"},
        "generation_options": dict(GENERATION_OPTIONS),
        "reader_prompt_version": READER_PROMPT_VERSION,
        "top_k": 2,
        "retrieved": [{"id": "p2", "score": 0.9}, {"id": "p1", "score": 0.8}],
    }
    passages = [
        {"id": "p2", "title": "Second", "text": "Second retrieved passage.", "score": 0.9},
        {"id": "p1", "title": "First", "text": "First retrieved passage.", "score": 0.8},
    ]
    manifest = {
        "run_id": "source-run", "status": "completed", "dataset": "musique",
        "expected_question_ids": ["q1"], "results_sha256": "a" * 64,
        "inputs": {"queries_sha256": "queries-sha", "corpus_sha256": "corpus-sha",
                   "corpus_fingerprint": "fingerprint"},
        "embedding": {"model": {"name": "bge-m3:latest", "digest": "embedding-digest"}},
        "generation": {"reader_prompt_version": READER_PROMPT_VERSION,
                        "options": dict(GENERATION_OPTIONS),
                        "reader_template_sha256": "template-sha"},
        "retrieval": {"method": "cosine", "top_k": 2},
        "index_embedding": {"cache_build_provenance": {"build_run_id": "index-run"}},
    }
    return {"run_id": "source-run", "dataset": "musique", "rows": [row],
            "questions": [{"row": row, "retrieved_passages": passages}],
            "manifest": manifest}


class ReaderReplayTests(unittest.TestCase):
    def test_replay_source_accepts_historical_prompt_when_manifest_and_rows_match(self):
        payload = replay_payload()
        historical = "hipporag2-musique-one-shot-v5"
        payload["manifest"]["generation"]["reader_prompt_version"] = historical
        payload["rows"][0]["reader_prompt_version"] = historical
        self.assertEqual(validate_replay_source(payload), 2)

    def test_replay_source_requires_completed_consistent_full_ordered_contexts(self):
        payload = replay_payload()
        self.assertEqual(validate_replay_source(payload), 2)
        payload["questions"][0]["retrieved_passages"].reverse()
        with self.assertRaisesRegex(ValueError, "preserve saved retrieval order"):
            validate_replay_source(payload)

    def test_replay_source_rejects_changed_reader_options_and_missing_questions(self):
        payload = replay_payload()
        payload["manifest"]["generation"]["options"]["num_predict"] -= 1
        with self.assertRaisesRegex(ValueError, "fixed generation options"):
            validate_replay_source(payload)
        payload = replay_payload()
        payload["rows"].clear()
        with self.assertRaisesRegex(ValueError, "ordered expected IDs"):
            validate_replay_source(payload)

    def test_replay_run_preserves_exact_prompt_and_records_source_lineage(self):
        payload = replay_payload()
        with tempfile.TemporaryDirectory(prefix="reader-replay-test-") as temp:
            root = Path(temp)
            source_path = root / "source.jsonl"
            source_path.write_text("source", encoding="utf-8")
            source_path.with_suffix(".manifest.json").write_text("{}", encoding="utf-8")
            queries_path = root / "data" / "processed" / "musique" / "queries.json"
            queries_path.parent.mkdir(parents=True)
            queries_bytes = json.dumps([{"id": "q1", "question": "Who is the person?"}],
                                       ensure_ascii=False).encode("utf-8")
            queries_path.write_bytes(queries_bytes)
            payload["manifest"]["inputs"]["queries_sha256"] = hashlib.sha256(
                queries_bytes).hexdigest()

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"version": "test"}

            class FakeSession:
                def get(self, *_args, **_kwargs):
                    return FakeResponse()

                def close(self):
                    pass

            expected_messages = build_reader_messages(
                payload["rows"][0]["question"], payload["questions"][0]["retrieved_passages"]
            )
            expected_hash = hashlib.sha256(
                json.dumps(expected_messages, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            with (
                patch("scripts.replay_reader.ROOT", root),
                patch("scripts.replay_reader.prepare_payload", return_value=payload),
                patch("scripts.replay_reader.git_snapshot", return_value={"commit": "test"}),
                patch("scripts.replay_reader.model_info", return_value={
                    "name": "qwen2.5:7b", "digest": "generation-digest"}),
                patch("scripts.replay_reader.requests.Session", return_value=FakeSession()),
                patch("scripts.replay_reader.post_json", return_value={
                    "message": {"content": "Thought: Alice.\nAnswer: Alice"},
                    "prompt_eval_count": 100, "eval_count": 2,
                    "total_duration": 1000000, "load_duration": 100,
                    "eval_duration": 500000, "done": True, "done_reason": "stop",
                }) as post_json,
            ):
                output = run(source_path, "qwen2.5:7b")

            result = json.loads(output.read_text(encoding="utf-8").strip())
            manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result["reader_prompt_sha256"], expected_hash)
            self.assertEqual(result["retrieved"], payload["rows"][0]["retrieved"])
            self.assertEqual(result["context_source_run_id"], "source-run")
            self.assertIsNone(result["query_embedding_client_seconds"])
            self.assertIsNone(result["retrieval_seconds"])
            self.assertEqual(manifest["retrieval"]["context_source_results_sha256"],
                             "a" * 64)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(post_json.call_count, 1)
            self.assertEqual(post_json.call_args.args[1], "/api/chat")
            self.assertEqual(post_json.call_args.args[2]["messages"], expected_messages)


if __name__ == "__main__":
    unittest.main()
