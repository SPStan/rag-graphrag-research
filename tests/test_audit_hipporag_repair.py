import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_hipporag_repair import summarize_attempts


class HippoRAGRepairAuditTests(unittest.TestCase):
    def test_counts_only_latest_unresolved_stages_and_dependent_refreshes(self):
        attempts = [
            {"passage_id": "private-1", "stage": "openie_ner", "attempt": 1,
             "status": "truncated"},
            {"passage_id": "private-1", "stage": "openie_ner", "attempt": 2,
             "status": "valid_nonempty"},
            {"passage_id": "private-1", "stage": "openie_triples", "attempt": 1,
             "status": "truncated"},
            {"passage_id": "private-2", "stage": "openie_ner", "attempt": 1,
             "status": "truncated"},
            {"passage_id": "private-2", "stage": "openie_triples", "attempt": 1,
             "status": "valid_nonempty"},
        ]

        report = summarize_attempts(attempts)

        self.assertEqual(report["unresolved_by_stage"],
                         {"openie_ner": 1, "openie_triples": 1})
        self.assertEqual(report["passages_with_both_stages_unresolved"], 0)
        self.assertEqual(report["ner_repairs_requiring_dependent_triple_refresh"], 1)
        self.assertEqual(
            report["estimated_targeted_generation_calls_if_dependency_refresh_is_required"],
            3,
        )
        self.assertNotIn("private-1", json.dumps(report))

    def test_overlap_does_not_double_count_dependent_triple_refresh(self):
        attempts = [
            {"passage_id": "p", "stage": stage, "attempt": 1,
             "status": "truncated"}
            for stage in ("openie_ner", "openie_triples")
        ]

        report = summarize_attempts(attempts)

        self.assertEqual(report["passages_with_both_stages_unresolved"], 1)
        self.assertEqual(report["ner_repairs_requiring_dependent_triple_refresh"], 0)
        self.assertEqual(
            report["estimated_targeted_generation_calls_if_dependency_refresh_is_required"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
