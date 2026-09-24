import unittest
import json
import tempfile
from pathlib import Path

from scripts.evaluate_dense import (answer_scores, evaluate, normalize_answer, recall_at_k,
                                    validate_manifest_file)


def valid_row(qid="q1", **updates):
    row = {"run_id": "one", "dataset": "musique", "mode": "local-poc",
           "question_id": qid, "planned_question_ids": [qid], "answer": "Paris",
           "answer_extraction_status": "ok", "raw_answer": "Thought\nAnswer: Paris",
           "top_k": 5, "retrieved": [{"id": "p1"}],
           "embedding_model": {"name": "bge-m3", "digest": "e"},
           "generation_model": {"name": "qwen2.5:3b", "digest": "g"},
           "reader_prompt_version": "hipporag2-musique-one-shot-v5",
           "generation_options": {"temperature": 0, "seed": 42,
                                   "num_predict": 512, "num_ctx": 4096},
           "done_reason": "stop", "done": True}
    row.update(updates)
    return row


def valid_manifest(ids=("q1",), **updates):
    manifest = {"run_id": "one", "status": "completed",
                "expected_question_ids": list(ids), "index_embedding": {}}
    manifest.update(updates)
    return manifest


class DenseEvaluationTests(unittest.TestCase):
    def test_squad_style_normalization(self):
        self.assertEqual(normalize_answer("The U.S. is a country!"), "us is country")

    def test_alias_can_match_exactly_and_partial_answer_gets_token_f1(self):
        scores = answer_scores("Alice Smith", ["Alicia Smith", "Alice Smith"])
        self.assertEqual(scores, {"em": 1.0, "f1": 1.0})
        partial = answer_scores("Alice", ["Alice Smith"])
        self.assertEqual(partial["em"], 0.0)
        self.assertAlmostEqual(partial["f1"], 2 / 3)

    def test_recall_at_k_uses_only_first_k_and_counts_distinct_supporting_passages(self):
        self.assertEqual(recall_at_k(["other", "other", "x", "y", "z", "a"], ["a", "b"], 5), 0.0)
        self.assertEqual(recall_at_k(["a", "a", "other"], ["a", "b"], 5), 0.5)

    def test_empty_answer_f1_matches_hipporag(self):
        self.assertEqual(answer_scores("", [""]) ["f1"], 0.0)

    def test_evaluation_aggregates_answer_and_retrieval_metrics(self):
        rows = [
            valid_row("q1", run_id="run-1", answer="Alice Smith",
                      retrieved=[{"id": "p1"}, {"id": "p2"}]),
            valid_row("q2", run_id="run-1", answer="wrong", retrieved=[{"id": "p3"}]),
        ]
        labels = [
            {"id": "q1", "answer": "Alice", "answer_aliases": ["Alice Smith"],
             "supporting_ids": ["p1", "p2"]},
            {"id": "q2", "answer": "right", "answer_aliases": [],
             "supporting_ids": ["p3", "p4"]},
        ]
        for row in rows:
            row.update(planned_question_ids=["q1", "q2"], reader_prompt_version="test")
        result = evaluate(rows, labels)
        self.assertEqual(result["questions_evaluated"], 2)
        self.assertEqual(result["em"], 0.5)
        self.assertAlmostEqual(result["token_f1"], 0.5)
        self.assertEqual(result["recall_at_k"], 0.75)

    def test_rejects_mixed_runs_and_missing_labels(self):
        row = valid_row("q1", answer="A")
        with self.assertRaisesRegex(ValueError, "share one"):
            evaluate([row, {**row, "run_id": "two", "question_id": "q2"}], [])
        with self.assertRaisesRegex(ValueError, "No gold label"):
            evaluate([{**row, "planned_question_ids": ["q1"]}], [], ["q1"])

    def test_rejects_incomplete_or_mixed_configuration_runs(self):
        row = valid_row("q1", planned_question_ids=["q1", "q2"], answer="A")
        labels = [{"id": qid, "answer": "A", "supporting_ids": ["p1"]}
                  for qid in ("q1", "q2")]
        with self.assertRaisesRegex(ValueError, "exactly match"):
            evaluate([row], labels)
        with self.assertRaisesRegex(ValueError, "mixed top_k"):
            evaluate([row, {**row, "question_id": "q2", "top_k": 10}], labels)

    def test_legacy_run_needs_explicit_expected_ids(self):
        row = valid_row("q1", planned_question_ids=None, answer="A")
        labels = [{"id": "q1", "answer": "A", "supporting_ids": ["p1"]}]
        with self.assertRaisesRegex(ValueError, "required for legacy"):
            evaluate([row], labels)
        self.assertEqual(evaluate([row], labels, ["q1"])["questions_evaluated"], 1)

    def test_evaluation_recovers_inline_answer_marker_from_saved_raw_response(self):
        row = valid_row("q1", answer="", answer_extraction_status="missing_answer_marker",
                        raw_answer="Reasoning ends here. Answer: Paris.")
        labels = [{"id": "q1", "answer": "Paris", "supporting_ids": ["p1"]}]
        result = evaluate([row], labels)
        self.assertEqual(result["em"], 1.0)
        self.assertEqual(result["per_question"][0]["answer_extraction_status"], "ok")

    def test_evaluation_reports_phase_usage_and_unknown_index_usage_as_null(self):
        row = valid_row("q1", prompt_tokens=12, completion_tokens=3,
                        query_embedding_prompt_tokens=4,
                        query_embedding_client_seconds=0.2,
                        retrieval_seconds=0.01, generation_wall_seconds=0.4,
                        generation_seconds=0.35, question_end_to_end_seconds=0.7,
                        generation_tokens_per_second=8.0,
                        context_source_run_id="retrieval-source")
        label = {"id": "q1", "answer": "Paris", "supporting_ids": ["p1"]}
        manifest = valid_manifest(index_embedding={
            "embedding_prompt_tokens": 100, "build_seconds_this_run": 10.0,
            "cache_read_seconds": None,
            "cache_build_provenance": {
                "build_run_id": "index-build-1", "build_seconds": 78.764,
                "embedding_prompt_tokens": None, "api_total_duration_ns": None,
            }}, retrieval={"context_source_run_id": "retrieval-source"})
        result = evaluate([row], [label], manifest=manifest)
        self.assertEqual(result["generation_stopped_normally"], 1)
        self.assertEqual(result["context_source_run_id"], "retrieval-source")
        self.assertEqual(result["usage"]["index_embedding_prompt_tokens"], 100)
        self.assertEqual(result["usage"]["generation_prompt_tokens"], 12)
        self.assertEqual(result["usage"]["generation_completion_tokens"], 3)
        self.assertEqual(result["usage"]["retrieval_seconds"], 0.01)
        self.assertIsNone(result["usage"]["index_embedding_cache_read_seconds"])
        self.assertEqual(result["usage"]["index_embedding_original_build_run_id"],
                         "index-build-1")
        self.assertEqual(result["usage"]["index_embedding_original_build_seconds"], 78.764)
        self.assertIsNone(result["usage"]["index_embedding_original_prompt_tokens"])
        self.assertIsNone(result["usage"]["index_embedding_original_api_total_duration_ns"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            evaluate([row], [label], manifest=valid_manifest(run_id="other"))

    def test_manifest_defines_complete_denominator_and_rejects_partial_run(self):
        row = valid_row("q1")
        labels = [{"id": q, "answer": "Paris", "supporting_ids": ["p1"]}
                  for q in ("q1", "q2")]
        with self.assertRaisesRegex(ValueError, "exactly match"):
            evaluate([row], labels, manifest=valid_manifest(("q1", "q2")))

    def test_manifest_must_be_completed_and_failed_answers_remain_in_denominator(self):
        row = valid_row("q1", answer="", answer_extraction_status="ambiguous_answer_marker",
                        done_reason="length")
        label = {"id": "q1", "answer": "Paris", "supporting_ids": ["p1"]}
        result = evaluate([row], [label], manifest=valid_manifest())
        self.assertEqual(result["questions_evaluated"], 1)
        self.assertEqual(result["em"], 0.0)
        self.assertEqual(result["token_f1"], 0.0)
        self.assertEqual(result["generation_stopped_normally"], 0)
        with self.assertRaisesRegex(ValueError, "status must be completed"):
            evaluate([row], [label], manifest=valid_manifest(status="failed"))

    def test_rejects_missing_generation_configuration_and_incomplete_response(self):
        label = {"id": "q1", "answer": "Paris", "supporting_ids": ["p1"]}
        with self.assertRaisesRegex(ValueError, "missing required reader_prompt_version"):
            evaluate([valid_row("q1", reader_prompt_version=None)], [label], ["q1"])
        with self.assertRaisesRegex(ValueError, "incomplete generation"):
            evaluate([valid_row("q1", done=False)], [label], ["q1"])
        with self.assertRaisesRegex(ValueError, "done=true"):
            evaluate([valid_row("q1", done=None)], [label], ["q1"])
        with self.assertRaisesRegex(ValueError, "must include temperature"):
            evaluate([valid_row("q1", generation_options={"seed": 42})], [label], ["q1"])
        with self.assertRaisesRegex(ValueError, "answer string"):
            evaluate([valid_row("q1", answer=None)], [label], ["q1"])

    def test_manifest_file_hash_and_run_id_are_verified(self):
        row = valid_row("q1")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            content = (json.dumps(row) + "\n").encode()
            path.write_bytes(content)
            manifest = valid_manifest(results_sha256=__import__("hashlib").sha256(content).hexdigest())
            self.assertEqual(validate_manifest_file(path, [row], manifest), ["q1"])
            with self.assertRaisesRegex(ValueError, "results hash"):
                validate_manifest_file(path, [row], valid_manifest(results_sha256="bad"))


if __name__ == "__main__":
    unittest.main()
