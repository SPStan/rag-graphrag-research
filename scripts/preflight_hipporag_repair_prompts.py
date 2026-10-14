"""Read-only prompt rendering audit for the pinned HippoRAG OpenIE templates.

Run with the isolated HippoRAG environment. Audit/preflight modes never generate.
The separate --target-openie-check mode sends up to five verified saved cases,
with durable accounting and private request/response files; never calls Ollama.
"""

import argparse
import hashlib
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import statistics
import sqlite3
import subprocess
import uuid

try:
    from scripts.plan_hipporag_repair import (
        SOURCE_RUN_ID,
        build_plan_report,
        load_source_inputs,
    )
    from scripts.hipporag_repair_executor import render_openie_messages
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from plan_hipporag_repair import (
        SOURCE_RUN_ID,
        build_plan_report,
        load_source_inputs,
    )
    from hipporag_repair_executor import render_openie_messages

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff"
PROPOSED_RETRY_CAPS = {"openie_ner": 1024, "openie_triples": 3072}


def verify_native_cases(snapshot, counts, tokenizer):
    """Recompute every native count/SHA before any generation transport exists."""
    if hashlib.sha256(snapshot).hexdigest() != counts["source_snapshot_sha256"]:
        raise ValueError("case_snapshot_sha_mismatch")
    cases = json.loads(snapshot)
    if len(cases) != 5 or len(counts["cases"]) != 5:
        raise ValueError("expected_five_cases")
    for case, expected in zip(cases, counts["cases"]):
        source = case["source_attempt"]
        if (source["stage"], source["passage_id"]) != (
            expected["stage"],
            expected["passage_id"],
        ):
            raise ValueError("case_identity_mismatch")
        ids = tokenizer.apply_chat_template(
            case["messages"], tokenize=True, **counts["options"]
        )
        text = tokenizer.apply_chat_template(
            case["messages"], tokenize=False, **counts["options"]
        )
        cap = PROPOSED_RETRY_CAPS[source["stage"]]
        if (
            len(ids) != expected["input_tokens"]
            or hashlib.sha256(text.encode()).hexdigest() != expected["rendered_sha256"]
            or ids != tokenizer.encode(text, add_special_tokens=False)
            or cap != expected["output_cap"]
            or len(ids) + cap != expected["total_reserved"]
            or len(ids) + cap > counts["context_window"]
        ):
            raise ValueError("native_context_fit_mismatch")
    if sum(row["total_reserved"] for row in counts["cases"]) > 20_000:
        raise ValueError("planned_token_budget_exceeded")
    return cases


