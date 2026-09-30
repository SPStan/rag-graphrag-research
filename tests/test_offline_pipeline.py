"""Exercise retrieval -> actual reader formatting -> parsing -> scoring, offline."""

import unittest

from scripts.answer_parser import extract_reader_answer
from scripts.evaluate_dense import evaluate
from scripts.run_dense import (
    GENERATION_OPTIONS,
    READER_PROMPT_VERSION,
    build_reader_messages,
    top_k,
)


class OfflinePipelineTests(unittest.TestCase):
    def test_retrieval_to_scoring_on_synthetic_corpus(self):
        corpus = [
            {"id": "p1", "title": "Lena", "text": "Lena designed the bridge."},
            {"id": "p2", "title": "Weather", "text": "It rained yesterday."},
        ]
        ranked = top_k([1, 0], [[1, 0], [0, 1]], k=1)
        passages = [corpus[i] for i, _ in ranked]
        messages = build_reader_messages("Who designed the bridge?", passages)
        # Deterministic fake reader response. No model or network involved.
        self.assertIn("Lena designed", messages[-1]["content"])
        self.assertNotIn("rained", messages[-1]["content"])
        self.assertNotIn("supporting_ids", messages[-1]["content"])
        raw = "Thought: The passage names the designer.\nAnswer: Lena"
        answer, status = extract_reader_answer(raw)
        row = {
            "run_id": "synthetic",
            "dataset": "sample",
            "mode": "mock",
            "question_id": "q1",
            "planned_question_ids": ["q1"],
            "top_k": 1,
            "embedding_model": {"name": "fake-embedding"},
            "generation_model": {"name": "fake-reader"},
            "reader_prompt_version": READER_PROMPT_VERSION,
            "generation_options": GENERATION_OPTIONS,
            "answer": answer,
            "answer_extraction_status": status,
            "raw_answer": raw,
            "done": True,
            "done_reason": "stop",
            "retrieved": [{"id": passages[0]["id"]}],
        }
        # Labels are introduced only after the reader step.
        labels = [{"id": "q1", "answer": "Lena", "supporting_ids": ["p1"]}]
        metrics = evaluate([row], labels)
        self.assertEqual(metrics["em"], 1)
        self.assertEqual(metrics["token_f1"], 1)
        self.assertEqual(metrics["recall_at_k"], 1)


if __name__ == "__main__":
    unittest.main()
