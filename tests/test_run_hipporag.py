import unittest
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import requests

from scripts.run_hipporag import (normalize_inputs, parse_args, passage_id,
                                  normalize_ner_entities, summarize_usage,
                                  persist_interrupted_run, windows_safe_model_label,
                                  record_openie_failure, instrument_models,
                                  build_shared_reader_messages, install_shared_reader_template,
                                  run_shared_reader, git_snapshot,
                                  install_no_truncate_embedding_api, ollama_api_base)
from scripts.run_dense import build_reader_messages


class HippoRAGRunnerTests(unittest.TestCase):
    def test_git_snapshot_works_with_workspace_safe_directory_override(self):
        snapshot = git_snapshot()

        self.assertRegex(snapshot["commit"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(snapshot["dirty"], bool)
        self.assertIn("scripts/run_hipporag.py", snapshot["source_sha256"])

    def test_native_embedding_request_disables_truncation_and_checks_vectors(self):
        calls = []
        embedding_model = SimpleNamespace(
            global_config=SimpleNamespace(embedding_request_timeout=5),
            last_usage=None,
        )

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"embeddings": [[3.0, 4.0]], "prompt_eval_count": 7,
                        "total_duration": 11, "load_duration": 2}

        def post_json(url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        endpoint = install_no_truncate_embedding_api(
            embedding_model, "http://localhost:11434/v1/", "bge-m3:latest",
            post_json=post_json,
        )
        vector = embedding_model.encode(["title\ntext"])

        self.assertEqual(ollama_api_base("http://localhost:11434/v1"),
                         "http://localhost:11434")
        self.assertEqual(endpoint, "http://localhost:11434/api/embed")
        self.assertEqual(calls[0][1]["json"]["truncate"], False)
        self.assertEqual(calls[0][1]["json"]["input"], ["title text"])
        self.assertEqual(vector.tolist(), [[3.0, 4.0]])
        self.assertEqual(embedding_model.last_usage["prompt_tokens"], 7)
        self.assertFalse(embedding_model.last_usage["truncate"])

        class ZeroResponse(Response):
            def json(self):
                return {"embeddings": [[0.0, 0.0]], "prompt_eval_count": 7}

        install_no_truncate_embedding_api(
            embedding_model, "http://localhost:11434/v1", "bge-m3:latest",
            post_json=lambda *_args, **_kwargs: ZeroResponse(),
        )
        with self.assertRaisesRegex(RuntimeError, "zero embeddings"):
            embedding_model.encode(["passage"])

    def test_native_embedding_splits_rejected_batches_and_aggregates_usage(self):
        calls = []
        embedding_model = SimpleNamespace(
            global_config=SimpleNamespace(embedding_request_timeout=5),
            last_usage=None,
        )

        class Response:
            def __init__(self, inputs):
                self.inputs = inputs
                self.status_code = 200

            def raise_for_status(self):
                if len(self.inputs) > 2:
                    self.status_code = 400
                    error = requests.HTTPError("bad batch")
                    error.response = self
                    raise error

            def json(self):
                return {"embeddings": [[float(len(text)), 1.0] for text in self.inputs],
                        "prompt_eval_count": len(self.inputs),
                        "total_duration": 10, "load_duration": 2}

        def post_json(_url, **kwargs):
            inputs = kwargs["json"]["input"]
            calls.append(inputs)
            return Response(inputs)

        install_no_truncate_embedding_api(
            embedding_model, "http://localhost:11434/v1", "bge-m3:latest",
            post_json=post_json,
        )
        vectors = embedding_model.encode(["one", "two", "three", "four"])

        self.assertEqual(len(calls), 3)
        self.assertEqual(vectors[:, 0].tolist(), [3.0, 3.0, 5.0, 4.0])
        self.assertEqual(embedding_model.last_usage["prompt_tokens"], 4)
        self.assertEqual(embedding_model.last_usage["total_duration_ns"], 20)

    def test_shared_reader_messages_match_dense_exactly(self):
        passages = [
            {"title": "First", "text": "Evidence one."},
            {"title": "Second", "text": "Evidence two."},
        ]
        question = "What is the answer?"

        self.assertEqual(
            build_shared_reader_messages(question, passages),
            build_reader_messages(question, passages),
        )

    def test_shared_reader_template_installs_dense_demo_messages(self):
        rag = SimpleNamespace(
            prompt_template_manager=SimpleNamespace(templates={})
        )

        digest = install_shared_reader_template(rag)

        template = rag.prompt_template_manager.templates["rag_qa_musique"]
        rendered = [item["content"].template for item in template]
        self.assertEqual(len(rendered), 4)
        self.assertEqual(rendered[-1], "${prompt_user}")
        self.assertTrue(digest)

    def test_shared_reader_disables_json_mode_and_uses_common_answer_parser(self):
        qa_llm = SimpleNamespace(global_config=SimpleNamespace(
            response_format={"type": "json_object"}), infer=lambda *args, **kwargs: None)
        infer_calls = []
        qa_llm.infer = lambda *args, **kwargs: infer_calls.append(kwargs.copy())
        solution = SimpleNamespace(answer="old")

        def original_qa(solutions):
            self.assertIsNone(qa_llm.global_config.response_format)
            qa_llm.infer(messages=[])
            return solutions, ["Thought.\nAnswer: 42\n"], [{"finish_reason": "stop"}]

        solutions, raw_answers, metadata = run_shared_reader(
            original_qa, qa_llm, [solution])

        self.assertEqual(solutions[0].answer, "42")
        self.assertEqual(raw_answers, ["Thought.\nAnswer: 42\n"])
        self.assertEqual(metadata[0]["answer_extraction_status"], "ok")
        self.assertEqual(qa_llm.global_config.response_format, {"type": "json_object"})
        self.assertEqual(infer_calls, [{"messages": [], "_bypass_cache": True}])

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

    def test_openie_failure_records_passage_and_error_without_source_text(self):
        failures = []
        lock = threading.Lock()
        failure = record_openie_failure(
            failures, lock, "sha256:passage-id", RuntimeError("token repeat limit reached"),
            "openie_triples")

        self.assertEqual(failure["passage_id"], "sha256:passage-id")
        self.assertEqual(failure["stage"], "openie_triples")
        self.assertEqual(failure["error_type"], "RuntimeError")
        self.assertEqual(len(failures), 1)
        self.assertNotIn("passage_text", failure)

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

    def test_batched_embedding_tokens_are_not_falsely_attributed_per_passage(self):
        corpus = [
            {"id": "p1", "title": "A", "text": "One."},
            {"id": "p2", "title": "B", "text": "Two."},
        ]
        summary = summarize_usage([{
            "kind": "embedding", "stage": "index_embedding", "batch_size": 2,
            "usage": {"prompt_tokens": 17},
            "items": [{"passage_id": "p1"}, {"passage_id": "p2"}],
        }], corpus)

        self.assertEqual(summary["phases"]["index_embedding"]["api_embedding_tokens"], 17)
        for passage_id in ("p1", "p2"):
            row = summary["per_passage"][passage_id]
            self.assertIsNone(row["passage_embedding_tokens"])
            self.assertFalse(row["passage_embedding_usage_attributed"])
            self.assertEqual(row["embedding_batches"], 1)

    def test_embedding_request_batch_usage_is_not_falsely_attributed_per_passage(self):
        corpus = [
            {"id": "p1", "title": "A", "text": "One."},
            {"id": "p2", "title": "B", "text": "Two."},
        ]

        class FakeEmbedding:
            last_usage = None

            def encode(self, texts):
                token_total = sum(len(text) for text in texts)
                self.last_usage = {"prompt_tokens": token_total,
                                   "total_tokens": token_total}
                return np.asarray([[len(text)] for text in texts], dtype=np.float32)

        rag = SimpleNamespace(
            qa_llm=SimpleNamespace(infer=lambda *args, **kwargs: ("", {}, False)),
            embedding_model=FakeEmbedding(),
            openie=SimpleNamespace(ner=lambda *args: None,
                                   triple_extraction=lambda *args: None),
            index=lambda docs: docs,
            retrieve=lambda queries: queries,
            qa=lambda solutions: solutions,
        )
        events = []
        instrument_models(rag, corpus, {}, events, threading.Lock(),
                          embedding_max_inputs_per_second=10000)

        result = rag.embedding_model.encode(["A\nOne.", "B\nTwo."])
        summary = summarize_usage(events, corpus)

        self.assertEqual(result.shape, (2, 1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["batch_size"], 2)
        self.assertEqual(len(events[0]["items"]), 2)
        self.assertEqual(summary["phases"]["unknown"]["api_embedding_tokens"], 12)
        for passage_id in ("p1", "p2"):
            row = summary["per_passage"][passage_id]
            self.assertIsNone(row["passage_embedding_tokens"])
            self.assertFalse(row["passage_embedding_usage_attributed"])
            self.assertEqual(row["embedding_batches"], 1)


if __name__ == "__main__":
    unittest.main()
