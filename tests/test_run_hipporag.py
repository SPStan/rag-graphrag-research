import unittest
import json
import tempfile
import threading
from pathlib import Path

from scripts.run_hipporag import (normalize_inputs, parse_args, passage_id,
                                  normalize_ner_entities, summarize_usage,
                                  persist_interrupted_run, windows_safe_model_label)


class HippoRAGRunnerTests(unittest.TestCase):
    def test_interrupted_run_manifest_persists_status_and_partial_usage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "run.manifest.json"
            manifest = {"status": "initializing"}
            events = [{"stage": "openie_triples", "usage": {"prompt_tokens": 5}}]

            persist_interrupted_run(manifest, path, events, threading.Lock())

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "interrupted")
            self.assertEqual(saved["error_type"], "KeyboardInterrupt")
            self.assertEqual(saved["usage_events"], events)
            self.assertIn("interrupted_at", saved)

    def test_object_shaped_ner_items_keep_entity_names_not_labels(self):
        self.assertEqual(
            normalize_ner_entities([
                "Alice", {"entity": "Bob", "type": "person"},
                {"Athlete": "Carol", "Sport": "Tennis"}, "Alice"
            ]),
            ["Alice", "Bob", "Carol", "Tennis"],
        )

    def test_corpus_and_queries_must_be_explicit(self):
        with self.assertRaises(SystemExit):
            parse_args([])

        args = parse_args(["--corpus", "corpus.json", "--queries", "queries.json"])
        self.assertEqual(str(args.corpus), "corpus.json")
        self.assertEqual(str(args.queries), "queries.json")

    def test_upstream_sample_schema_builds_support_labels_after_input_normalization(self):
        corpus = [
            {"title": "A", "text": "  First   supporting passage.\nMore text. "},
            {"title": "B", "text": "Distractor passage."},
        ]
        queries = [{
            "id": "sample/q1", "question": "Who is named?", "answer": ["Alice"],
            "paragraphs": [
                {"title": "A", "text": "First supporting passage. More text.",
                 "is_supporting": True},
                {"title": "B", "text": "Distractor passage.", "is_supporting": False},
            ],
        }]

        normalized_corpus, normalized_queries, labels = normalize_inputs(corpus, queries)

        self.assertEqual(normalized_queries, [{"id": "sample/q1", "question": "Who is named?"}])
        self.assertEqual(labels[0]["answer"], "Alice")
        self.assertEqual(labels[0]["supporting_ids"], [passage_id("A", "First supporting passage. More text.")])
        self.assertEqual(len(normalized_corpus), 2)

    def test_separate_labels_are_matched_by_id_and_not_added_to_queries(self):
        corpus = [{"id": "p1", "title": "A", "text": "Passage."}]
        queries = [{"id": "q1", "question": "Question?"}]
        labels = [{"id": "q1", "answer": "Answer", "answer_aliases": [], "supporting_ids": ["p1"]}]

        _, clean_queries, normalized_labels = normalize_inputs(corpus, queries, labels)

        self.assertNotIn("answer", clean_queries[0])
        self.assertEqual(normalized_labels, labels)

    def test_missing_supporting_passage_is_rejected(self):
        corpus = [{"title": "B", "text": "Not the support."}]
        queries = [{"id": "q1", "question": "Question?", "answer": "Answer",
                    "paragraphs": [{"title": "A", "text": "Missing.", "is_supporting": True}]}]
        with self.assertRaisesRegex(ValueError, "absent from corpus"):
            normalize_inputs(corpus, queries)

    def test_windows_model_labels_replace_path_separators_and_colons(self):
        self.assertEqual(windows_safe_model_label("qwen2.5:3b"), "qwen2.5_3b")
        self.assertEqual(windows_safe_model_label("org/model:tag"), "org_model_tag")

    def test_usage_summary_separates_api_usage_from_cached_replays(self):
        corpus = [{"id": "p1", "title": "A", "text": "Passage."}]
        events = [
            {"kind": "embedding", "stage": "index_embedding", "usage": {"prompt_tokens": 8},
             "items": [{"passage_id": "p1"}]},
            {"kind": "chat", "stage": "openie_ner", "passage_id": "p1", "cache_hit": False,
             "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
            {"kind": "chat", "stage": "openie_ner", "passage_id": "p1", "cache_hit": True,
             "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
        ]

        summary = summarize_usage(events, corpus)

        self.assertEqual(summary["phases"]["openie_ner"]["api_prompt_tokens"], 12)
        self.assertEqual(summary["phases"]["openie_ner"]["cached_prompt_tokens"], 12)
        self.assertEqual(summary["per_passage"]["p1"]["passage_embedding_tokens"], 8)
        self.assertEqual(summary["per_passage"]["p1"]["openie_prompt_tokens"], 12)
        self.assertEqual(summary["per_passage"]["p1"]["openie_cached_prompt_tokens"], 12)


if __name__ == "__main__":
    unittest.main()
