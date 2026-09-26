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
                               embed_corpus, normalize_rows, recover_cache_build_provenance,
                               require_completed_generation, run, top_k, validate_processed_data,
                               DEMO_USER, DEMO_ASSISTANT, READER_SYSTEM, READER_PROMPT_VERSION,
                               PROMPT_SOURCE_COMMIT, reader_template_sha256)
from scripts.vendor.hipporag2_musique_template import prompt_template
from scripts.evaluation_view import load_view, ordered_ids_sha256, select_in_view


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
    def test_frozen_view_selects_exact_order_and_checks_ids_and_labels_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            labels = root / "labels.json"
            labels.write_text("[]", encoding="utf-8")
            view_path = root / "view.json"
            question_ids = ["q2", "q1"]
            view_path.write_text(json.dumps({
                "dataset": "musique", "view": "candidate",
                "question_ids": question_ids,
                "ordered_question_ids_sha256": ordered_ids_sha256(question_ids),
                "labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
            }), encoding="utf-8")

            metadata = load_view(view_path, "musique", labels)
            selected = select_in_view([{"id": "q1"}, {"id": "q2"}],
                                      metadata["question_ids"], "query")

            self.assertEqual([row["id"] for row in selected], question_ids)
            view_path.write_text(view_path.read_text(encoding="utf-8").replace(
                '"q2", "q1"', '"q1", "q2"'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ordered ID hash"):
                load_view(view_path, "musique", labels)

    def test_frozen_view_refuses_missing_and_duplicate_source_ids(self):
        with self.assertRaisesRegex(ValueError, "unknown query IDs"):
            select_in_view([{"id": "q1"}], ["q2"], "query")
        with self.assertRaisesRegex(ValueError, "Duplicate query ID"):
            select_in_view([{"id": "q1"}, {"id": "q1"}], ["q1"], "query")

    def test_reader_messages_match_pinned_upstream_template_exactly(self):
        question = "Who is the professor?"
        passages = [{"title": "Person", "text": "A professor."}]
        messages = build_reader_messages(question, passages)
        upstream = [
            {"role": item["role"],
             "content": item["content"].replace("${prompt_user}", messages[-1]["content"])}
            for item in prompt_template
        ]
        self.assertEqual(messages, upstream)
        self.assertEqual(READER_PROMPT_VERSION, "hipporag2-musique-one-shot-v6")
        self.assertEqual(len(reader_template_sha256()), 64)
        self.assertEqual(READER_SYSTEM, prompt_template[0]["content"])
        self.assertEqual(DEMO_USER, prompt_template[1]["content"])
        self.assertEqual(DEMO_ASSISTANT, prompt_template[2]["content"])

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
        self.assertTrue(messages[-1]["content"].endswith("Thought: "))
        self.assertTrue(messages[1]["content"].endswith("Thought: "))
        self.assertIn("The person is Alice.", messages[-1]["content"])
        self.assertIn("This is another passage.", messages[-1]["content"])
        self.assertNotIn("Alice Smith", messages[-1]["content"])
        self.assertEqual(PROMPT_SOURCE_COMMIT, "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff")
        self.assertIn("Distributed by Buena Vista Pictures Distribution", DEMO_USER)
        self.assertNotIn("\n\nWikipedia Title:", DEMO_USER)

    def test_hipporag_musique_reader_refuses_unvalidated_hotpotqa_template(self):
        with self.assertRaisesRegex(ValueError, "validated only for MuSiQue"):
            run("hotpotqa")

    def test_answer_extraction_requires_explicit_answer_marker(self):
        self.assertEqual(extract_reader_answer("Thought: Some reasoning.\nAnswer: Paris."),
                         ("Paris.", "ok"))
        self.assertEqual(extract_reader_answer("Some reasoning. Answer: Paris."),
                         ("Paris.", "ok"))
        self.assertEqual(extract_reader_answer("No marker"), ("", "missing_answer_marker"))
        self.assertEqual(extract_reader_answer("Answer: Paris\nAnswer: London"),
                         ("", "ambiguous_answer_marker"))

    def test_generation_must_report_completion_before_run_can_finish(self):
        require_completed_generation({"done": True, "done_reason": "stop"}, "q1")
        with self.assertRaisesRegex(RuntimeError, "did not report a completed response"):
            require_completed_generation({"done": False, "done_reason": "length"}, "q1")
        with self.assertRaisesRegex(RuntimeError, "did not report a completed response"):
            require_completed_generation({"done": True}, "q1")

    def test_embedding_cache_records_and_checks_no_truncation_policy(self):
        corpus = [{"id": "p1", "title": "A", "text": "first"},
                  {"id": "p2", "title": "B", "text": "second"}]
        with tempfile.TemporaryDirectory(prefix="dense-cache-test-", dir=ROOT / "indexes" / "dense") as temp:
            cache = Path(temp) / "cache.npz"
            first_session = FakeEmbeddingSession()
            first_vectors, first_stats = embed_corpus(
                first_session, corpus, cache, corpus_fingerprint(corpus), "digest",
                dataset="test", build_run_id="cache-test-run",
            )
            self.assertEqual(first_vectors.shape, (2, 2))
            self.assertFalse(first_stats["cache_hit"])
            self.assertIsNone(first_stats["embedding_prompt_tokens"])
            self.assertEqual(first_stats["cache_build_provenance"]["build_run_id"],
                             "cache-test-run")
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
            self.assertEqual(cached_stats["cache_build_provenance"]["build_run_id"],
                             "cache-test-run")
            np.testing.assert_array_equal(cached_vectors, first_vectors)

    def test_historical_cache_provenance_requires_completed_hash_verified_run(self):
        fingerprint = "corpus-fingerprint"
        digest = "embedding-model-digest"
        run_id = "historical-run"
        with tempfile.TemporaryDirectory(prefix="dense-provenance-test-") as temp:
            root = Path(temp)
            cache = root / "indexes" / "dense" / "cache.npz"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"cache bytes")
            raw_dir = root / "results" / "raw"
            raw_dir.mkdir(parents=True)
            result_name = "dense-musique-historical-run.jsonl"
            result_path = raw_dir / result_name
            result_bytes = b'{"run_id":"historical-run"}\n'
            result_path.write_bytes(result_bytes)
            manifest = {
                "run_id": run_id, "status": "completed", "dataset": "musique",
                "results_file": result_name,
                "results_sha256": hashlib.sha256(result_bytes).hexdigest(),
                "inputs": {"corpus_fingerprint": fingerprint},
                "embedding": {
                    "cache_file": "indexes/dense/cache.npz", "text_version": EMBED_TEXT_VERSION,
                    "truncate": EMBED_TRUNCATE, "cache_schema": EMBED_CACHE_SCHEMA_VERSION,
                    "model": {"digest": digest},
                },
                "index_embedding_seconds_this_run": 78.764,
            }
            manifest_path = raw_dir / "dense-musique-historical-run.manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch("scripts.run_dense.ROOT", root):
                provenance = recover_cache_build_provenance(cache, fingerprint, digest)
                self.assertEqual(provenance["build_run_id"], run_id)
                self.assertEqual(provenance["build_seconds"], 78.764)
                self.assertIsNone(provenance["embedding_prompt_tokens"])
                result_path.write_bytes(b"changed results")
                self.assertIsNone(recover_cache_build_provenance(cache, fingerprint, digest))

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
