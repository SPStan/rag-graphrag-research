import json
import tempfile
import unittest
from pathlib import Path

from scripts.freeze_eval_view import build_candidate_view, verify_candidate_view


class FreezeEvaluationViewTests(unittest.TestCase):
    def test_freezes_ordered_slice_and_audits_manifest_and_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ids_path = root / "ids.json"
            ids_path.write_text(json.dumps({
                "dataset": "musique", "source_revision": "revision",
                "question_ids": [f"q{i}" for i in range(500)],
            }), encoding="utf-8")
            results = root / "results"
            results.mkdir()
            (results / "run-a.manifest.json").write_text(json.dumps({
                "dataset": "musique", "run_id": "run-a", "status": "completed",
                "expected_question_ids": ["q1"],
            }), encoding="utf-8")
            (results / "run-b.jsonl").write_text(json.dumps({
                "dataset": "musique", "question_id": "q199",
            }) + "\n", encoding="utf-8")

            view = build_candidate_view(ids_path, results)

            self.assertEqual(view["question_ids"], [f"q{i}" for i in range(200, 300)])
            self.assertEqual(view["status"], "frozen_candidate_not_run")
            self.assertEqual(view["disjointness_audit"]["manifest_count"], 1)
            self.assertEqual(view["disjointness_audit"]["raw_without_manifest_count"], 1)
            self.assertEqual(view["disjointness_audit"]["overlap_count"], 0)
            frozen_path = root / "candidate.json"
            frozen_path.write_text(json.dumps(view), encoding="utf-8")
            before = frozen_path.read_bytes()
            verification = verify_candidate_view(frozen_path, ids_path, results)
            self.assertTrue(verification["verified"])
            self.assertEqual(frozen_path.read_bytes(), before)

    def test_refuses_any_historical_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ids_path = root / "ids.json"
            ids_path.write_text(json.dumps({
                "dataset": "musique", "question_ids": [f"q{i}" for i in range(500)],
            }), encoding="utf-8")
            results = root / "results"
            results.mkdir()
            (results / "run.manifest.json").write_text(json.dumps({
                "dataset": "musique", "run_id": "run", "status": "failed",
                "expected_question_ids": ["q250"],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "overlap"):
                build_candidate_view(ids_path, results)


if __name__ == "__main__":
    unittest.main()