def claim_target_cases(data_root, snapshot_sha, run_id):
    """One run per source snapshot, shared by output dirs and worktrees."""
    directory = Path(data_root).resolve() / "results/raw/openie-target-claims"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot_sha}.claim.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"run_id": run_id, "snapshot_sha256": snapshot_sha}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def execute_target_cases(cases, counts, config, parse, session, directory, run_id):
    """At most five new requests; no resume, corrections or historical cache writes."""
    from scripts import run_dense as dense
    from scripts import run_dense_target as target
    from scripts.openie_protocol import classify_openie_attempt, VALID_STATUSES
    from scripts.token_accounting import Journal

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    journal = Journal(
        directory / "tokens.jsonl", run_id=run_id, method="hipporag2", dataset="musique"
    )
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "starting",
        "ready_for_indexing": False,
        "server_usage_verified": False,
        "token_budget": 20_000,
        "maximum_requests": 5,
        "automatic_retries": 0,
        "corrections": 0,
        "model": config["model"],
        "base_url": config["base_url"],
        "code": dense.git_snapshot(),
        "runner_sha256": dense.sha256_file(Path(__file__)),
        "native_count_contract": counts,
        "cases": [],
    }
    try:
        if (
            config["model"] != "iairlab/qwen3.8-27b"
            or len(cases) != 5
            or len(counts["cases"]) != 5
        ):
            raise ValueError("target_case_plan_mismatch")
        if session.get_adapter(config["base_url"]).max_retries.total != 0:
            raise ValueError("transport_retries_must_be_zero")
        for index, (case, expected) in enumerate(zip(cases, counts["cases"])):
            row = {
                "stage": expected["stage"],
                "passage_id": expected["passage_id"],
                "before_status": case["source_attempt"]["status"],
                "status": "starting",
                "local_input_tokens": expected["input_tokens"],
                "output_cap": expected["output_cap"],
                "rendered_sha256": expected["rendered_sha256"],
                "client_request_id": f"{run_id}-{index}",
            }
            result["cases"].append(row)
            headers = {
                "Authorization": "Bearer " + config["key"],
                "X-Client-Request-Id": f"{run_id}-{index}",
            }
            payload = {
                "model": config["model"],
                "messages": case["messages"],
                **target.OPTIONS,
                "max_tokens": expected["output_cap"],
                "response_format": {"type": "json_object"},
            }
            request_path, response_path = (
                directory / f"{index}.request.json",
                directory / f"{index}.response.json",
            )
            target.save_private_json(request_path, payload, headers)
            row["request_sha256"] = dense.sha256_file(request_path)
            dense.write_json_atomic(directory / "manifest.json", result)
            body = target.checked_post(
                session,
                config["base_url"] + "/chat/completions",
                payload,
                journal,
                phase="index",
                operation=expected["stage"],
                provider="target_api",
                model=config["model"],
                kind="llm",
                object_id=expected["passage_id"],
                headers=headers,
                response_path=response_path,
                token_limit=20_000,
            )
            row["response_sha256"] = dense.sha256_file(response_path)
            row["usage"] = body["usage"]
            row["returned_model"] = body.get("model")
            row["response_id"] = body.get("id")
            row["server_input_matches"] = (
                body["usage"]["prompt_tokens"] == expected["input_tokens"]
            )
            if not row["server_input_matches"]:
                row["status"] = "server_token_count_mismatch"
                raise ValueError("server_token_count_mismatch")
            choice = body["choices"][0]
            response = choice["message"]["content"]
            finish = choice.get("finish_reason")
            try:
                values = parse(expected["stage"], response, recover_partial=False)
                parse_error = False
            except (ValueError, TypeError, KeyError):
                values, parse_error = None, True
            row["finish_reason"] = finish
            row["status"] = classify_openie_attempt(
                response, finish, values, parse_error=parse_error
            )
            row["value_count"] = len(values) if isinstance(values, list) else None
            dense.write_json_atomic(directory / "manifest.json", result)
            if row["status"] not in VALID_STATUSES:
                raise ValueError("openie_result_not_accepted")
        result["server_usage_verified"] = True
        result["status"] = "completed"
    except Exception as exc:
        result["status"] = "failed"
        result["error_type"] = type(exc).__name__
        result["error_code"] = (
            str(exc)
            if isinstance(exc, ValueError) and str(exc).replace("_", "").isalnum()
            else "see_private_response"
        )
        if result["cases"] and result["cases"][-1]["status"] == "starting":
            result["cases"][-1]["status"] = "request_or_usage_error"
    finally:
        if result["cases"]:
            last_response = directory / f"{len(result['cases']) - 1}.response.json"
            if last_response.exists():
                result["cases"][-1]["response_sha256"] = dense.sha256_file(
                    last_response
                )
        result["token_accounting"] = journal.reference()
        dense.write_json_atomic(directory / "manifest.json", result)
    return result


