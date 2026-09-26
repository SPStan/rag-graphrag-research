"""Run with the pinned HippoRAG environment: offline graph build from ready vectors."""

import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace


class PinnedGraphTests(unittest.TestCase):
    def test_pinned_compatible_transport_is_blocked_before_request(self):
        if importlib.util.find_spec("hipporag") is None:
            self.skipTest("Run this integration test with the pinned HippoRAG Python")
        from hipporag.llm.openai_gpt import CacheOpenAI
        from scripts.hipporag_repair_executor import make_uncached_ollama_request

        captured = []
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"named_entities": []}'),
                                     finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5,
                                  total_tokens=9),
            id="fake", model="qwen-test", _request_id="fake-request",
        )
        class FakeCompletions:
            def create(self, **payload):
                captured.append(payload)
                return response
        llm = CacheOpenAI.__new__(CacheOpenAI)
        llm.max_retries = 0
        llm.request_model_name = "qwen-test"
        llm.global_config = SimpleNamespace(
            llm_supports_max_completion_tokens=False,
            llm_base_url="http://127.0.0.1:1/v1", azure_endpoint=None)
        llm.llm_config = SimpleNamespace(generate_params={"model": "qwen-test"})
        llm.openai_client = SimpleNamespace(
            max_retries=0, chat=SimpleNamespace(completions=FakeCompletions()))
        protocol = {"model": "qwen-test", "model_digest": "verified-digest",
                    "seed": 42, "temperature": 0.0, "num_ctx": 4096}
        with self.assertRaisesRegex(RuntimeError, "does not forward num_ctx"):
            make_uncached_ollama_request(
                llm, protocol=protocol, model_digest="verified-digest")
        self.assertEqual(captured, [])

    def test_pinned_index_uses_repaired_state_without_model_or_embedding(self):
        if importlib.util.find_spec("hipporag") is None:
            self.skipTest("Run this integration test with the pinned HippoRAG Python")
        import pyarrow as pa
        import pyarrow.parquet as parquet
        from hipporag import HippoRAG
        from hipporag.utils.config_utils import BaseConfig
        from hipporag.utils.misc_utils import compute_mdhash_id
        from scripts.hipporag_repair import (
            expected_openie_vector_ids, plan_openie_repairs, finalize_repair_graph,
            sha256_file, openie_values_sha256,
        )
        from scripts.hipporag_repair_journal import RepairJournal
        from scripts.run_hipporag_repair_offline import run_repair_pass

        class NoNetworkLLM:
            def infer(self, *args, **kwargs):
                raise AssertionError("Unexpected model request")

        class ReadyEmbeddings:
            def batch_encode(self, *args, **kwargs):
                raise AssertionError("Unexpected embedding request")

        passage = "Synthetic title\nAlice likes Bob."
        chunk_id = compute_mdhash_id(passage, "chunk-")
        triples = [["Alice", "likes", "Bob"]]
        source_state = {"docs": [{"idx": chunk_id, "passage": passage,
                                  "extracted_entities": ["Old"],
                                  "extracted_triples": [["Old", "is", "old"]]}]}
        source_attempts = [
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 1,
             "status": "truncated", "source_provenance_complete": True},
            {"passage_id": "p1", "stage": "openie_triples", "attempt": 1,
             "status": "valid_nonempty", "source_provenance_complete": True},
        ]
        targets = plan_openie_repairs(["p1"], source_attempts)["targets"]

        with tempfile.TemporaryDirectory() as temporary:
            config = BaseConfig(
                llm_name="fake-llm", embedding_model_name="fake-embed",
                llm_base_url="http://127.0.0.1:1/v1",
                embedding_base_url="http://127.0.0.1:1/v1",
                embedding_provider="openai", save_dir=temporary,
                synonymy_edge_topk=1,
            )
            rag = HippoRAG(global_config=config, extraction_llm=NoNetworkLLM(),
                           qa_llm=NoNetworkLLM(), embedding_model=ReadyEmbeddings(),
                           index_identity="synthetic-fixed")
            working = Path(rag.working_dir)
            provenance = rag._current_openie_provenance()
            rag.close()
            checkpoint = Path(temporary) / "results" / "raw" / "checkpoint.json"
            schedule = [RepairJournal.task_key(task) for task in targets]
            identity = dict(plan_sha256="a" * 64,
                            source_hashes={"manifest": "b" * 64},
                            protocol={"model_digest": "fake", "num_ctx": 4096},
                            expected_task_keys=schedule)
            with RepairJournal(checkpoint, **identity) as journal:
                ner = targets[0]
                journal.begin(ner)
                journal.complete(ner, {**ner, "status": "valid_nonempty",
                                       "source_provenance_complete": True},
                                 ["Alice", "Bob"])
            with RepairJournal(checkpoint, **identity) as journal:
                result = run_repair_pass(
                    journal, targets, source_attempts, source_state, {"p1": chunk_id},
                    lambda task, entities: {
                        "attempt": {**task, "status": "valid_nonempty",
                                    "source_provenance_complete": True},
                        "values": triples if entities == ["Alice", "Bob"] else
                        self.fail("Dependent triple lost repaired entities"),
                    })
            state = result["state"]
            state["provenance"] = provenance
            state_path = working / "openie_state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            entity_ids, fact_ids = expected_openie_vector_ids(state["docs"])
            schema = pa.schema([
                ("hash_id", pa.large_string()), ("content", pa.large_string()),
                ("embedding", pa.list_(pa.float32())),
            ])
            stores = (
                ("chunk", [(chunk_id, passage)]),
                ("entity", [(item, item) for item in sorted(entity_ids)]),
                ("fact", [(item, item) for item in sorted(fact_ids)]),
            )
            for name, rows in stores:
                table = pa.Table.from_pylist([
                    {"hash_id": key, "content": content, "embedding": [1.0, 0.5]}
                    for key, content in rows
                ], schema=schema)
                parquet.write_table(table, working / f"{name}_embeddings" / f"vdb_{name}.parquet")
            config.force_index_from_scratch = True
            old_graph_hash = "a" * 64
            manifest_hash = sha256_file(working / "index_manifest.json")
            (working / "repair_provenance.json").write_text(json.dumps({
                "status": "graph_pending",
                "gate": {"eligible": True},
                "repaired_openie_state_sha256": sha256_file(state_path),
                "repaired_openie_values_sha256": openie_values_sha256(state),
            }), encoding="utf-8")
            with HippoRAG(global_config=config, extraction_llm=NoNetworkLLM(),
                          qa_llm=NoNetworkLLM(), embedding_model=ReadyEmbeddings(),
                          index_identity="synthetic-fixed") as rebuilt:
                rebuilt.index([passage])
                self.assertGreater(rebuilt.graph.vcount(), 0)
                self.assertTrue((working / "graph.pickle").is_file())
            ready = finalize_repair_graph(
                working, {"graph": old_graph_hash,
                          "index_manifest": manifest_hash})
            self.assertEqual(ready["status"], "graph_ready")
            self.assertEqual(ready["index_manifest_sha256"], manifest_hash)


if __name__ == "__main__":
    unittest.main()
