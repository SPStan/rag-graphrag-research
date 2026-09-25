"""Synthetic probe transport; no Ollama or embedding requests."""

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_hipporag_repair as runner


class SevenBProbeTests(unittest.TestCase):
    def test_probe_records_only_diagnostic_result_and_keeps_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "storage/hipporag2-independent-s500-200-299-repair-f6ea0928/openie-repair-checkpoint.json"
            remedial = root / "storage/hipporag2-remedial-ner3-cap2048-b401b7e6/openie-repair-checkpoint.json"
            old.parent.mkdir(parents=True)
            remedial.parent.mkdir(parents=True)
            messages = [{"role": "user", "content": "synthetic prompt"}]
            encoded = json.dumps(messages, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), default=str).encode()
            prompt_hash = hashlib.sha256(encoded).hexdigest()
            old.write_text(json.dumps({"status": "stopped", "in_flight": None,
                                       "attempts": [
                                           {"task": {"passage_id": "other"},
                                            "attempt": {"status": "valid_nonempty"}},
                                           {"task": {"passage_id": "p"},
                                            "attempt": {"status": "truncated"}}]}))
            remedial.write_text(json.dumps({"status": "stopped", "in_flight": None,
                                            "attempts": [{"task": {"passage_id": "p"},
                                                          "attempt": {
                                                              "status": "truncated",
                                                              "attempt": 3,
                                                              "retry_of_attempt": 2,
                                                              "prompt_sha256": prompt_hash}}]}))
            corpus = root / "corpus.json"
            corpus.write_text(json.dumps([{"id": "p", "title": "T", "text": "X"}]))
            manifest = {"run_id": "source", "storage_dir": "ignored",
                        "inputs": {"corpus_path": str(corpus)},
                        "generation": {"endpoint": "http://localhost:11434/v1"}}
            old_bytes, remedial_bytes = old.read_bytes(), remedial.read_bytes()
            calls = []

            def fake_request(*_args, **_kwargs):
                def request(_messages, *, max_new_tokens, response_format):
                    calls.append(max_new_tokens)
                    if max_new_tokens == 1:
                        return None, {"prompt_tokens": 334,
                                      "completion_tokens": 1}, {}
                    return '{"named_entities":["x"]}', {
                        "prompt_tokens": 334, "completion_tokens": 10,
                        "finish_reason": "stop"}, {}
                return request

            def fake_sha(path):
                if Path(path) == old:
                    return runner.STOPPED_CHECKPOINT_SHA
                if Path(path) == remedial:
                    return runner.REMEDIAL_CHECKPOINT_SHA
                return hashlib.sha256(Path(path).read_bytes()).hexdigest()

            class Distribution:
                version = "pinned"
                def read_text(self, _name):
                    return "pinned"

            with (patch.object(runner, "ROOT", root),
                  patch.object(runner, "load_source_inputs", return_value=(
                      manifest, ["p"], [], "a" * 64, "b" * 64)),
                  patch.object(runner, "build_plan_report", return_value={
                      "plan_sha256": runner.EXPECTED_PLAN_SHA}),
                  patch.object(runner.importlib.metadata, "distribution",
                               return_value=Distribution()),
                  patch.object(runner, "validate_upstream_pin"),
                  patch.object(runner, "_source_artifacts",
                               return_value={str(i): None for i in range(7)}),
                  patch.object(runner, "sha256_file", side_effect=fake_sha),
                  patch.object(runner, "render_openie_messages",
                               return_value=messages),
                  patch.object(runner, "model_info", return_value={
                      "digest": runner.SEVEN_B_DIGEST}),
                  patch.object(runner, "make_native_ollama_request",
                               side_effect=fake_request),
                  patch.object(runner, "make_pinned_openie_parser",
                               return_value=lambda *_a, **_kw: ["x"])):
                runner.run_7b_ner_probe(SimpleNamespace(manifest=root / "manifest.json"),
                                        dry_run=False)

            output = root / "results/raw" / f"hipporag-7b-ner-probe-{prompt_hash[:8]}.json"
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(calls, [1, 2048])
            self.assertEqual(report["status"], "valid_nonempty")
            self.assertEqual(report["requests_completed"], 2)
            self.assertIsNone(report["in_flight"])
            self.assertNotIn("response", report)
            self.assertNotIn("values", report)
            self.assertEqual(old.read_bytes(), old_bytes)
            self.assertEqual(remedial.read_bytes(), remedial_bytes)


if __name__ == "__main__":
    unittest.main()
