import hashlib
import json
import unittest

from scripts.hipporag_repair_executor import (
    execute_openie_task, make_uncached_ollama_request, render_openie_messages,
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

    def test_cache_bypass_adapter_requires_zero_sdk_retries(self):
        class FakeResponse:
            pass

        class FakeClient:
            max_retries = 0

        class FakeLLM:
            max_retries = 0
            openai_client = FakeClient()
            def infer(self, messages, **kwargs):
                raise AssertionError("decorated infer must be bypassed")

        def direct_infer(self, messages, **kwargs):
            return "response", {"finish_reason": "stop"}

        # Mimic functools.wraps metadata on the pinned cache decorator.
        FakeLLM.infer.__wrapped__ = direct_infer
        callback = make_uncached_ollama_request(FakeLLM())
        response, metadata, request_meta = callback(
            [{"role": "user", "content": "x"}], max_new_tokens=10,
            response_format={"type": "json_object"})
        self.assertEqual(response, "response")
        self.assertEqual(metadata["finish_reason"], "stop")
        self.assertEqual(request_meta["cache_status"], "bypassed")
        self.assertEqual(request_meta["transport_attempt_count"], 1)


if __name__ == "__main__":
    unittest.main()
