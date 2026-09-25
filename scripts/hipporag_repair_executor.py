"""One-task OpenIE repair executor; guarded against accidental model requests."""

import hashlib
import json
import math
import threading
import time

try:
    from scripts.openie_protocol import classify_openie_attempt
    from scripts.run_hipporag import record_openie_attempt
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from openie_protocol import classify_openie_attempt
    from run_hipporag import record_openie_attempt

VALID_STATUSES = {"valid_empty", "valid_nonempty"}


def render_openie_messages(stage, passage, named_entities=None, *, prompt_manager=None):
    """Render the pinned upstream extraction prompt without calling a model."""
    if not isinstance(passage, str) or not passage:
        raise ValueError("OpenIE passage must be a non-empty string")
    if prompt_manager is None:
        from hipporag.prompts import PromptTemplateManager
        prompt_manager = PromptTemplateManager(role_mapping={
            "system": "system", "user": "user", "assistant": "assistant",
        })
    if stage == "openie_ner":
        return prompt_manager.render(name="ner", passage=passage)
    if stage == "openie_triples":
        if (not isinstance(named_entities, list)
                or any(not isinstance(value, str) or not value.strip()
                       for value in named_entities)):
            raise ValueError("Triple extraction requires validated entity strings")
        return prompt_manager.render(
            name="triple_extraction", passage=passage,
            named_entity_json=json.dumps({"named_entities": named_entities},
                                         ensure_ascii=False),
        )
    raise ValueError("Unknown OpenIE repair stage")


def validate_context_preflight(report, *, model_digest, num_ctx, output_cap,
                               prompt_sha256, stage, temperature, seed,
                               response_format):
    """Require a verified per-prompt token count under the same frozen config."""
    if not isinstance(report, dict) or report.get("status") != "context_fit_verified":
        raise ValueError("A tokenizer-backed context-fit report is required")
    if (report.get("model_digest") != model_digest
            or report.get("num_ctx") != num_ctx
            or report.get("max_new_tokens") != output_cap
            or report.get("prompt_sha256") != prompt_sha256
            or report.get("temperature") != temperature
            or report.get("seed") != seed
            or report.get("stage") != stage
            or report.get("response_format") != response_format):
        raise ValueError("Context preflight does not match this exact request")
    input_tokens = report.get("input_tokens")
    if (not isinstance(input_tokens, int) or isinstance(input_tokens, bool)
            or input_tokens < 0 or input_tokens + output_cap > num_ctx):
        raise ValueError("Prompt and output budget exceed the configured context")
    return input_tokens


def make_uncached_ollama_request(llm, *, protocol, model_digest):
    """Reject the incompatible OpenAI route before any model request.

    Ollama 0.34.4's OpenAI middleware drops ``extra_body.options.num_ctx``.
    A callback that claims a frozen context through this route is unsafe.
    """
    raise RuntimeError(
        "Ollama OpenAI-compatible chat does not forward num_ctx; "
        "a verified context-preserving transport is required")


def make_pinned_openie_parser():
    """Build the parser callback from the pinned HippoRAG installation."""
    from hipporag.information_extraction.openie_openai import (
        _extract_json_list_field, _extract_ner_from_response,
    )
    from hipporag.utils.llm_utils import fix_broken_generated_json, filter_invalid_triples
    try:
        from scripts.run_hipporag import normalize_ner_entities
    except ModuleNotFoundError:
        from run_hipporag import normalize_ner_entities

    def parse(stage, response, *, recover_partial):
        parsed = fix_broken_generated_json(response) if recover_partial else response
        if stage == "openie_ner":
            return normalize_ner_entities(_extract_ner_from_response(parsed))
        if stage == "openie_triples":
            triples = _extract_json_list_field(parsed, "triples")
            return filter_invalid_triples(triples=triples)
        raise ValueError("Unknown OpenIE repair stage")

    return parse


