"""Bounded smoke check of local BGE-M3 and the target chat API."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from dotenv import load_dotenv
import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "summary" / "target-api-check.json"
EMBED_INPUTS = (
    "Кошка сидит на окне",
    "В лаборатории сравнивают способы поиска документов",
)
QUESTION = "Ответь одним словом: сколько будет два плюс два?"
TOKEN_LIMIT = 50_000


def settings(environ):
    required = ("TARGET_API_BASE_URL", "LITELLM_API_KEY", "TARGET_API_MODEL")
    missing = [name for name in required if not environ.get(name)]
    if missing:
        raise ValueError("Missing required settings: " + ", ".join(missing))
    base = environ["TARGET_API_BASE_URL"].rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query:
        raise ValueError("TARGET_API_BASE_URL must be an HTTPS API base URL")
    if parsed.fragment or parsed.path.rstrip("/") != "/v1":
        raise ValueError("TARGET_API_BASE_URL must end in /v1")
    ollama = environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    local = urlsplit(ollama)
    if local.scheme != "http" or local.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("OLLAMA_BASE_URL must point to local HTTP Ollama")
    return {
        "base_url": base,
        "key": environ["LITELLM_API_KEY"],
        "model": environ["TARGET_API_MODEL"],
        "ollama_url": ollama,
        "embedding_model": environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest"),
    }


def finite_embeddings(payload):
    if not isinstance(payload, dict):
        raise ValueError("embedding_invalid_response")
    vectors = payload.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(EMBED_INPUTS):
        raise ValueError("embedding_count_mismatch")
    if any(not isinstance(vector, list) for vector in vectors):
        raise ValueError("embedding_dimension_mismatch")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1 or not dimensions or 0 in dimensions:
        raise ValueError("embedding_dimension_mismatch")
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for vector in vectors
        for value in vector
    ):
        raise ValueError("embedding_non_finite")
    return dimensions.pop()


def token_count(value):
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def local_embedding(session, config):
    base = config["ollama_url"]
    tags = session.get(f"{base}/api/tags", timeout=(5, 15))
    tags.raise_for_status()
    available = tags.json()
    if not isinstance(available, dict):
        raise ValueError("embedding_invalid_response")
    model = next(
        (
            row
            for row in available.get("models", [])
            if isinstance(row, dict)
            if row.get("name") == config["embedding_model"]
            or row.get("model") == config["embedding_model"]
        ),
        None,
    )
    if model is None:
        raise ValueError("local_embedding_model_missing")
    started = time.perf_counter()
    response = session.post(
        f"{base}/api/embed",
        json={
            "model": config["embedding_model"],
            "input": EMBED_INPUTS,
            "truncate": False,
        },
        timeout=(5, 120),
    )
    response.raise_for_status()
    payload = response.json()
    duration = time.perf_counter() - started
    dimension = finite_embeddings(payload)
    return {
        "status": "verified",
        "provider": "local_ollama",
        "model": config["embedding_model"],
        "digest": model.get("digest"),
        "input_count": len(EMBED_INPUTS),
        "vector_count": len(payload["embeddings"]),
        "dimension": dimension,
        "wall_seconds": round(duration, 3),
        "prompt_tokens": token_count(payload.get("prompt_eval_count")),
    }


def thinking_parameters(thinking_switch):
    if thinking_switch == "chat-template":
        return {"chat_template_kwargs": {"enable_thinking": False}}
    if thinking_switch == "top-level":
        return {"enable_thinking": False}
    raise ValueError("invalid_thinking_switch")


def remote_generation(session, config, max_tokens=32, thinking_switch="chat-template"):
    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": QUESTION}],
        "max_tokens": max_tokens,
        "stream": False,
        **thinking_parameters(thinking_switch),
    }
    started = time.perf_counter()
    response = session.post(
        f"{config['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {config['key']}"},
        json=payload,
        timeout=(5, 120),
        allow_redirects=False,
    )
    if 300 <= response.status_code < 400:
        raise ValueError("remote_redirect_refused")
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("remote_invalid_response")
    duration = time.perf_counter() - started
    usage = result.get("usage") or {}
    if not isinstance(usage, dict):
        raise ValueError("remote_invalid_response")
    input_tokens = token_count(usage.get("prompt_tokens"))
    output_tokens = token_count(usage.get("completion_tokens"))
    reported_total = token_count(usage.get("total_tokens"))
    if input_tokens is None or output_tokens is None:
        raise ValueError("remote_usage_missing")
    if max(input_tokens + output_tokens, reported_total or 0) > TOKEN_LIMIT:
        raise ValueError("remote_token_limit_exceeded")
    choices = result.get("choices") or []
    if not isinstance(choices, list) or (choices and not isinstance(choices[0], dict)):
        raise ValueError("remote_invalid_response")
    details = usage.get("completion_tokens_details") or {}
    if not isinstance(details, dict):
        details = {}
    message = choices[0].get("message") if choices else None
    content = message.get("content") if isinstance(message, dict) else None
    record = {
        "status": "verified" if isinstance(content, str) and content else "blocked",
        "model_requested": config["model"],
        "model_returned": result.get("model"),
        "request_parameters": {
            "max_tokens": max_tokens,
            "stream": False,
            **thinking_parameters(thinking_switch),
        },
        "thinking_mode_effect": (
            "reported_zero_reasoning_tokens"
            if token_count(details.get("reasoning_tokens")) == 0
            else "reported_reasoning_tokens"
            if token_count(details.get("reasoning_tokens")) is not None
            else "unknown"
        ),
        "answer": content if isinstance(content, str) and content else None,
        "finish_reason": choices[0].get("finish_reason") if choices else None,
        "response_id": result.get("id"),
        "wall_seconds": round(duration, 3),
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens_reported": reported_total,
        "reasoning_tokens": token_count(details.get("reasoning_tokens")),
    }
    if record["status"] == "blocked":
        record["error_kind"] = "remote_answer_missing"
    return record


def error_kind(exc):
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return f"http_{status}" if status is not None else "http_error"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.RequestException):
        return "network_error"
    if isinstance(exc, ValueError):
        return (
            str(exc)
            if str(exc)
            in {
                "local_embedding_model_missing",
                "embedding_count_mismatch",
                "embedding_dimension_mismatch",
                "embedding_non_finite",
                "embedding_invalid_response",
                "remote_usage_missing",
                "remote_invalid_response",
                "remote_token_limit_exceeded",
                "remote_answer_missing",
                "local_embedding_usage_missing",
                "remote_redirect_refused",
            }
            else "invalid_response"
        )
    return "unexpected_error"


def run(
    config,
    local_session,
    remote_session,
    generation_only=False,
    max_tokens=32,
    thinking_switch="chat-template",
):
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "kind": (
            "target_api_generation_diagnostic_not_benchmark"
            if generation_only
            else "target_api_smoke_not_benchmark"
        ),
        "remote_base_url": config["base_url"],
        "generation": {"status": "not_run"},
        "embeddings": {"status": "not_run"},
        "request_attempts": {
            "local_embedding": 0 if generation_only else None,
            "remote_generation": 0,
        },
        "daily_activity": "not_checked_endpoint_schema_unknown",
    }
    stage = "generation" if generation_only else "embeddings"
    try:
        if not generation_only:
            report["embeddings"] = local_embedding(local_session, config)
            report["request_attempts"]["local_embedding"] = 1
            if report["embeddings"]["prompt_tokens"] is None:
                raise ValueError("local_embedding_usage_missing")
        stage = "generation"
        report["request_attempts"]["remote_generation"] = 1
        report["generation"] = {
            "status": "started",
            "model_requested": config["model"],
            "request_parameters": {
                "max_tokens": max_tokens,
                "stream": False,
                **thinking_parameters(thinking_switch),
            },
            "prompt_tokens": None,
            "completion_tokens": None,
            "wall_seconds": None,
        }
        report["generation"] = remote_generation(
            remote_session,
            config,
            max_tokens=max_tokens,
            thinking_switch=thinking_switch,
        )
        report["status"] = report["generation"]["status"]
        if report["status"] == "blocked":
            report["error_kind"] = report["generation"]["error_kind"]
        elif not generation_only and (
            report["embeddings"]["prompt_tokens"]
            + max(
                report["generation"]["prompt_tokens"]
                + report["generation"]["completion_tokens"],
                report["generation"]["total_tokens_reported"] or 0,
            )
            > TOKEN_LIMIT
        ):
            report["status"] = "blocked"
            report["error_kind"] = "combined_token_limit_exceeded"
            report["generation"]["status"] = "blocked"
            report["generation"]["error_kind"] = report["error_kind"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        report["status"] = "blocked"
        report["error_kind"] = error_kind(exc)
        report[stage]["status"] = "blocked"
        report[stage]["error_kind"] = report["error_kind"]
        if stage == "generation":
            report["generation"]["usage_status"] = "unknown_not_captured"
    return report


def safe_json(report, secret):
    return (
        json.dumps(report, ensure_ascii=False, indent=2).replace(secret, "[redacted]")
        + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--generation-only",
        action="store_true",
        help="One bounded diagnostic chat request",
    )
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument(
        "--thinking-switch",
        choices=("top-level", "chat-template"),
        default="chat-template",
    )
    args = parser.parse_args()
    if not 1 <= args.max_tokens <= 256 or (
        not args.generation_only and args.max_tokens != 32
    ):
        raise SystemExit("Diagnostic max_tokens must be 1-256; standard smoke uses 32")
    if not args.generation_only and args.thinking_switch != "chat-template":
        raise SystemExit("Legacy thinking switch requires --generation-only")
    if args.output.exists():
        raise SystemExit("Refusing to overwrite existing target API report")
    load_dotenv(Path.cwd() / ".env.target-api", override=False)
    try:
        config = settings(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    with requests.Session() as local_session, requests.Session() as remote_session:
        report = run(
            config,
            local_session,
            remote_session,
            generation_only=args.generation_only,
            max_tokens=args.max_tokens,
            thinking_switch=args.thinking_switch,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(safe_json(report, config["key"]), encoding="utf-8")
    print(f"Target API smoke: {report['status']}; report: {args.output}")
    if report["status"] != "verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
