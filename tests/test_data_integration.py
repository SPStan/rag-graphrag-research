"""Offline integration tests; raw data must first be downloaded explicitly."""

import hashlib
import json
from pathlib import Path
import unittest

from data.make_subsample import build_subset, json_bytes
from scripts.download_data import verify

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "data/sources.lock.json").read_text(encoding="utf-8"))
HAS_DATA = all((ROOT / "data/raw" / entry["name"]).exists() for entry in LOCK["files"])


@unittest.skipUnless(HAS_DATA, "Download pinned data with scripts/download_data.py first")
class RealDataTests(unittest.TestCase):
    def test_all_six_source_checksums(self):
        for entry in LOCK["files"]:
            with self.subTest(file=entry["name"]):
                verify((ROOT / "data/raw" / entry["name"]).read_bytes(), entry)

    def test_rebuild_matches_committed_ids_and_output_hashes(self):
        report = json.loads((ROOT / "results/data/subsamples.json").read_text(encoding="utf-8"))
        for dataset in ("musique", "hotpotqa"):
            with self.subTest(dataset=dataset):
                questions = json.loads((ROOT / f"data/raw/{dataset}.json").read_bytes())
                source_corpus = json.loads((ROOT / f"data/raw/{dataset}_corpus.json").read_bytes())
                queries, labels, corpus, ids, stats = build_subset(dataset, questions, source_corpus)
                saved = json.loads((ROOT / f"data/ids/{dataset}_s500.json").read_text(encoding="utf-8"))
                self.assertEqual(ids["question_ids"], saved["question_ids"])
                self.assertEqual(ids["passage_ids"], saved["passage_ids"])
                self.assertEqual(ids["views"], saved["views"])
                self.assertEqual(len(queries), 500)
                self.assertEqual(len(corpus), 5500)
                for view, size in (("debug10", 10), ("debug20", 20), ("baseline100", 100), ("pilot200", 200)):
                    self.assertEqual(saved["views"][view], saved["question_ids"][:size])
                self.assertEqual(saved["views"]["holdout100"], saved["question_ids"][-100:])
                self.assertFalse(set(saved["views"]["holdout100"]) &
                                 set(saved["views"]["pilot200"]))
                self.assertEqual({row["id"] for row in queries}, {row["id"] for row in labels})
                for row in labels:
                    self.assertTrue(set(row["supporting_ids"]) <= set(saved["passage_ids"]))
                for name, value in (("queries.json", queries), ("labels.json", labels), ("corpus.json", corpus)):
                    self.assertEqual(hashlib.sha256(json_bytes(value)).hexdigest(),
                                     report["datasets"][dataset]["output_sha256"][name])


if __name__ == "__main__":
    unittest.main()
