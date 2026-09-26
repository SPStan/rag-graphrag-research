import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_openie import build_report, classify_documents, write_json_atomic


class OpenIEAuditTests(unittest.TestCase):
    def sample_state(self):
        return {
            "docs": [
                {"idx": "one", "passage": "A | B\n1 | 2\n3 | 4", "extracted_entities": [],
                 "extracted_triples": [["A", "is", "B"]]},
                {"idx": "two", "passage": "Plain text", "extracted_entities": ["A"],
                 "extracted_triples": []},
                {"idx": "three", "passage": "Nothing here", "extracted_entities": [],
                 "extracted_triples": []},
                {"idx": "four", "passage": "Entity and relation", "extracted_entities": ["A"],
                 "extracted_triples": [["A", "is", "B"]]},
            ]
        }

    def test_categories_and_spot_check_are_deterministic_and_safe(self):
        report = classify_documents(self.sample_state(), seed=7, sample_size=1)
        self.assertEqual(report["documents"], 4)
        self.assertEqual(report["categories"], {
            "entities_empty_triples_present": 1,
            "entities_present_triples_empty": 1,
            "both_empty": 1,
            "both_present": 1,
        })
        self.assertEqual(report["table_like_by_category"]["entities_empty_triples_present"], 1)
        encoded = json.dumps(report)
        self.assertNotIn("Plain text", encoded)
        self.assertNotIn("Nothing here", encoded)
        self.assertEqual(
            classify_documents(self.sample_state(), seed=7, sample_size=1), report
        )

    def test_cache_aggregate_is_read_only_and_reports_unlinkable_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            state_path.write_text(json.dumps(self.sample_state()), encoding="utf-8")
            cache_path = root / "cache.sqlite"
            connection = sqlite3.connect(cache_path)
            connection.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, message TEXT, metadata TEXT)")
            connection.executemany(
                "INSERT INTO cache VALUES (?, ?, ?)",
                [
                    ("one", '{"named_entities": []}', '{"finish_reason": "stop"}'),
                    ("two", '{"triples": [["A", "is", "B"]]}', '{"finish_reason": "length"}'),
                    ("three", "not json", "not json"),
                ],
            )
            connection.commit()
            connection.close()
            state_hash_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
            cache_hash_before = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            report = build_report(state_path, cache_path, seed=42, sample_size=1, source_run_id="run")
            self.assertEqual(report["cache"]["entries"], 3)
            self.assertEqual(report["cache"]["response_kinds"]["ner_empty"], 1)
            self.assertEqual(report["cache"]["response_kinds"]["triples_present"], 1)
            self.assertEqual(report["cache"]["finish_reasons"]["length"], 1)
            self.assertEqual(report["cache"]["malformed_metadata"], 1)
            self.assertIn("unavailable", report["cache"]["linkage_to_passages"])
            self.assertEqual(state_hash_before, hashlib.sha256(state_path.read_bytes()).hexdigest())
            self.assertEqual(cache_hash_before, hashlib.sha256(cache_path.read_bytes()).hexdigest())

    def test_atomic_report_write_uses_stable_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "nested" / "report.json"
            write_json_atomic(output, {"b": 2, "a": 1})
            self.assertEqual(output.read_text(encoding="utf-8"), '{\n  "a": 1,\n  "b": 2\n}\n')


if __name__ == "__main__":
    unittest.main()
