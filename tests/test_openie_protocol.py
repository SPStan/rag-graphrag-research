import unittest

from scripts.openie_protocol import (
    build_openie_acceptance_gate,
    classify_openie_attempt,
)


class OpenIEProtocolTests(unittest.TestCase):
    def test_valid_empty_requires_complete_response_and_valid_list(self):
        self.assertEqual(classify_openie_attempt("{\"entities\":[]}", "stop", []),
                         "valid_empty")
        self.assertEqual(classify_openie_attempt("not-json", "stop", [], parse_error=True),
                         "parse_error")
        self.assertEqual(classify_openie_attempt("{\"entities\":[]}", "length", []),
                         "truncated")
        self.assertEqual(classify_openie_attempt(None, None, None),
                         "raw_response_missing")
        self.assertEqual(classify_openie_attempt(None, None, None, request_error=True),
                         "request_error")
        self.assertEqual(classify_openie_attempt("{}", None, []), "completion_unknown")

    def test_gate_accepts_two_stages_with_valid_empty_or_nonempty_outputs(self):
        attempts = [
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
             "status": "valid_empty", "retry_of_attempt": None,
             "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
             "status": "valid_nonempty", "retry_of_attempt": None,
             "source_provenance_complete": True},
        ]
        gate = build_openie_acceptance_gate(["p1"], attempts)
        self.assertTrue(gate["eligible"])
        self.assertEqual(gate["expected_stage_outcomes"], 2)

    def test_gate_requires_all_stages_and_resolved_retries(self):
        initial = {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
                   "status": "parse_error", "retry_of_attempt": None,
                   "source_provenance_complete": True}
        retry = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                 "status": "valid_nonempty", "retry_of_attempt": 1,
                 "source_provenance_complete": True}
        triple = {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
                  "status": "valid_empty", "retry_of_attempt": None,
                  "source_provenance_complete": True}
        self.assertFalse(build_openie_acceptance_gate(["p1"], [initial])["eligible"])
        self.assertTrue(build_openie_acceptance_gate(
            ["p1"], [initial, retry, triple])["eligible"])
        retry["retry_of_attempt"] = None
        gate = build_openie_acceptance_gate(["p1"], [initial, retry, triple])
        self.assertFalse(gate["eligible"])
        self.assertIn("retry_link_missing", {
            item["reason"] for item in gate["unresolved_stage_outcomes"]
        })

    def test_gate_rejects_unknown_passages_and_duplicate_expected_ids(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            build_openie_acceptance_gate(["p1", "p1"], [])
        gate = build_openie_acceptance_gate(["p1"], [{
            "passage_id": "p2", "stage": "openie_ner", "attempt": 1,
            "status": "valid_empty", "source_provenance_complete": True,
        }])
        self.assertFalse(gate["eligible"])
        self.assertEqual(gate["unexpected_attempts"][0]["reason"],
                         "unexpected_passage_or_stage")

    def test_gate_rejects_unattributed_cache_results_and_retry_after_valid_status(self):
        base = {"passage_id": "p1", "status": "valid_empty",
                "source_provenance_complete": True}
        attempts = [
            {**base, "stage": "openie_ner", "attempt": 1,
             "retry_of_attempt": None},
            {**base, "stage": "openie_ner", "attempt": 2,
             "retry_of_attempt": 1},
            {**base, "stage": "openie_triples", "attempt": 1,
             "retry_of_attempt": None},
        ]
        gate = build_openie_acceptance_gate(["p1"], attempts)
        self.assertFalse(gate["eligible"])
        self.assertIn("retry_after_valid_attempt", {
            item["reason"] for item in gate["unresolved_stage_outcomes"]
        })

        attempts[0]["source_provenance_complete"] = False
        attempts[1]["status"] = "parse_error"
        gate = build_openie_acceptance_gate(["p1"], attempts)
        self.assertIn("source_provenance_missing", {
            item["reason"] for item in gate["unresolved_stage_outcomes"]
        })

    def test_gate_accepts_triple_refresh_linked_to_corrected_ner(self):
        attempts = [
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
             "status": "truncated", "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
             "status": "valid_nonempty", "retry_of_attempt": 1,
             "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
             "status": "valid_nonempty", "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 2,
             "status": "valid_nonempty", "retry_of_attempt": 1,
             "operation": "dependency_refresh", "dependency_stage": "openie_ner",
             "dependency_attempt": 2, "source_provenance_complete": True},
        ]
        gate = build_openie_acceptance_gate(["p1"], attempts)
        self.assertTrue(gate["eligible"], gate["unresolved_stage_outcomes"])

        attempts[2]["status"] = "truncated"
        gate = build_openie_acceptance_gate(["p1"], attempts)
        self.assertTrue(gate["eligible"], gate["unresolved_stage_outcomes"])

    def test_gate_rejects_unlinked_or_unverified_dependency_refresh(self):
        attempts = [
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
             "status": "truncated", "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
             "status": "valid_nonempty", "retry_of_attempt": 1,
             "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
             "status": "valid_empty", "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 2,
             "status": "valid_nonempty", "retry_of_attempt": 1,
             "operation": "dependency_refresh", "dependency_stage": "openie_ner",
             "dependency_attempt": 1, "source_provenance_complete": True},
        ]
        gate = build_openie_acceptance_gate(["p1"], attempts)
        self.assertFalse(gate["eligible"])
        self.assertIn("dependency_refresh_link_invalid", {
            item["reason"] for item in gate["unresolved_stage_outcomes"]
        })

    def test_gate_allows_one_explicit_remedial_attempt_and_rejects_more(self):
        ner = [
            {"passage_id": "p1", "stage": "openie_ner", "attempt": number,
             "status": status, "retry_of_attempt": number - 1 if number > 1 else None,
             "source_provenance_complete": True}
            for number, status in ((1, "truncated"), (2, "request_error"),
                                   (3, "valid_nonempty"))
        ]
        triple = {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
                  "status": "valid_empty", "source_provenance_complete": True}
        gate = build_openie_acceptance_gate(["p1"], [*ner, triple])
        self.assertFalse(gate["eligible"])
        ner[-1]["remedial_retry"] = True
        gate = build_openie_acceptance_gate(["p1"], [*ner, triple])
        self.assertTrue(gate["eligible"], gate["unresolved_stage_outcomes"])

        ner.append({"passage_id": "p1", "stage": "openie_ner", "attempt": 4,
                    "status": "valid_nonempty", "retry_of_attempt": 3,
                    "remedial_retry": True, "source_provenance_complete": True})
        gate = build_openie_acceptance_gate(["p1"], [*ner, triple])
        self.assertFalse(gate["eligible"])
        self.assertIn("maximum_attempts_exceeded", {
            item["reason"] for item in gate["unresolved_stage_outcomes"]
        })


if __name__ == "__main__":
    unittest.main()
