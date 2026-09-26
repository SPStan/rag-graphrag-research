import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from data.make_subsample import build_subset, build_views, canonical_key, passage_id, write_stable
from scripts.download_data import verify


def fixture():
    corpus = [{"title": "Same title", "text": f"Different passage {i}"} for i in range(12)]
    questions = [{"id": f"q{i}", "question": f"Question {i}?", "answer": str(i),
                  "answer_aliases": [f"alias {i}"], "answerable": True,
                  "paragraphs": [{"title": corpus[i]["title"], "paragraph_text": corpus[i]["text"],
                                  "idx": 0, "is_supporting": True}]} for i in range(6)]
    return questions, corpus


class SubsampleTests(unittest.TestCase):
    def test_repeatability_and_input_order(self):
        questions, corpus = fixture()
        first = build_subset("musique", questions, corpus, 4, 8)
        second = build_subset("musique", list(reversed(questions)), list(reversed(corpus)), 4, 8)
        self.assertEqual(first, second)

    def test_supporting_coverage_no_leakage_and_unique_ids(self):
        questions, corpus = fixture()
        queries, labels, docs, ids, stats = build_subset("musique", questions, corpus, 4, 8)
        self.assertEqual(len({d["id"] for d in docs}), 8)
        self.assertEqual(len(set(ids["question_ids"])), 4)
        for query in queries:
            self.assertEqual(set(query), {"id", "question"})
        for doc in docs:
            self.assertEqual(set(doc), {"id", "title", "text"})
        for label in labels:
            self.assertTrue(set(label["supporting_ids"]) <= set(ids["passage_ids"]))
        self.assertEqual(stats["supporting_passages"], 4)
        self.assertEqual(ids["views"]["debug10"], ids["question_ids"][:10])

    def test_holdout_view_uses_last_hundred_and_is_disjoint_from_development_views(self):
        selected_ids = [f"q{i}" for i in range(500)]
        views = build_views(selected_ids)
        self.assertEqual(views["holdout100"], selected_ids[400:500])
        for name in ("debug10", "debug20", "baseline100", "pilot200"):
            self.assertFalse(set(views["holdout100"]) & set(views[name]))

    def test_same_title_is_not_enough(self):
        questions, corpus = fixture()
        questions[0]["paragraphs"][0]["paragraph_text"] = "Not in the corpus"
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
            build_subset("musique", questions, corpus, 6, 8)

    def test_duplicate_questions_rejected(self):
        questions, corpus = fixture()
        with self.assertRaisesRegex(ValueError, "duplicate question"):
            build_subset("musique", questions + [questions[0]], corpus, 4, 8)

    def test_too_many_supporting_passages_rejected(self):
        questions, corpus = fixture()
        with self.assertRaisesRegex(ValueError, "exceed"):
            build_subset("musique", questions, corpus, 6, 3)

    def test_no_supporting_rejected(self):
        questions, corpus = fixture()
        questions[0]["paragraphs"][0]["is_supporting"] = False
        with self.assertRaisesRegex(ValueError, "No supporting"):
            build_subset("musique", questions, corpus, 6, 8)

    def test_unanswerable_rejected(self):
        questions, corpus = fixture()
        questions[0]["answerable"] = False
        with self.assertRaisesRegex(ValueError, "Unanswerable"):
            build_subset("musique", questions, corpus, 6, 8)

    def test_canonical_duplicate_is_one_document(self):
        questions, corpus = fixture()
        duplicate = {"title": "Same   title", "text": " Different passage 0  "}
        *_, stats = build_subset("musique", questions, corpus + [duplicate], 4, 8)
        self.assertEqual(stats["canonical_duplicates_removed"], 1)

    def test_hotpot_sentence_join_and_repeated_supporting_titles(self):
        question = {"_id": "h1", "question": "Who?", "answer": "A",
                    "context": [["A", ["First sentence.", " Second sentence."]]],
                    "supporting_facts": [["A", 0], ["A", 1]]}
        corpus = [{"title": "A", "text": "First sentence. Second sentence."},
                  {"title": "A", "text": "Other article version."}]
        _, labels, _, _, stats = build_subset("hotpotqa", [question], corpus, 1, 2)
        expected = passage_id(canonical_key("A", corpus[0]["text"]))
        self.assertEqual(labels[0]["supporting_ids"], [expected])
        self.assertEqual(stats["supporting_passages"], 1)
        bad = copy.deepcopy(question)
        bad["supporting_facts"] = [["A", 9]]
        with self.assertRaisesRegex(ValueError, "sentence index"):
            build_subset("hotpotqa", [bad], corpus, 1, 2)

    def test_hotpot_missing_context_rejected(self):
        question = {"_id": "h1", "question": "Who?", "answer": "A",
                    "context": [], "supporting_facts": [["A", 0]]}
        with self.assertRaisesRegex(ValueError, "missing from context"):
            build_subset("hotpotqa", [question], [{"title": "A", "text": "A"}], 1, 1)

    def test_count_bounds(self):
        questions, corpus = fixture()
        for count, size in ((0, 8), (7, 8), (4, 13), (4, 0)):
            with self.assertRaises(ValueError):
                build_subset("musique", questions, corpus, count, size)

    def test_fixed_output_cannot_be_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ids.json"
            write_stable(path, b"one")
            write_stable(path, b"one")
            with self.assertRaisesRegex(ValueError, "differs"):
                write_stable(path, b"two")
            self.assertEqual(path.read_bytes(), b"one")


class DownloadIntegrityTests(unittest.TestCase):
    def test_hashes_and_corruption(self):
        payload = json.dumps([{"id": "q1"}]).encode()
        entry = {"name": "test.json", "size": len(payload),
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "git_blob_sha1": hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()}
        self.assertEqual(verify(payload, entry), entry["sha256"])
        for bad in (payload[:-1], payload.replace(b"q1", b"q2")):
            with self.assertRaises(ValueError):
                verify(bad, entry)
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify(payload, {"name": "test.json", "size": len(payload)})


if __name__ == "__main__":
    unittest.main()
