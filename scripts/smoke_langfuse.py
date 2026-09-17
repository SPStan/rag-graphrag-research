"""Send and read back a local Langfuse test trace without calling any LLM."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import time
from urllib.parse import urlparse
import uuid

from dotenv import dotenv_values
from langfuse import Langfuse, propagate_attributes


ROOT = Path(__file__).resolve().parents[1]
TRACE_NAME = "smoke-test-no-llm"
CHILD_NAME = "local-python-step"


def main():
    settings = dotenv_values(ROOT / ".env")
    required = ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    missing = [key for key in required if not settings.get(key)]
    if missing:
        raise SystemExit("Missing .env settings: " + ", ".join(missing))

    base_url = settings["LANGFUSE_BASE_URL"].rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("This smoke test expects the local Langfuse HTTP server.")

    run_id = "smoke-" + uuid.uuid4().hex[:12]
    client = Langfuse(
        public_key=settings["LANGFUSE_PUBLIC_KEY"],
        secret_key=settings["LANGFUSE_SECRET_KEY"],
        base_url=base_url,
        environment="local-smoke",
        timeout=10,
    )
    result = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_name": TRACE_NAME,
        "mode": "mock",
        "llm_calls": 0,
        "llm_tokens_spent": 0,
        "sdk_version": version("langfuse"),
        "status": "started",
    }
    try:
        if not client.auth_check():
            raise RuntimeError("Langfuse authentication failed. Check the local project keys.")

        with client.start_as_current_observation(
            as_type="span",
            name=TRACE_NAME,
            input={"message": "Проверка связи Python с локальным Langfuse"},
        ) as root:
            with propagate_attributes(
                trace_name=TRACE_NAME,
                tags=["smoke-test", "mock", "no-llm"],
                metadata={"run_id": run_id, "mode": "mock", "phase": "setup", "llm_calls": "0"},
            ):
                with client.start_as_current_observation(
                    as_type="span",
                    name=CHILD_NAME,
                    input={"operation": "local arithmetic", "a": 2, "b": 2},
                ) as child:
                    child.update(output={"result": 2 + 2, "generated_by": "Python, not an LLM"})
                root.update(output={"message": "Тестовая трасса отправлена", "mode": "mock"})
                result["trace_id"] = client.get_current_trace_id()

        # Delivery and query visibility are different: the worker processes data asynchronously.
        client.flush()
        result["status"] = "sent"
        print("Trace sent. Waiting for it to become readable in Langfuse...", flush=True)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            observations = client.api.observations.get_many(trace_id=result["trace_id"], limit=10)
            names = {observation.name for observation in observations.data}
            if {TRACE_NAME, CHILD_NAME}.issubset(names):
                result["status"] = "verified"
                result["observations_verified"] = sorted(names)
                result["trace_url"] = client.get_trace_url(trace_id=result["trace_id"])
                break
            time.sleep(2)
        else:
            raise RuntimeError("Trace was sent, but both observations were not readable within 45 seconds.")
    finally:
        # Write only test identifiers and results. Never serialize client settings or credentials.
        output_dir = ROOT / "results" / "smoke"
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = output_dir / f"{run_id}.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        client.shutdown()

    print(json.dumps(result, ensure_ascii=True, indent=2))
    print("Result file: " + str(result_path))


if __name__ == "__main__":
    main()
