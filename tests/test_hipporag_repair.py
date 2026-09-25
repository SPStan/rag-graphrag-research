import unittest

import pyarrow as pa

from scripts.hipporag_repair import filter_embedding_table_to_ids


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


if __name__ == "__main__":
    unittest.main()
