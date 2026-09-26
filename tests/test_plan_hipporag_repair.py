import unittest

from scripts.plan_hipporag_repair import build_plan_report


class HippoRAGRepairPlanReportTests(unittest.TestCase):
    def test_report_is_deterministic_and_contains_no_raw_targets(self):
        attempts = []
        for pid in ("private-passage-id-a", "private-passage-id-b"):
            attempts.extend([
                {"passage_id": pid, "stage": "openie_ner", "attempt": 1,
                 "status": "truncated", "source_provenance_complete": True},
                {"passage_id": pid, "stage": "openie_triples", "attempt": 1,
                 "status": "valid_nonempty", "source_provenance_complete": True},
            ])

        report = build_plan_report(
            "source-run", ["private-passage-id-a", "private-passage-id-b"], attempts,
            manifest_sha256="a" * 64, corpus_sha256="b" * 64)

        self.assertEqual(report["status"], "planned_no_model_requests")
        self.assertEqual(report["preflight_status"], "not_ready_for_model_calls")
        self.assertEqual(report["plan"]["planned_stage_outcomes"], 4)
        self.assertEqual(report["plan"]["dependency_refreshes"], 2)
        self.assertEqual(report["plan"]["model_requests_made"], 0)
        self.assertNotIn("private-passage-id", str(report))
        self.assertEqual(report["plan_sha256"], build_plan_report(
            "source-run", ["private-passage-id-a", "private-passage-id-b"], attempts,
            manifest_sha256="a" * 64, corpus_sha256="b" * 64)["plan_sha256"])


if __name__ == "__main__":
    unittest.main()
