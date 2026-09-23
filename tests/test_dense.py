import unittest

import numpy as np

from scripts.run_dense import (build_reader_messages, extract_reader_answer,
                               normalize_rows, top_k)


class DenseRetrievalTests(unittest.TestCase):
    def test_top_k_uses_cosine_similarity_and_returns_descending_order(self):
        documents = np.asarray([[10, 0], [1, 1], [0, 5]], dtype=np.float32)
        ranked = top_k([1, 0], documents, 3)
        self.assertEqual([index for index, _score in ranked], [0, 1, 2])
        self.assertAlmostEqual(ranked[0][1], 1.0)
        self.assertAlmostEqual(ranked[1][1], 2 ** -0.5, places=6)
        self.assertAlmostEqual(ranked[2][1], 0.0)

    def test_top_k_is_stable_for_equal_scores(self):
        ranked = top_k([1, 0], [[1, 1], [2, 2], [0, 1]], 2)
        self.assertEqual([index for index, _score in ranked], [0, 1])

    def test_rejects_mismatched_dimensions_and_zero_vectors(self):
        with self.assertRaisesRegex(ValueError, "dimensions differ"):
            top_k([1, 0, 0], [[1, 0]], 1)
        with self.assertRaisesRegex(ValueError, "non-zero"):
            normalize_rows([[0, 0]])

    def test_top_k_requires_positive_k(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            top_k([1, 0], [[1, 0]], 0)

    def test_reader_messages_follow_hipporag_roles_and_include_only_selected_passages(self):
        messages = build_reader_messages("Who is the person?", [
            {"title": "First", "text": "The person is Alice."},
            {"title": "Second", "text": "This is another passage."},
        ])
        self.assertEqual([message["role"] for message in messages],
                         ["system", "user", "assistant", "user"])
        self.assertIn("Question: Who is the person?", messages[-1]["content"])
        self.assertIn("The person is Alice.", messages[-1]["content"])
        self.assertIn("This is another passage.", messages[-1]["content"])
        self.assertNotIn("Alice Smith", messages[-1]["content"])

    def test_answer_extraction_requires_explicit_answer_marker(self):
        self.assertEqual(extract_reader_answer("Thought: Some reasoning.\nAnswer: Paris."),
                         ("Paris.", "ok"))
        self.assertEqual(extract_reader_answer("No marker"), ("", "missing_answer_marker"))


if __name__ == "__main__":
    unittest.main()
