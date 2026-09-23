import unittest

from scripts.evaluate_dense import answer_scores, evaluate, normalize_answer, recall_at_k


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
            {"run_id": "run-1", "dataset": "musique", "mode": "local-poc",
             "question_id": "q1", "answer": "Alice Smith", "top_k": 5,
             "retrieved": [{"id": "p1"}, {"id": "p2"}],
             "embedding_model": {"name": "bge-m3"},
             "generation_model": {"name": "qwen2.5:3b"}},
            {"run_id": "run-1", "dataset": "musique", "mode": "local-poc",
             "question_id": "q2", "answer": "wrong", "top_k": 5,
             "retrieved": [{"id": "p3"}],
             "embedding_model": {"name": "bge-m3"},
             "generation_model": {"name": "qwen2.5:3b"}},
        ]
        labels = [
            {"id": "q1", "answer": "Alice", "answer_aliases": ["Alice Smith"],
             "supporting_ids": ["p1", "p2"]},
            {"id": "q2", "answer": "right", "answer_aliases": [],
             "supporting_ids": ["p3", "p4"]},
        ]
        for row in rows:
            row.update(planned_question_ids=["q1", "q2"], reader_prompt_version="test",
                       generation_options={"temperature": 0})
        result = evaluate(rows, labels)
        self.assertEqual(result["questions_evaluated"], 2)
        self.assertEqual(result["em"], 0.5)
        self.assertAlmostEqual(result["token_f1"], 0.5)
        self.assertEqual(result["recall_at_k"], 0.75)

    def test_rejects_mixed_runs_and_missing_labels(self):
        row = {"run_id": "one", "dataset": "musique", "question_id": "q1",
               "answer": "A", "retrieved": [{"id": "p1"}]}
        with self.assertRaisesRegex(ValueError, "share one"):
            evaluate([row, {**row, "run_id": "two", "question_id": "q2"}], [])
        with self.assertRaisesRegex(ValueError, "No gold label"):
            evaluate([{**row, "planned_question_ids": ["q1"], "top_k": 5,
                       "embedding_model": {}, "generation_model": {},
                       "reader_prompt_version": "test", "generation_options": {}}], [], ["q1"])

    def test_rejects_incomplete_or_mixed_configuration_runs(self):
        row = {"run_id": "one", "dataset": "musique", "mode": "local-poc",
               "question_id": "q1", "planned_question_ids": ["q1", "q2"],
               "answer": "A", "top_k": 5, "retrieved": [{"id": "p1"}],
               "embedding_model": {}, "generation_model": {},
               "reader_prompt_version": "test", "generation_options": {}}
        labels = [{"id": qid, "answer": "A", "supporting_ids": ["p1"]}
                  for qid in ("q1", "q2")]
        with self.assertRaisesRegex(ValueError, "exactly match"):
            evaluate([row], labels)
        with self.assertRaisesRegex(ValueError, "mixed top_k"):
            evaluate([row, {**row, "question_id": "q2", "top_k": 10}], labels)

    def test_legacy_run_needs_explicit_expected_ids(self):
        row = {"run_id": "one", "dataset": "musique", "mode": "local-poc",
               "question_id": "q1", "answer": "A", "top_k": 5, "retrieved": [],
               "embedding_model": {}, "generation_model": {},
               "reader_prompt_version": "test", "generation_options": {}}
        labels = [{"id": "q1", "answer": "A", "supporting_ids": ["p1"]}]
        with self.assertRaisesRegex(ValueError, "required for legacy"):
            evaluate([row], labels)
        self.assertEqual(evaluate([row], labels, ["q1"])["questions_evaluated"], 1)

    def test_evaluation_recovers_inline_answer_marker_from_saved_raw_response(self):
        row = {"run_id": "one", "dataset": "musique", "mode": "local-poc",
               "question_id": "q1", "planned_question_ids": ["q1"], "answer": "",
               "answer_extraction_status": "missing_answer_marker",
               "raw_answer": "Reasoning ends here. Answer: Paris.", "top_k": 5,
               "retrieved": [{"id": "p1"}], "embedding_model": {}, "generation_model": {},
               "reader_prompt_version": "test", "generation_options": {}}
        labels = [{"id": "q1", "answer": "Paris", "supporting_ids": ["p1"]}]
        result = evaluate([row], labels)
        self.assertEqual(result["em"], 1.0)
        self.assertEqual(result["per_question"][0]["answer_extraction_status"], "ok")


if __name__ == "__main__":
    unittest.main()
