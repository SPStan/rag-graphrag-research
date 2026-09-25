import hashlib
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa

from scripts.hipporag_repair import (
    REPAIR_ARTIFACTS,
    create_verified_index_copy,
    filter_embedding_table_to_ids,
    merge_attempt_ledgers,
    apply_openie_updates,
)


class HippoRAGRepairPlanningTests(unittest.TestCase):
    def test_filter_reuses_matching_vectors_and_reports_new_and_obsolete_ids(self):
        source = pa.table({
            "hash_id": ["keep-a", "stale", "keep-b"],
            "content": ["a", "obsolete", "b"],
            "embedding": [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]],
        })

        filtered, plan = filter_embedding_table_to_ids(
            source, {"keep-a", "keep-b", "new-c"}
        )

        self.assertEqual(filtered.column("hash_id").to_pylist(), ["keep-a", "keep-b"])
        self.assertEqual(plan, {
            "source_rows": 3,
            "target_rows": 3,
            "retained_rows": 2,
            "obsolete_rows": 1,
            "missing_rows": 1,
            "complete": False,
        })
        self.assertEqual(source.column("hash_id").to_pylist(),
                         ["keep-a", "stale", "keep-b"])

    def test_filter_rejects_duplicate_source_ids(self):
        source = pa.table({"hash_id": ["duplicate", "duplicate"],
                           "embedding": [[1.0], [2.0]]})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            filter_embedding_table_to_ids(source, {"duplicate"})

    def test_verified_copy_preserves_source_and_copies_only_whitelisted_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            hashes = {}
            for name, relative in REPAIR_ARTIFACTS.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"synthetic:{name}", encoding="utf-8")
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            (source / "unlisted.cache").write_text("leave behind", encoding="utf-8")
            destination = root / "copy"

            copied = create_verified_index_copy(source, destination, hashes)

            self.assertEqual(set(copied), set(REPAIR_ARTIFACTS))
            for name, relative in REPAIR_ARTIFACTS.items():
                self.assertEqual((source / relative).read_bytes(),
                                 (destination / relative).read_bytes())
            self.assertFalse((destination / "unlisted.cache").exists())
            self.assertTrue((source / "unlisted.cache").exists())

    def test_verified_copy_refuses_bad_hash_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            hashes = {}
            for name, relative in REPAIR_ARTIFACTS.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding="utf-8")
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            bad_hashes = dict(hashes, graph="0" * 64)
            destination = root / "copy"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                create_verified_index_copy(source, destination, bad_hashes)
            self.assertFalse(destination.exists())
            create_verified_index_copy(source, destination, hashes)
            with self.assertRaisesRegex(ValueError, "destination must be new"):
                create_verified_index_copy(source, destination, hashes)

    def test_ledger_merge_appends_linked_attempts_without_mutating_source(self):
        source = [{"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
                   "status": "truncated", "source_provenance_complete": True}]
        repair = [{"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                   "retry_of_attempt": 1, "status": "valid_nonempty",
                   "source_provenance_complete": True}]

        merged = merge_attempt_ledgers(source, repair, ["p1"])

        self.assertEqual([row["attempt"] for row in merged], [1, 2])
        self.assertEqual(len(source), 1)
        self.assertNotIn("retry_of_attempt", source[0])

    def test_ledger_merge_requires_declared_third_attempt(self):
        source = [{"passage_id": "p1", "stage": "openie_ner", "attempt": number,
                   "status": "truncated", "source_provenance_complete": True}
                  for number in (1, 2)]
        repair = [{"passage_id": "p1", "stage": "openie_ner", "attempt": 3,
                   "retry_of_attempt": 2, "status": "valid_nonempty",
                   "source_provenance_complete": True}]
        with self.assertRaisesRegex(ValueError, "marked remedial"):
            merge_attempt_ledgers(source, repair, ["p1"])
        repair[0]["remedial_retry"] = True
        self.assertEqual(len(merge_attempt_ledgers(source, repair, ["p1"])), 3)

    def test_openie_state_updates_create_copy_and_validate_extracted_shapes(self):
        source = {"provenance": {"identity": "unchanged"}, "docs": [{
            "idx": "doc-1", "passage": "synthetic passage",
            "extracted_entities": ["old"],
            "extracted_triples": [["old", "relation", "value"]],
        }]}
        updates = [
            {"passage_id": "p1", "stage": "openie_ner", "status": "valid_nonempty",
             "values": ["new"]},
            {"passage_id": "p1", "stage": "openie_triples",
             "status": "valid_nonempty", "values": [["new", "relation", "value"]]},
        ]

        repaired, summary = apply_openie_updates(source, {"p1": "doc-1"}, updates)

        self.assertEqual(repaired["docs"][0]["extracted_entities"], ["new"])
        self.assertEqual(repaired["docs"][0]["extracted_triples"],
                         [["new", "relation", "value"]])
        self.assertEqual(summary["updated_by_stage"],
                         {"openie_ner": 1, "openie_triples": 1})
        self.assertEqual(source["docs"][0]["extracted_entities"], ["old"])
        updates[1]["values"] = [["broken", "triple"]]
        with self.assertRaisesRegex(ValueError, "three non-empty strings"):
            apply_openie_updates(source, {"p1": "doc-1"}, updates)
        partial = [{"passage_id": "p1", "stage": "openie_ner",
                    "status": "truncated", "values": ["partial"]}]
        with self.assertRaisesRegex(ValueError, "Only complete"):
            apply_openie_updates(source, {"p1": "doc-1"}, partial)


if __name__ == "__main__":
    unittest.main()