def run_target_cases(args):
    """Bind verified immutable inputs, actual SDK parser and native tokenizer."""
    import requests
    from dotenv import dotenv_values
    from transformers import AutoTokenizer
    import transformers
    import tokenizers
    from scripts.check_target_api import settings
    from scripts.hipporag_repair_executor import make_pinned_openie_parser
    from scripts.run_dense import sha256_file, read_json, write_json_atomic

    counts = read_json(args.native_counts)
    preflight = read_json(args.source_preflight)
    config = settings(dotenv_values(args.env_file))
    if (
        transformers.__version__ != counts["runtime_transformers"]
        or tokenizers.__version__ != counts["runtime_tokenizers"]
    ):
        raise ValueError("native_tokenizer_runtime_mismatch")
    for name, expected in counts["files"].items():
        if sha256_file(args.native_tokenizer / name) != expected:
            raise ValueError("native_tokenizer_file_sha_mismatch")
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.native_tokenizer), local_files_only=True, trust_remote_code=False
    )
    tokenizer.chat_template = (args.native_tokenizer / "chat_template.jinja").read_text(
        encoding="utf-8"
    )
    snapshot = args.case_snapshot.read_bytes()
    if counts["source_snapshot_sha256"] != preflight["private_cases_sha256"]:
        raise ValueError("snapshot_not_bound_to_source_preflight")
    cases = verify_native_cases(snapshot, counts, tokenizer)
    _manager, files = verify_target_prompt_installation(args.sdk_source)
    manifest, _ids, _attempts, manifest_sha, corpus_sha = load_source_inputs(
        args.manifest, data_root=args.data_root
    )
    states = list(Path(manifest["storage_dir"]).rglob("openie_state.json"))
    caches = list(Path(manifest["storage_root"]).rglob("*.sqlite"))
    if len(states) != 1 or len(caches) != 1:
        raise ValueError("historical_storage_not_unique")
    paths = {
        "manifest": args.manifest,
        "corpus": args.data_root / manifest["inputs"]["corpus_path"],
        "state": states[0],
        "cache": caches[0],
    }
    before = {k: sha256_file(p) for k, p in paths.items()}
    if (
        before != preflight["source_hashes"]
        or before["manifest"] != manifest_sha
        or before["corpus"] != corpus_sha
    ):
        raise ValueError("historical_sources_changed")
    run_id = str(uuid.uuid4())
    claim_target_cases(args.data_root, counts["source_snapshot_sha256"], run_id)
    directory = ROOT / "results/raw" / f"openie-target-live-{run_id}"
    with requests.Session() as session:
        result = execute_target_cases(
            cases,
            counts,
            config,
            make_pinned_openie_parser(),
            session,
            directory,
            run_id,
        )
    result["source_unchanged_verified"] = before == {
        k: sha256_file(p) for k, p in paths.items()
    }
    result["installed_python_files_verified"] = files
    result["raw_directory"] = directory.name
    if not result["source_unchanged_verified"]:
        result["status"] = "failed"
        result["error_code"] = "historical_sources_changed"
    write_json_atomic(directory / "manifest.json", result)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": result["status"],
                "cases_attempted": len(result["cases"]),
                "error_code": result.get("error_code"),
            }
        )
    )
    if result["status"] != "completed":
        raise SystemExit(1)


def validate_upstream_pin(version, direct_url_text):
    """Require the isolated prompt library to match the recorded source pin."""
    if version != "2.0.0a5":
        raise ValueError("Installed HippoRAG version does not match the pinned package")
    try:
        direct_url = json.loads(direct_url_text)
        commit = direct_url["vcs_info"]["commit_id"]
    except (TypeError, ValueError, KeyError):
        raise ValueError(
            "Installed HippoRAG package has no verifiable VCS commit"
        ) from None
    if commit != UPSTREAM_COMMIT:
        raise ValueError(
            "Installed HippoRAG commit differs from the pinned prompt source"
        )
    return commit


def summarize_prompts(rows, *, model_digest, num_ctx, output_caps):
    """Summarize rendered prompt byte lengths; deliberately do not call them tokens."""
    if set(output_caps) != {"openie_ner", "openie_triples"}:
        raise ValueError("Both frozen stage output caps are required")
    by_stage = {}
    for stage in output_caps:
        selected = sorted(
            (row for row in rows if row["stage"] == stage), key=lambda row: row["order"]
        )
        lengths = [row["utf8_bytes"] for row in selected]
        by_stage[stage] = {
            "rendered_count": len(lengths),
            "max_rendered_prompt_utf8_bytes": max(lengths) if lengths else None,
            "median_rendered_prompt_utf8_bytes": (
                statistics.median(lengths) if lengths else None
            ),
            "max_output_tokens": output_caps[stage],
            "prompt_sha256_set": hashlib.sha256(
                "\n".join(row["prompt_sha256"] for row in selected).encode("ascii")
            ).hexdigest(),
        }
    return {
        "schema_version": 1,
        "status": "rendered_no_model_requests",
        "preflight_status": "not_ready_for_model_calls",
        "upstream_commit": UPSTREAM_COMMIT,
        "model_digest": model_digest,
        "num_ctx": num_ctx,
        "exact_prompt_token_counts": None,
        "by_stage": by_stage,
        "not_renderable_yet": {
            "stage": "openie_triples",
            "count": None,
            "reason": "Prompts for NER repairs depend on entity outputs not yet generated.",
        },
        "blocker": (
            "UTF-8 byte lengths are diagnostics, not tokenizer counts. Exact input-token "
            "fit against num_ctx cannot be verified by this no-model-call preflight."
        ),
        "model_requests_made": 0,
    }


