import unittest
from pathlib import Path
import tempfile
import hashlib
import json
from unittest.mock import patch

import numpy as np

from scripts.answer_parser import extract_reader_answer
from scripts.run_dense import (EMBED_CACHE_SCHEMA_VERSION, EMBED_TEXT_VERSION,
                               EMBED_TRUNCATE, ROOT, build_reader_messages, corpus_fingerprint,
                               embed_corpus, normalize_rows, top_k, validate_processed_data)


class FakeEmbeddingResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeEmbeddingSession:
    def __init__(self):
        self.payloads = []

    def post(self, _url, json, timeout):
        self.payloads.append(json)
        return FakeEmbeddingResponse({"embeddings": [[1.0, 0.0] for _ in json["input"]]})


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
        self.assertEqual(extract_reader_answer("Some reasoning. Answer: Paris."),
                         ("Paris.", "ok"))
        self.assertEqual(extract_reader_answer("No marker"), ("", "missing_answer_marker"))

    def test_embedding_cache_records_and_checks_no_truncation_policy(self):
        corpus = [{"id": "p1", "title": "A", "text": "first"},
                  {"id": "p2", "title": "B", "text": "second"}]
        with tempfile.TemporaryDirectory(prefix="dense-cache-test-", dir=ROOT / "indexes" / "dense") as temp:
            cache = Path(temp) / "cache.npz"
            first_session = FakeEmbeddingSession()
            first_vectors, first_stats = embed_corpus(
                first_session, corpus, cache, corpus_fingerprint(corpus), "digest"
            )
            self.assertEqual(first_vectors.shape, (2, 2))
            self.assertFalse(first_stats["cache_hit"])
            self.assertIsNone(first_stats["embedding_prompt_tokens"])
            self.assertTrue(all(payload["truncate"] is EMBED_TRUNCATE
                                for payload in first_session.payloads))
            with np.load(cache, allow_pickle=False) as saved:
                self.assertEqual(int(saved["cache_schema"].item()), EMBED_CACHE_SCHEMA_VERSION)
                self.assertEqual(str(saved["text_version"].item()), EMBED_TEXT_VERSION)
                self.assertFalse(bool(saved["truncate"].item()))

            class NoNetworkSession:
                def post(self, *_args, **_kwargs):
                    raise AssertionError("A valid cache should avoid embedding API calls")

            cached_vectors, cached_stats = embed_corpus(
                NoNetworkSession(), corpus, cache, corpus_fingerprint(corpus), "digest"
            )
            self.assertTrue(cached_stats["cache_hit"])
            self.assertIsNone(cached_stats["embedding_prompt_tokens"])
            np.testing.assert_array_equal(cached_vectors, first_vectors)

    def test_processed_data_must_match_pinned_hashes_and_id_manifests(self):
        queries = [{"id": "q1", "question": "Question?"}]
        corpus = [{"id": "p1", "title": "Title", "text": "Passage"}]
        with tempfile.TemporaryDirectory(prefix="dense-data-test-") as temp:
            root = Path(temp)
            data_dir = root / "data" / "processed" / "musique"
            data_dir.mkdir(parents=True)
            (root / "data" / "ids").mkdir()
            (root / "results" / "data").mkdir(parents=True)
            payloads = {"queries.json": json.dumps(queries).encode(),
                        "corpus.json": json.dumps(corpus).encode()}
            for filename, payload in payloads.items():
                (data_dir / filename).write_bytes(payload)
            ids_manifest = {"question_ids": ["q1"], "passage_ids": ["p1"],
                            "source_revision": "test-revision"}
            (root / "data" / "ids" / "musique_s500.json").write_text(
                json.dumps(ids_manifest), encoding="utf-8")
            integrity_report = {"datasets": {"musique": {"output_sha256": {
                name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()
            }}}}
            (root / "results" / "data" / "subsamples.json").write_text(
                json.dumps(integrity_report), encoding="utf-8")
            with patch("scripts.run_dense.ROOT", root):
                self.assertEqual(validate_processed_data("musique", data_dir, queries, corpus)
                                 ["source_revision"], "test-revision")
                (data_dir / "queries.json").write_text(
                    json.dumps([{"id": "q1", "question": "Edited"}]), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "pinned subsample report"):
                    validate_processed_data("musique", data_dir, queries, corpus)


if __name__ == "__main__":
    unittest.main()
