import hashlib
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa

from scripts.hipporag_repair import (
    REPAIR_ARTIFACTS,
    create_verified_index_copy,
    expected_openie_vector_ids,
    filter_embedding_table_to_ids,
    merge_attempt_ledgers,
    plan_openie_repairs,
    apply_openie_updates,
    prepare_repair_clone,
    sha256_file,
)


class HippoRAGRepairPlanningTests(unittest.TestCase):
    def test_repair_plan_orders_ner_before_dependent_triples_and_bounds_attempts(self):
        history = []
        for pid in ("p1", "p2", "p3"):
            ner_attempts = 2 if pid == "p2" else 1
            for attempt in range(1, ner_attempts + 1):
                history.append({
                    "passage_id": pid, "stage": "openie_ner", "attempt": attempt,
                    "status": "truncated", "source_provenance_complete": True,
                })
            history.append({
                "passage_id": pid, "stage": "openie_triples", "attempt": 1,
                "status": ("valid_nonempty" if pid == "p3" else "parse_error"),
                "source_provenance_complete": True,
            })

        plan = plan_openie_repairs(["p1", "p2", "p3"], history)

        self.assertEqual(plan["summary"], {
            "expected_passages": 3,
            "planned_stage_outcomes": 6,
            "planned_by_stage": {"openie_ner": 3, "openie_triples": 3},
            "dependency_refreshes": 3,
            "remedial_attempts": 1,
            "model_requests_made": 0,
        })
        self.assertEqual([row["stage"] for row in plan["targets"]], [
            "openie_ner", "openie_ner", "openie_ner", "openie_triples",
            "openie_triples", "openie_triples",
        ])
        # All NER work must precede triple extraction even when input IDs vary.
        self.assertEqual([row["passage_id"] for row in plan["targets"][:3]],
                         ["p1", "p2", "p3"])
        p2_ner = next(row for row in plan["targets"]
                      if row["passage_id"] == "p2" and row["stage"] == "openie_ner")
        self.assertEqual(p2_ner["attempt"], 3)
        self.assertTrue(p2_ner["remedial_retry"])
        p1_triples = next(row for row in plan["targets"]
                          if row["passage_id"] == "p1" and row["stage"] == "openie_triples")
        self.assertEqual(p1_triples["operation"], "dependency_refresh")
        p3_triples = next(row for row in plan["targets"]
                          if row["passage_id"] == "p3" and row["stage"] == "openie_triples")
        self.assertEqual(p3_triples["attempt"], 2)
        self.assertEqual(p3_triples["retry_of_attempt"], 1)
        self.assertEqual(len(history), 7)

    def test_repair_plan_rejects_missing_history_and_attempt_overflow(self):
        with self.assertRaisesRegex(ValueError, "missing stage history"):
            plan_openie_repairs(["p1"], [])

        history = [{
            "passage_id": "p1", "stage": "openie_ner", "attempt": number,
            "status": "truncated", "source_provenance_complete": True,
        } for number in (1, 2, 3)] + [{
            "passage_id": "p1", "stage": "openie_triples", "attempt": 1,
            "status": "valid_empty", "source_provenance_complete": True,
        }]
        with self.assertRaisesRegex(ValueError, "exceed the three-attempt limit"):
            plan_openie_repairs(["p1"], history)

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

    def test_prepare_repair_clone_filters_and_reuses_vectors_without_touching_source(self):
        import json
        import pyarrow.parquet as parquet

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            source_state = {"provenance": {"identity": "original"}, "docs": [{
                "idx": "doc-1", "passage": "synthetic title\\ntext",
                "extracted_entities": ["Old"],
                "extracted_triples": [["Old", "relation", "Thing"]],
            }]}
            (source / REPAIR_ARTIFACTS["openie_state"]).write_text(
                json.dumps(source_state), encoding="utf-8")
            for name, relative in REPAIR_ARTIFACTS.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if name == "openie_state":
                    continue
                if name == "chunk_embeddings":
                    table = pa.table({
                        "hash_id": pa.array(["doc-1"], type=pa.large_string()),
                        "content": pa.array(["synthetic title\\ntext"], type=pa.large_string()),
                        "embedding": pa.array([[1.0, 0.0]], type=pa.list_(pa.float32())),
                    })
                    parquet.write_table(table, path)
                elif name in {"entity_embeddings", "fact_embeddings"}:
                    continue
                else:
                    path.write_text(f"synthetic:{name}", encoding="utf-8")

            updates = [
                {"passage_id": "p1", "stage": "openie_ner",
                 "status": "valid_nonempty", "values": ["Alice", "Bob"]},
                {"passage_id": "p1", "stage": "openie_triples",
                 "status": "valid_nonempty", "values": [["Alice", "likes", "Bob"]]},
            ]
            repaired_state, _ = apply_openie_updates(
                source_state, {"p1": "doc-1"}, updates)
            entity_ids, fact_ids = expected_openie_vector_ids(repaired_state["docs"])
            schema = pa.schema([
                ("hash_id", pa.large_string()), ("content", pa.large_string()),
                ("embedding", pa.list_(pa.float32())),
            ])
            source_entities = pa.Table.from_pylist([{
                "hash_id": "entity-obsolete", "content": "obsolete",
                "embedding": [0.0, 1.0],
            }], schema=schema)
            source_facts = pa.Table.from_pylist([{
                "hash_id": "fact-obsolete", "content": "obsolete fact",
                "embedding": [0.0, 1.0],
            }], schema=schema)
            parquet.write_table(source_entities, source / REPAIR_ARTIFACTS["entity_embeddings"])
            parquet.write_table(source_facts, source / REPAIR_ARTIFACTS["fact_embeddings"])
            new_entities = pa.Table.from_pylist([{
                "hash_id": vector_id, "content": "new entity",
                "embedding": [1.0, 0.0],
            } for vector_id in sorted(entity_ids)], schema=schema)
            new_facts = pa.Table.from_pylist([{
                "hash_id": vector_id, "content": "new fact",
                "embedding": [1.0, 0.0],
            } for vector_id in sorted(fact_ids)], schema=schema)
            expected_hashes = {
                name: sha256_file(source / relative)
                for name, relative in REPAIR_ARTIFACTS.items()
            }
            source_attempts = [
                {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
                 "status": "truncated", "source_provenance_complete": True},
                {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
                 "status": "valid_nonempty", "source_provenance_complete": True},
            ]
            repair_attempts = [
                {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                 "retry_of_attempt": 1, "status": "valid_nonempty",
                 "source_provenance_complete": True},
                {"passage_id": "p1", "stage": "openie_triples", "attempt": 2,
                 "retry_of_attempt": 1, "status": "valid_nonempty",
                 "operation": "dependency_refresh", "dependency_stage": "openie_ner",
                 "dependency_attempt": 2, "source_provenance_complete": True},
            ]
            protocol = {
                "model_digest": "synthetic-model", "prompt_schema_version": "synthetic-v1",
                "response_format": {"type": "json_object"}, "temperature": 0,
                "seed": 1, "num_ctx": 4096, "ner_max_new_tokens": 1024,
                "triples_max_new_tokens": 3072,
            }
            destination = root / "clone"

            result = prepare_repair_clone(
                source, destination, expected_hashes,
                source_run_id="synthetic-source-run",
                source_compatibility={
                    key: True for key in (
                        "producer_identity_matches", "embedding_identity_matches",
                        "openie_identity_matches", "source_corpus_sha256_matches_manifest",
                        "source_passages_match_openie_state", "chunk_ids_match_openie_state",
                        "entity_ids_match_openie_state", "fact_ids_match_openie_state",
                        "current_state_artifacts_consistent",
                    )
                },
                source_attempts=source_attempts, repair_attempts=repair_attempts,
                expected_passage_ids=["p1"], state_updates=updates,
                passage_id_to_index={"p1": "doc-1"},
                new_entity_rows=new_entities, new_fact_rows=new_facts,
                repair_protocol=protocol,
            )

            self.assertTrue(result["provenance"]["gate"]["eligible"])
            self.assertTrue(result["provenance"]["vector_plans"]["entity_embeddings"]["complete"])
            self.assertTrue(result["provenance"]["vector_plans"]["fact_embeddings"]["complete"])
            clone_state = json.loads((destination / "openie_state.json").read_text(encoding="utf-8"))
            self.assertEqual(clone_state["docs"][0]["extracted_entities"], ["Alice", "Bob"])
            self.assertEqual(json.loads((source / "openie_state.json").read_text(encoding="utf-8")),
                             source_state)
            self.assertEqual(set(parquet.read_table(
                destination / REPAIR_ARTIFACTS["entity_embeddings"]
            ).column("hash_id").to_pylist()), entity_ids)
            self.assertEqual(set(parquet.read_table(
                destination / REPAIR_ARTIFACTS["fact_embeddings"]
            ).column("hash_id").to_pylist()), fact_ids)
            self.assertEqual(len(result["merged_attempts"]), 4)


if __name__ == "__main__":
    unittest.main()