def render_source_prompts(
    manifest, expected_ids, attempts, *, include_messages=False, data_root=None
):
    """Render exact prompts for stages whose input data is already known."""
    from hipporag.prompts import PromptTemplateManager

    # Only the private in-memory target list is needed here; it is never saved.
    try:
        from scripts.hipporag_repair import plan_openie_repairs
    except ModuleNotFoundError:
        from hipporag_repair import plan_openie_repairs
    targets = plan_openie_repairs(expected_ids, attempts)["targets"]

    corpus_path = Path(manifest["inputs"]["corpus_path"])
    if data_root is not None and not corpus_path.is_absolute():
        corpus_path = Path(data_root) / corpus_path
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    passage_by_id = {}
    try:
        from scripts.run_hipporag import canonical_key, passage_id
    except ModuleNotFoundError:
        from run_hipporag import canonical_key, passage_id
    for item in corpus:
        title, text = canonical_key(item["title"], item["text"])
        pid = item.get("id")
        if not pid:
            pid = passage_id(title, text)
        passage_by_id[pid] = title + "\n" + text

    state_files = list(Path(manifest["storage_dir"]).rglob("openie_state.json"))
    if len(state_files) != 1:
        raise ValueError("Expected exactly one source OpenIE state")
    state = json.loads(state_files[0].read_text(encoding="utf-8"))
    state_by_passage = {doc["passage"]: doc for doc in state["docs"]}
    latest = {}
    for row in attempts:
        key = (row["passage_id"], row["stage"])
        if key not in latest or row["attempt"] > latest[key]["attempt"]:
            latest[key] = row
    failed_ner_ids = {
        pid
        for pid in expected_ids
        if latest[(pid, "openie_ner")]["status"]
        not in {"valid_empty", "valid_nonempty"}
    }
    manager = PromptTemplateManager(
        role_mapping={
            "system": "system",
            "user": "user",
            "assistant": "assistant",
        }
    )
    rows = []
    pending_triples = 0
    for order, target in enumerate(targets):
        pid, stage = target["passage_id"], target["stage"]
        if stage == "openie_triples" and pid in failed_ner_ids:
            pending_triples += 1
            continue
        passage = passage_by_id[pid]
        if passage not in state_by_passage:
            raise ValueError("Source passage does not match persisted OpenIE state")
        if stage == "openie_ner":
            messages = render_openie_messages(stage, passage, prompt_manager=manager)
        else:
            entities = state_by_passage[passage].get("extracted_entities", [])
            messages = render_openie_messages(
                stage, passage, entities, prompt_manager=manager
            )
        serialized = json.dumps(
            messages,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        row = {
            "order": order,
            "passage_id": pid,
            "stage": stage,
            "utf8_bytes": len(serialized),
            "prompt_sha256": hashlib.sha256(serialized).hexdigest(),
        }
        if include_messages:
            row["messages"] = messages
        rows.append(row)

    return rows, pending_triples


def select_target_failure_cases(attempts):
    """Five fixed development examples: byte extremes per stage plus missing result."""
    latest = {}
    for item in attempts:
        key = (item["passage_id"], item["stage"])
        if key not in latest or item["attempt"] > latest[key]["attempt"]:
            latest[key] = item
    failed = [
        r
        for r in latest.values()
        if r["status"] not in {"valid_empty", "valid_nonempty"}
    ]
    selected = []
    for stage in ("openie_ner", "openie_triples"):
        rows = sorted(
            (r for r in failed if r["stage"] == stage and r["status"] == "truncated"),
            key=lambda r: (r["response_bytes"], r["passage_id"]),
        )
        if rows:
            selected.append(
                dict(
                    rows[0],
                    selection_reason="minimum historical truncated response bytes",
                )
            )
            if len(rows) > 1:
                selected.append(
                    dict(
                        rows[-1],
                        selection_reason="maximum historical truncated response bytes",
                    )
                )
    missing = sorted(
        (r for r in failed if r["status"] in {"request_error", "raw_response_missing"}),
        key=lambda r: (r["passage_id"], r["stage"]),
    )
    if missing:
        selected.append(
            dict(
                missing[0],
                selection_reason="historical request failure without response",
            )
        )
    return selected, failed


def target_capabilities(session, config):
    """Metadata GETs only; never retain server configuration or credentials."""
    origin = config["base_url"].removesuffix("/v1")
    fields = (
        "max_input_tokens",
        "max_output_tokens",
        "context_window",
        "tokenizer",
        "revision",
    )
    observed = []
    for route in ("/v1/models", "/model/info", "/v1/model/info"):
        if session.get_adapter(origin).max_retries.total != 0:
            raise ValueError("Metadata transport retries must be zero")
        try:
            reply = session.get(
                origin + route,
                headers={"Authorization": "Bearer " + config["key"]},
                params=None if route.endswith("models") else {"model": config["model"]},
                timeout=(5, 30),
                allow_redirects=False,
            )
            row = {"route": route, "http_status": reply.status_code}
            if reply.status_code == 200:
                records = reply.json().get("data", [])
                match = next(
                    (
                        r
                        for r in records
                        if r.get("id", r.get("model_name")) == config["model"]
                    ),
                    None,
                )
                info = (
                    (match.get("model_info", {}) if "info" in route else match)
                    if match
                    else {}
                )
                row["limits"] = {
                    k: info.get(k)
                    if isinstance(info.get(k), (str, int))
                    and not isinstance(info.get(k), bool)
                    and config["key"] not in str(info.get(k))
                    else None
                    for k in fields
                }
            observed.append(row)
        except Exception as exc:
            observed.append({"route": route, "error_type": type(exc).__name__})
    return observed


def verify_target_prompt_installation(source):
    """Verify the actual installed prompt/parser package against the pinned checkout."""
    from hipporag.prompts import PromptTemplateManager
    from hipporag import __file__ as installed_file

    source = Path(source).resolve(strict=True)
    commit = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={source.as_posix()}",
            "-C",
            str(source),
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError("SDK source revision mismatch")
    installed = Path(installed_file).parent
    files = list((source / "src" / "hipporag").rglob("*.py"))
    for path in files:
        relative = path.relative_to(source / "src" / "hipporag")
        if path.read_bytes().replace(b"\r\n", b"\n") != (
            installed / relative
        ).read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("Installed SDK file differs from pinned source")
    return PromptTemplateManager, len(files)


def run_target_preflight(args):
    """Issue #11 prerequisite audit; no generation route exists in this mode."""
    import requests
    from dotenv import dotenv_values
    from scripts.check_target_api import settings
    from scripts.openie_protocol import classify_openie_attempt
    from scripts.run_hipporag import sha256_file, write_json_atomic, git_snapshot
    from scripts.token_accounting import Journal
    from scripts.audit_openie import _response_kind
    from collections import Counter

    manifest, expected_ids, attempts, manifest_sha, corpus_sha = load_source_inputs(
        args.manifest, data_root=args.data_root
    )
    _manager, installed_files = verify_target_prompt_installation(args.sdk_source)
    storage = Path(manifest["storage_dir"])
    state = list(storage.rglob("openie_state.json"))
    caches = list(Path(manifest["storage_root"]).rglob("*.sqlite"))
    if len(state) != 1 or len(caches) != 1:
        raise ValueError("Exactly one historical state and SQLite cache required")
    hashes = {
        "manifest": manifest_sha,
        "corpus": corpus_sha,
        "state": sha256_file(state[0]),
        "cache": sha256_file(caches[0]),
    }
    cases, failed = select_target_failure_cases(attempts)
    wanted = {r.get("response_sha256") for r in cases if r.get("response_sha256")}
    cached = {}
    with sqlite3.connect(
        caches[0].as_uri() + "?mode=ro&immutable=1", uri=True
    ) as database:
        for message, metadata in database.execute(
            "SELECT message, metadata FROM cache"
        ):
            sha = hashlib.sha256(message.encode("utf-8")).hexdigest()
            if sha in wanted:
                cached[sha] = (message, json.loads(metadata))
    rendered, pending = render_source_prompts(
        manifest,
        expected_ids,
        attempts,
        include_messages=True,
        data_root=args.data_root,
    )
    prompts = {(r["passage_id"], r["stage"]): r for r in rendered}
    public, private = [], []
    for item in cases:
        entry = cached.get(item.get("response_sha256"))
        if item.get("response_sha256") and entry is None:
            raise ValueError("Selected historical response missing from verified cache")
        raw = entry[0] if entry else None
        status = classify_openie_attempt(
            raw,
            item.get("finish_reason"),
            [],
            request_error=item["status"] == "request_error",
        )
        if status != item["status"]:
            raise ValueError("Selected historical status cannot be reproduced")
        prompt = prompts.get((item["passage_id"], item["stage"]))
        public.append(
            {
                "passage_id": item["passage_id"],
                "stage": item["stage"],
                "selection_reason": item["selection_reason"],
                "historical_status": status,
                "historical_attempt": item["attempt"],
                "response_sha256": item.get("response_sha256"),
                "historical_response_shape": _response_kind(raw)
                if raw is not None
                else "absent",
                "historical_usage": item.get("usage"),
                "historical_usage_unknown": item.get("usage_unknown"),
                "prompt_sha256": prompt["prompt_sha256"] if prompt else None,
                "prompt_utf8_bytes": prompt["utf8_bytes"] if prompt else None,
                "exact_input_tokens": None,
                "proposed_output_cap": PROPOSED_RETRY_CAPS[item["stage"]],
                "target_status": "not_attempted_context_limits_unknown"
                if prompt is not None
                else "not_attempted_ner_dependency",
                "target_cost": None,
            }
        )
        private.append(
            {
                "source_attempt": item,
                "raw_response": raw,
                "cache_metadata": entry[1] if entry else None,
                "messages": prompt["messages"] if prompt else None,
            }
        )
    config = settings(dict(dotenv_values(args.env_file)))
    with requests.Session() as session:
        capabilities = target_capabilities(session, config)
    run_id = str(uuid.uuid4())
    raw_dir = ROOT / "results" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    private_path = raw_dir / f"openie-target-{run_id}.cases.json"
    write_json_atomic(private_path, private)
    journal = Journal(
        raw_dir / f"openie-target-{run_id}.tokens.jsonl",
        run_id=run_id,
        method="hipporag2",
        dataset=manifest["dataset"],
    )
    report = {
        "schema_version": 1,
        "kind": "issue11_target_openie_preflight",
        "run_id": run_id,
        "status": "blocked_target_context_contract",
        "source_run_id": manifest["run_id"],
        "code": {
            **git_snapshot(),
            "preflight_source_sha256": sha256_file(Path(__file__)),
            "protocol_source_sha256": sha256_file(
                ROOT / "scripts" / "openie_protocol.py"
            ),
        },
        "source_hashes": hashes,
        "installed_upstream_commit": UPSTREAM_COMMIT,
        "installed_python_files_verified": installed_files,
        "target_model": config["model"],
        "target_base_url": config["base_url"],
        "capability_checks": capabilities,
        "historical_terminal_failures": len(failed),
        "by_stage_status": dict(
            Counter(r["stage"] + "/" + r["status"] for r in failed)
        ),
        "selection": "Two response-byte extremes per truncated stage plus one missing-response case from historical development run; no evaluation answers or support labels used",
        "cases": public,
        "pending_dependent_triple_prompts": pending,
        "private_cases_file": private_path.name,
        "private_cases_sha256": sha256_file(private_path),
        "model_requests_made": 0,
        "token_accounting": journal.reference(),
        "ready_for_indexing": False,
        "blocker": "No tokenizer-backed per-prompt target context-fit contract is available. Provider metadata and user do not currently confirm context/output limits and tokenizer/backend revision; metadata observations are recorded, bytes and historical local counts are not target token counts.",
        "next_required_input": "Confirmed target context/output limits and tokenizer revision or exact server token-count endpoint; then separately bounded check of these five cases, maximum two corrections per cause",
    }
    after = {
        "manifest": sha256_file(args.manifest),
        "corpus": sha256_file(Path(args.data_root) / manifest["inputs"]["corpus_path"]),
        "state": sha256_file(state[0]),
        "cache": sha256_file(caches[0]),
    }
    if after != hashes:
        raise ValueError("Historical artifacts changed during read-only preflight")
    report["source_unchanged_verified"] = True
    output = (
        args.output or ROOT / "results" / "summary" / "openie-target-preflight.json"
    )
    if output.exists():
        raise ValueError("Refusing to overwrite an existing target preflight")
    write_json_atomic(output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "selected_cases": len(public),
                "model_requests_made": 0,
                "run_id": run_id,
            }
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT
        / "results"
        / "raw"
        / f"hipporag2-musique-{SOURCE_RUN_ID}.manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--target-api-check",
        action="store_true",
        help="issue #11 metadata/read-only preflight; no generation",
    )
    parser.add_argument(
        "--target-openie-check",
        action="store_true",
        help="send up to five verified saved cases; stops at first failure, no retry",
    )
    parser.add_argument("--case-snapshot", type=Path)
    parser.add_argument(
        "--native-counts",
        type=Path,
        default=ROOT / "results/summary/openie-target-context-counts.json",
    )
    parser.add_argument(
        "--source-preflight",
        type=Path,
        default=ROOT / "results/summary/openie-target-preflight.json",
    )
    parser.add_argument(
        "--native-tokenizer",
        type=Path,
        default=ROOT
        / ".cache/qwen38-tokenizer/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
    )
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--sdk-source", type=Path, default=ROOT / ".cache" / "hipporag-sdk-1438aba3"
    )
    args = parser.parse_args(argv)
    if args.target_openie_check:
        if args.target_api_check or args.case_snapshot is None or args.env_file is None:
            parser.error(
                "--target-openie-check requires --case-snapshot/--env-file and excludes --target-api-check"
            )
        run_target_cases(args)
        return
    if args.target_api_check:
        if args.env_file is None:
            parser.error("--target-api-check requires --env-file")
        run_target_preflight(args)
        return
    if args.output is None:
        args.output = (
            ROOT / "results" / "summary" / "hipporag-repair-prompt-preflight.json"
        )
    manifest, expected_ids, attempts, manifest_sha, corpus_sha = load_source_inputs(
        args.manifest
    )
    distribution = importlib_metadata.distribution("hipporag")
    upstream_commit = validate_upstream_pin(
        distribution.version, distribution.read_text("direct_url.json")
    )
    rows, pending = render_source_prompts(manifest, expected_ids, attempts)
    plan_report = build_plan_report(
        manifest["run_id"],
        expected_ids,
        attempts,
        manifest_sha256=manifest_sha,
        corpus_sha256=corpus_sha,
    )
    report = summarize_prompts(
        rows,
        model_digest=manifest["generation"]["model"]["digest"],
        num_ctx=manifest["generation"]["options"]["num_ctx"],
        output_caps=PROPOSED_RETRY_CAPS,
    )
    report["output_caps_source"] = (
        "ADR-0008 retry-cap proposal; must be frozen before execution"
    )
    report.update(
        {
            "source_run_id": manifest["run_id"],
            "hipporag_package_version": distribution.version,
            "installed_upstream_commit": upstream_commit,
            "source_manifest_sha256": manifest_sha,
            "source_corpus_sha256": corpus_sha,
            "plan_sha256": plan_report["plan_sha256"],
            "not_renderable_yet": {
                "stage": "openie_triples",
                "count": pending,
                "reason": "Triple prompts depend on new NER repair outputs.",
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "preflight_status": report["preflight_status"],
                "rendered_prompts": sum(
                    item["rendered_count"] for item in report["by_stage"].values()
                ),
                "pending_triple_prompts": pending,
                "exact_prompt_token_counts": None,
                "model_requests_made": 0,
                "report": args.output.name,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