def execute_openie_task(task, passage, named_entities, *, request_fn, parse_fn,
                        run_id, model_digest, context_preflight,
                        model_requests_enabled=False, prompt_manager=None):
    """Execute a single planned task only after explicit and exact preflight.

    `request_fn` is called only when `model_requests_enabled` is explicitly
    true and the context report verifies this exact prompt/model/cap tuple.
    Raw prompts and responses are never returned in the attempt record.
    """
    if model_requests_enabled is not True:
        raise RuntimeError("Model requests are disabled for this run")
    stage = task.get("stage")
    attempt_number = task.get("attempt")
    if (not isinstance(attempt_number, int) or isinstance(attempt_number, bool)
            or attempt_number not in (2, 3)):
        raise ValueError("Repair task has an invalid attempt number")
    if attempt_number == 3 and task.get("remedial_retry") is not True:
        raise ValueError("Attempt 3 must be explicitly marked remedial")
    if task.get("retry_of_attempt") != attempt_number - 1:
        raise ValueError("Repair task must link to the immediately preceding attempt")
    if (not isinstance(task.get("passage_id"), str)
            or not task["passage_id"]):
        raise ValueError("Repair task needs a stable passage ID")
    if task.get("operation") == "dependency_refresh":
        dependency_attempt = task.get("dependency_attempt")
        if (task.get("dependency_stage") != "openie_ner"
                or not isinstance(dependency_attempt, int)
                or isinstance(dependency_attempt, bool)
                or task.get("dependency_attempt_pending") is True):
            raise ValueError("Triple refresh must link to the completed corrected NER attempt")
    stage_caps = {"openie_ner": "ner_max_new_tokens",
                  "openie_triples": "triples_max_new_tokens"}
    cap_key = stage_caps.get(stage)
    if cap_key is None:
        raise ValueError("Repair task has an unknown stage")
    # The frozen config is carried in the preflight document and must have
    # separate stage caps; the current report intentionally does not pass.
    protocol = context_preflight.get("protocol") if isinstance(context_preflight, dict) else None
    if not isinstance(protocol, dict):
        raise ValueError("Context report is missing the frozen repair protocol")
    transport_protocol = getattr(request_fn, "frozen_protocol", None)
    if transport_protocol is not None:
        if (getattr(request_fn, "model_digest", None) != model_digest
                or any(transport_protocol.get(key) != protocol.get(key)
                       for key in ("model", "model_digest", "seed", "temperature", "num_ctx"))):
            raise ValueError("Context report differs from frozen transport protocol")
    output_cap = protocol.get(cap_key)
    num_ctx = protocol.get("num_ctx")
    if (not isinstance(output_cap, int) or isinstance(output_cap, bool)
            or output_cap <= 0 or not isinstance(num_ctx, int)
            or isinstance(num_ctx, bool) or num_ctx <= output_cap):
        raise ValueError("Frozen context and output cap are invalid")

    messages = render_openie_messages(
        stage, passage, named_entities, prompt_manager=prompt_manager)
    serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), default=str).encode("utf-8")
    prompt_hash = hashlib.sha256(serialized).hexdigest()
    input_tokens = validate_context_preflight(
        context_preflight, model_digest=model_digest, num_ctx=num_ctx,
        output_cap=output_cap, prompt_sha256=prompt_hash, stage=stage,
        temperature=protocol.get("temperature"), seed=protocol.get("seed"),
        response_format={"type": "json_object"})
    try:
        response, metadata, request_meta = request_fn(
            messages, max_new_tokens=output_cap,
            response_format={"type": "json_object"})
    except Exception as exc:
        response, metadata = None, {}
        request_meta = {
            "cache_hit": False, "cache_status": "bypassed",
            "transport_attempt_count": None,
            "client_seconds": None, "error_type": type(exc).__name__,
        }
        request_error = True
    else:
        request_error = False
    if not isinstance(metadata, dict):
        metadata = {}
    if (not isinstance(request_meta, dict)
            or request_meta.get("cache_status") != "bypassed"
            or request_meta.get("cache_hit") is not False
            or (not request_error and request_meta.get("transport_attempt_count") != 1)
            or (request_error and request_meta.get("transport_attempt_count") is not None)):
        raise ValueError("Request callback did not prove one cache-bypassed transport call")

    values, parse_error = None, False
    if not request_error and isinstance(response, str) and response:
        try:
            parsed = parse_fn(stage, response,
                              recover_partial=metadata.get("finish_reason") == "length")
            if stage == "openie_ner":
                if not isinstance(parsed, list) or any(
                        not isinstance(value, str) or not value.strip()
                        for value in parsed):
                    raise ValueError("Parsed NER output has invalid shape")
            elif not isinstance(parsed, list) or any(
                    not isinstance(triple, (list, tuple)) or len(triple) != 3
                    or any(not isinstance(value, str) or not value.strip()
                           for value in triple) for triple in parsed):
                raise ValueError("Parsed triple output has invalid shape")
            values = [list(row) if stage == "openie_triples" else row
                      for row in parsed]
        except Exception:
            parse_error = True

    status = classify_openie_attempt(
        response, metadata.get("finish_reason"), values,
        parse_error=parse_error, request_error=request_error)
    accepted_values = values if status in VALID_STATUSES else None
    usage = {}
    usage_unknown = False
    for key in ("prompt_tokens", "completion_tokens"):
        value = metadata.get(key)
        if (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            usage[key] = None
            usage_unknown = True
        else:
            usage[key] = value
    client_seconds = request_meta.get("client_seconds")
    if (not isinstance(client_seconds, (int, float))
            or isinstance(client_seconds, bool) or not math.isfinite(client_seconds)
            or client_seconds < 0):
        client_seconds = None
    event = {
        "prompt_sha256": prompt_hash,
        "cache_hit": False,
        "usage": usage,
        "usage_unknown": usage_unknown,
        "client_seconds": client_seconds,
    }
    attempts = []
    record_openie_attempt(
        attempts, threading.Lock(), run_id=run_id, pid=task["passage_id"], passage=passage,
        stage=stage, attempt_number=attempt_number, response=response,
        metadata=metadata, values=values, model_digest=model_digest,
        call_event=event, parse_error=parse_error, request_error=request_error,
        retry_of_attempt=task.get("retry_of_attempt"))
    record = attempts[0]
    record["cache_status"] = request_meta["cache_status"]
    record["transport_attempt_count"] = request_meta["transport_attempt_count"]
    record["context_preflight"] = {
        "num_ctx": num_ctx, "input_tokens": input_tokens,
        "output_cap": output_cap, "fit_verified": True,
    }
    if attempt_number == 3:
        record["remedial_retry"] = True
    if request_meta.get("error_type"):
        record["request_error_type"] = request_meta["error_type"]
    for key in ("operation", "dependency_stage", "dependency_attempt"):
        if key in task:
            record[key] = task[key]
    return {"attempt": record, "values": accepted_values,
            "partial_recovery_succeeded": record["partial_recovery_succeeded"]}
