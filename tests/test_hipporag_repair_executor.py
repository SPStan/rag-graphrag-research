import hashlib
import json
import unittest

from scripts.hipporag_repair_executor import (
    execute_openie_task, make_native_ollama_request,
    make_uncached_ollama_request, measure_then_execute_openie_task,
    native_chat_payload, render_openie_messages,
)


class FakePromptManager:
    def render(self, *, name, **kwargs):
        return [{"role": "user", "content": f"{name}:{kwargs}"}]


def context_report(messages, *, stage="openie_ner", input_tokens=100):
    cap_key = "ner_max_new_tokens" if stage == "openie_ner" else "triples_max_new_tokens"
    cap = 1024 if stage == "openie_ner" else 3072
    serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), default=str).encode("utf-8")
    return {
        "status": "context_fit_verified",
        "model_digest": "model-sha",
        "num_ctx": 4096,
        "max_new_tokens": cap,
        "prompt_sha256": hashlib.sha256(serialized).hexdigest(),
        "input_tokens": input_tokens,
        "stage": stage,
        "temperature": 0.0,
        "seed": 42,
        "response_format": {"type": "json_object"},
        "protocol": {"num_ctx": 4096, cap_key: cap,
                      "temperature": 0.0, "seed": 42},
    }


class HippoRAGRepairExecutorTests(unittest.TestCase):
    def test_disabled_or_unverified_requests_never_invoke_callback(self):
        calls = []
        task = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                "retry_of_attempt": 1}
        kwargs = dict(
            task=task, passage="title\ntext", named_entities=None,
            request_fn=lambda *args, **kw: calls.append(args),
            parse_fn=lambda *args, **kw: [], run_id="repair", model_digest="model-sha",
            context_preflight=None, prompt_manager=FakePromptManager())
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            execute_openie_task(**kwargs)
        self.assertEqual(calls, [])

        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        kwargs["context_preflight"] = {
            "status": "not_ready_for_model_calls",
            "protocol": {"num_ctx": 4096, "ner_max_new_tokens": 1024},
        }
        with self.assertRaisesRegex(ValueError, "tokenizer-backed"):
            execute_openie_task(**kwargs, model_requests_enabled=True)
        self.assertEqual(calls, [])

    def test_valid_empty_response_is_accepted_and_cache_bypass_is_recorded(self):
        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        called = []

        def request_fn(actual_messages, *, max_new_tokens, response_format):
            called.append((actual_messages, max_new_tokens, response_format))
            return ('{"named_entities": []}', {
                "finish_reason": "stop", "prompt_tokens": 11,
                "completion_tokens": 4,
            }, {"cache_hit": False, "cache_status": "bypassed",
                "transport_attempt_count": 1, "client_seconds": 0.2})

        result = execute_openie_task(
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
             "retry_of_attempt": 1},
            "title\ntext", None, request_fn=request_fn,
            parse_fn=lambda stage, response, recover_partial: [],
            run_id="repair-run", model_digest="model-sha",
            context_preflight=context_report(messages), model_requests_enabled=True,
            prompt_manager=FakePromptManager())

        self.assertEqual(len(called), 1)
        self.assertEqual(result["attempt"]["status"], "valid_empty")
        self.assertTrue(result["attempt"]["source_provenance_complete"])
        self.assertEqual(result["attempt"]["cache_status"], "bypassed")
        self.assertEqual(result["attempt"]["transport_attempt_count"], 1)
        self.assertEqual(result["attempt"]["context_preflight"]["input_tokens"], 100)
        self.assertEqual(result["values"], [])
        self.assertNotIn("named_entities", result["attempt"])
        self.assertNotIn("response", result["attempt"])
        self.assertNotIn("prompt", result["attempt"])

    def test_truncated_recovered_partial_remains_unaccepted(self):
        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        result = execute_openie_task(
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
             "retry_of_attempt": 1},
            "title\ntext", None,
            request_fn=lambda *args, **kwargs: (
                '{"named_entities": ["partial"]}',
                {"finish_reason": "length", "prompt_tokens": 11,
                 "completion_tokens": 1024},
                {"cache_hit": False, "cache_status": "bypassed",
                 "transport_attempt_count": 1, "client_seconds": 0.2}),
            parse_fn=lambda stage, response, recover_partial: ["partial"],
            run_id="repair-run", model_digest="model-sha",
            context_preflight=context_report(messages), model_requests_enabled=True,
            prompt_manager=FakePromptManager())

        self.assertEqual(result["attempt"]["status"], "truncated")
        self.assertTrue(result["partial_recovery_succeeded"])
        self.assertIsNone(result["values"])

    def test_missing_usage_is_preserved_as_unknown_not_zero(self):
        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        result = execute_openie_task(
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
             "retry_of_attempt": 1},
            "title\ntext", None,
            request_fn=lambda *args, **kwargs: (
                '{"named_entities": []}', {"finish_reason": "stop"},
                {"cache_hit": False, "cache_status": "bypassed",
                 "transport_attempt_count": 1, "client_seconds": float("nan")}),
            parse_fn=lambda stage, response, recover_partial: [],
            run_id="repair-run", model_digest="model-sha",
            context_preflight=context_report(messages), model_requests_enabled=True,
            prompt_manager=FakePromptManager())

        self.assertEqual(result["attempt"]["status"], "valid_empty")
        self.assertEqual(result["attempt"]["usage"], {
            "prompt_tokens": None, "completion_tokens": None,
        })
        self.assertTrue(result["attempt"]["usage_unknown"])
        self.assertIsNone(result["attempt"]["client_seconds"])

    def test_request_error_does_not_claim_transport_was_sent(self):
        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        def before_send(*_args, **_kwargs):
            raise RuntimeError("before send")
        result = execute_openie_task(
            {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
             "retry_of_attempt": 1}, "title\ntext", None,
            request_fn=before_send, parse_fn=lambda *_args, **_kwargs: [],
            run_id="repair-run", model_digest="model-sha",
            context_preflight=context_report(messages), model_requests_enabled=True,
            prompt_manager=FakePromptManager())
        self.assertEqual(result["attempt"]["status"], "request_error")
        self.assertIsNone(result["attempt"]["transport_attempt_count"])

    def test_executor_rejects_unmarked_third_attempt_before_request(self):
        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        called = []
        with self.assertRaisesRegex(ValueError, "marked remedial"):
            execute_openie_task(
                {"passage_id": "p1", "stage": "openie_ner", "attempt": 3,
                 "retry_of_attempt": 2},
                "title\ntext", None,
                request_fn=lambda *args, **kwargs: called.append(True),
                parse_fn=lambda *args, **kwargs: [], run_id="repair-run",
                model_digest="model-sha", context_preflight=context_report(messages),
                model_requests_enabled=True, prompt_manager=FakePromptManager())
        self.assertEqual(called, [])

    def test_preflight_must_match_bound_transport(self):
        messages = render_openie_messages("openie_ner", "title\ntext",
                                          prompt_manager=FakePromptManager())
        calls = []
        def request(*args, **kwargs):
            calls.append(True)
        request.frozen_protocol = {"model": "qwen-test", "model_digest": "other",
                                   "seed": 42, "temperature": 0.0, "num_ctx": 4096}
        request.model_digest = "other"
        report = context_report(messages)
        report["protocol"].update({"model": "qwen-test", "model_digest": "model-sha"})
        with self.assertRaisesRegex(ValueError, "frozen transport"):
            execute_openie_task(
                {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                 "retry_of_attempt": 1}, "title\ntext", None,
                request_fn=request, parse_fn=lambda *_args, **_kwargs: [],
                run_id="repair", model_digest="model-sha",
                context_preflight=report, model_requests_enabled=True,
                prompt_manager=FakePromptManager())
        self.assertEqual(calls, [])

    def test_openai_compatible_adapter_fails_before_model_request(self):
        with self.assertRaisesRegex(RuntimeError, "does not forward num_ctx"):
            make_uncached_ollama_request(
                object(), protocol={"model": "qwen-test", "model_digest": "digest",
                                    "seed": 42, "temperature": 0.0, "num_ctx": 4096},
                model_digest="digest")

    def test_native_measurement_and_extraction_share_frozen_payload(self):
        protocol = {"model": "qwen-test", "model_digest": "digest",
                    "seed": 42, "temperature": 0.0, "num_ctx": 4096,
                    "ner_max_new_tokens": 1024}
        messages = [{"role": "user", "content": "synthetic"}]
        captured = []
        def post_json(payload):
            captured.append(payload)
            return {"message": {"content": '{"named_entities": []}'},
                    "done_reason": "stop", "prompt_eval_count": 12,
                    "eval_count": 8}
        request = make_native_ollama_request(
            "http://127.0.0.1:11434/v1", protocol=protocol,
            model_digest="digest", post_json=post_json)
        self.assertEqual(captured, [])
        content, metadata, meta = request(
            messages, max_new_tokens=1024,
            response_format={"type": "json_object"})
        self.assertEqual(content, '{"named_entities": []}')
        self.assertEqual(metadata, {"finish_reason": "stop",
                                    "prompt_tokens": 12,
                                    "completion_tokens": 8})
        self.assertEqual(meta["transport_attempt_count"], 1)
        self.assertEqual(captured, [native_chat_payload(
            messages, protocol=protocol, max_new_tokens=1024,
            response_format={"type": "json_object"})])
        self.assertEqual(captured[0]["options"], {
            "num_ctx": 4096, "num_predict": 1024,
            "seed": 42, "temperature": 0.0})
        self.assertIs(captured[0]["truncate"], False)
        self.assertEqual(captured[0]["format"], "json")

    def test_native_context_gate_runs_measurement_before_extraction(self):
        protocol = {"model": "qwen-test", "model_digest": "model-sha",
                    "seed": 42, "temperature": 0.0, "num_ctx": 4096,
                    "ner_max_new_tokens": 1024}
        task = {"passage_id": "p1", "stage": "openie_ner", "attempt": 2,
                "retry_of_attempt": 1}
        payloads = []
        def post_json(payload):
            payloads.append(payload)
            return {"message": {"content": '{"named_entities": []}'},
                    "done_reason": "stop", "prompt_eval_count": 100,
                    "eval_count": 1}
        request = make_native_ollama_request(
            "http://localhost:11434", protocol=protocol,
            model_digest="model-sha", post_json=post_json)
        kwargs = dict(request_fn=request,
                      parse_fn=lambda stage, response, recover_partial: [],
                      run_id="repair", model_digest="model-sha",
                      model_requests_enabled=True,
                      prompt_manager=FakePromptManager())
        result = measure_then_execute_openie_task(
            task, "title\ntext", None, **kwargs)
        self.assertEqual([p["options"]["num_predict"] for p in payloads],
                         [1, 1024])
        self.assertEqual(result["attempt"]["context_measurement_usage"],
                         {"prompt_tokens": 100, "completion_tokens": 1})
        payloads.clear()
        def over_budget(payload):
            payloads.append(payload)
            return {"message": {"content": "{}"}, "done_reason": "stop",
                    "prompt_eval_count": 3073, "eval_count": 1}
        kwargs["request_fn"] = make_native_ollama_request(
            "http://localhost:11434", protocol=protocol,
            model_digest="model-sha", post_json=over_budget)
        with self.assertRaisesRegex(ValueError, "exceed"):
            measure_then_execute_openie_task(task, "title\ntext", None, **kwargs)
        self.assertEqual(len(payloads), 1)


if __name__ == "__main__":
    unittest.main()
