"""Bounded Dense target smoke, reusing Dense retrieval, reader and evaluator."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time
import uuid

from dotenv import load_dotenv
import requests

from scripts import check_target_api as api
from scripts import evaluate_dense as evaluator
from scripts import run_dense as dense
from scripts.evaluation_view import ordered_ids_sha256, select_in_view
from scripts.token_accounting import Journal, recorded_call

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("musique", "hotpotqa")
OPTIONS = {
    "temperature": 0,
    "seed": 42,
    "max_tokens": 512,
    "stream": False,
    "chat_template_kwargs": {"enable_thinking": False},
}
TOKEN_LIMIT = 100_000  # Combined local embedding and remote LLM tokens, per dataset.
INPUT_BYTE_LIMIT = 16_000


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def prepare(dataset, data_root):
    """Validate full pinned input, then select development questions and corpus."""
    directory = Path(data_root) / "data" / "processed" / dataset
    queries = dense.read_json(directory / "queries.json")
    corpus = dense.read_json(directory / "corpus.json")
    provenance = dense.validate_processed_data(
        dataset, directory, queries, corpus, directory / "labels.json"
    )
    split_path = ROOT / "data" / "ids" / f"{dataset}_comparison_split.json"
    split = dense.read_json(split_path)
    ids_path = ROOT / "data" / "ids" / f"{dataset}_s500.json"
    ids = dense.read_json(ids_path)["question_ids"][:5]
    if (
        split["source_sha256"] != dense.sha256_file(ids_path)
        or not set(ids) <= set(split["signal_tuning_ids"])
        or set(ids) & set(split["signal_check_ids"])
        or set(ids) & set(split["legacy_holdout_reserved_ids"])
    ):
        raise ValueError("smoke_ids_not_in_verified_development_split")
    selected_queries = select_in_view(queries, ids, "query")
    labels = select_in_view(dense.read_json(directory / "labels.json"), ids, "label")
    supporting = {pid for row in labels for pid in row["supporting_ids"]}
    by_id = {row["id"]: row for row in corpus}
    if not supporting <= by_id.keys():
        raise ValueError("supporting_passage_missing")
    distractors = [row["id"] for row in corpus if row["id"] not in supporting][:20]
    selected_ids = supporting | set(distractors)
    selected_corpus = [row for row in corpus if row["id"] in selected_ids]
    plan = {
        "schema_version": 1,
        "kind": "dense_target_functionality_check",
        "dataset": dataset,
        "selection": "first 5 S500 IDs within signal_tuning; supporting union + first 20 other corpus IDs",
        "question_ids": ids,
        "ordered_question_ids_sha256": ordered_ids_sha256(ids),
        "passage_ids": [row["id"] for row in selected_corpus],
        "corpus_sha256": digest(selected_corpus),
        "queries_sha256": digest(selected_queries),
        "split_sha256": dense.sha256_file(split_path),
        "inputs": provenance,
        "reader_prompt_version": dense.READER_PROMPT_VERSION,
        "reader_template_sha256": dense.reader_template_sha256(),
        "generation_options": OPTIONS,
        "top_k": 5,
        "token_limit_per_dataset": TOKEN_LIMIT,
        "reader_input_byte_limit": INPUT_BYTE_LIMIT,
        "limitations": "Development smoke; support-preserving small corpus, not a quality benchmark. MuSiQue reader template is shared unchanged with HotpotQA for this smoke.",
    }
    return plan, selected_queries, selected_corpus, labels


def checked_post(
    session,
    url,
    payload,
    journal,
    *,
    phase,
    operation,
    provider,
    model,
    kind,
    object_id,
    headers=None,
    response_path=None,
    token_limit=TOKEN_LIMIT,
):
    # Conservative request reservation; no tokenizer/backend context limit is inferred.
    reserve = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
    if kind == "llm":
        reserve += payload.get("max_tokens", OPTIONS["max_tokens"])
    known = sum(journal.summary()["known_subtotal"].values())
    if known + reserve > token_limit:
        raise ValueError("token_budget_reservation_exceeded")

    def send():
        response = session.post(
            url, json=payload, headers=headers, timeout=(5, 120), allow_redirects=False
        )
        try:
            body = response.json()
        except ValueError:
            body = {"unparsed_response_text": response.text}
            if response_path is not None:
                save_private_json(response_path, body, headers)
            response.raise_for_status()
            raise ValueError("invalid_response_json") from None
        if response_path is not None:
            save_private_json(response_path, body, headers)
        if 300 <= response.status_code < 400:
            raise ValueError("redirect_refused")
        response.raise_for_status()
        return body

    result = recorded_call(
        journal,
        send,
        phase=phase,
        operation=operation,
        provider=provider,
        model=model,
        kind=kind,
        object_id=object_id,
    )
    summary = journal.summary()
    if not summary["complete"]:
        raise ValueError("missing_usage_stop")
    if sum(summary["known_subtotal"].values()) > token_limit:
        raise ValueError("token_budget_exceeded")
    return result


def save_private_json(path, body, headers=None):
    """Store response/prompt locally without retaining the supplied credential."""
    authorization = (headers or {}).get("Authorization", "")
    secret = authorization.removeprefix("Bearer ")
    text = json.dumps(body, ensure_ascii=False)
    if secret:
        text = text.replace(secret, "[redacted]")
    dense.write_json_atomic(path, json.loads(text))


def response_diagnostics(body):
    choices = body.get("choices") if isinstance(body, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else None
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    usage = body.get("usage") if isinstance(body, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("completion_tokens_details")
    details = details if isinstance(details, dict) else {}
    return {
        "structure_status": "valid" if isinstance(message, dict) else "invalid",
        "finish_reason": choice.get("finish_reason")
        if isinstance(choice, dict)
        else None,
        "content_type": type(content).__name__,
        "content_present": isinstance(content, str) and bool(content.strip()),
        "answer_extraction_status": dense.extract_target_reader_answer(content)[1]
        if isinstance(content, str)
        else "content_not_string",
        "prompt_tokens": api.token_count(usage.get("prompt_tokens")),
        "completion_tokens": api.token_count(usage.get("completion_tokens")),
        "reasoning_tokens": api.token_count(details.get("reasoning_tokens")),
    }


def execute(plan, queries, corpus, labels, config, local, remote, output_dir):
    """No retry/replay; persist each accepted answer and all transport attempts."""
    dataset = plan["dataset"]
    run_id = str(uuid.uuid4())
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"dense-{dataset}-{run_id}.jsonl"
    manifest_path = output.with_suffix(".manifest.json")
    journal = Journal(
        output.with_suffix(".tokens.jsonl"),
        run_id=run_id,
        method="dense",
        dataset=dataset,
    )
    manifest = {
        "run_id": run_id,
        "dataset": dataset,
        "status": "starting",
        "mode": "target-functionality-smoke",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "expected_question_ids": plan["question_ids"],
        "plan": plan,
        "plan_sha256": digest(plan),
        "code": dense.git_snapshot(),
        "results_file": output.name,
        "errors": [],
        "generation": {
            "requested_model": config["model"],
            "base_url": config["base_url"],
            "options": OPTIONS,
            "backend_revision": "unknown",
        },
        "retrieval": {"method": "cosine", "top_k": 5},
    }
    dense.write_json_atomic(manifest_path, manifest)
    rows = []
    current = None
    response_path = None
    options = plan.get("generation_options", OPTIONS)
    token_limit = plan.get("token_limit_per_dataset", TOKEN_LIMIT)
    manifest["generation"]["options"] = options
    manifest["reader_attempts"] = []
    try:
        for session, base in (
            (local, config["ollama_url"]),
            (remote, config["base_url"]),
        ):
            if session.get_adapter(base).max_retries.total != 0:
                raise ValueError("transport_retries_must_be_zero")
        tags = local.get(f"{config['ollama_url']}/api/tags", timeout=(5, 15))
        tags.raise_for_status()
        embedding_info = next(
            row
            for row in tags.json()["models"]
            if row.get("name") == config["embedding_model"]
        )
        if not embedding_info.get("digest"):
            raise ValueError("embedding_digest_missing")
        model = config["embedding_model"]

        def embed(texts, phase, object_id):
            result = checked_post(
                local,
                f"{config['ollama_url']}/api/embed",
                {"model": model, "input": texts, "truncate": False},
                journal,
                phase=phase,
                operation=f"{phase}_embedding",
                provider="local_ollama",
                model=model,
                kind="embedding",
                object_id=object_id,
                token_limit=token_limit,
            )
            vectors = result.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError("embedding_count_mismatch")
            matrix = dense.normalize_rows(vectors)
            if matrix.shape[1] != 1024:
                raise ValueError("bge_m3_dimension_mismatch")
            return matrix, result["prompt_eval_count"]

        matrices, index_tokens = [], 0
        for offset in range(0, len(corpus), 8):
            matrix, tokens = embed(
                [
                    f"{row['title']}\n{row['text']}"
                    for row in corpus[offset : offset + 8]
                ],
                "index",
                f"corpus:{offset}",
            )
            matrices.append(matrix)
            index_tokens += tokens
        document_vectors = dense.np.concatenate(matrices)
        manifest["embedding"] = {
            "model": embedding_info,
            "truncate": False,
            "text_version": dense.EMBED_TEXT_VERSION,
            "batch_size": 8,
        }
        manifest["runtime"] = {
            "python": platform.python_version(),
            "requests": requests.__version__,
        }
        manifest["code"]["source_sha256"]["scripts/run_dense_target.py"] = (
            dense.sha256_file(Path(__file__))
        )
        manifest["index_embedding"] = {
            "cache_hit": False,
            "api_batches": len(matrices),
            "embedding_prompt_tokens": index_tokens,
        }
        with output.open("x", encoding="utf-8") as stream:
            for query in queries:
                current = query["id"]
                began = time.perf_counter()
                query_vectors, query_tokens = embed(
                    [query["question"]], "retrieval", current
                )
                ranked = dense.top_k(query_vectors[0], document_vectors, 5)
                passages = [corpus[i] for i, _ in ranked]
                messages = dense.build_reader_messages(query["question"], passages)
                if (
                    len(json.dumps(messages, ensure_ascii=False).encode())
                    > INPUT_BYTE_LIMIT
                ):
                    raise ValueError("reader_input_byte_limit_exceeded")
                request_path = output.with_name(
                    f"{output.stem}-{digest(current)[:16]}.reader-request.json"
                )
                response_path = output.with_name(
                    f"{output.stem}-{digest(current)[:16]}.reader-response.json"
                )
                request_payload = {
                    "model": config["model"],
                    "messages": messages,
                    **options,
                }
                save_private_json(
                    request_path,
                    {
                        "payload": request_payload,
                        "retrieved": [
                            {
                                "id": p["id"],
                                "score": score,
                                "title": p["title"],
                                "text": p["text"],
                            }
                            for p, (_, score) in zip(passages, ranked)
                        ],
                    },
                )
                manifest["reader_attempts"].append(
                    {
                        "question_id": current,
                        "request_file": request_path.name,
                        "request_sha256": dense.sha256_file(request_path),
                        "prompt_sha256": digest(messages),
                        "response_file": response_path.name,
                    }
                )
                dense.write_json_atomic(manifest_path, manifest)
                response = checked_post(
                    remote,
                    f"{config['base_url']}/chat/completions",
                    request_payload,
                    journal,
                    phase="reader",
                    operation="reader",
                    provider="target_api",
                    model=config["model"],
                    kind="llm",
                    object_id=current,
                    headers={"Authorization": f"Bearer {config['key']}"},
                    response_path=response_path,
                    token_limit=token_limit,
                )
                diagnostics = response_diagnostics(response)
                if (
                    diagnostics["structure_status"] != "valid"
                    or not diagnostics["content_present"]
                ):
                    raise ValueError("reader_response_structure_invalid")
                choice = response["choices"][0]
                raw = choice["message"]["content"]
                answer, status = dense.extract_target_reader_answer(raw)
                if choice.get("finish_reason") != "stop" or status != "ok":
                    manifest["failed_reader_response"] = {
                        "question_id": current,
                        "file": response_path.name,
                        "sha256": dense.sha256_file(response_path),
                        "finish_reason": choice.get("finish_reason"),
                        "answer_extraction_status": status,
                    }
                    raise ValueError("reader_format_or_finish_reason_invalid")
                row = {
                    "run_id": run_id,
                    "dataset": dataset,
                    "question_id": current,
                    "mode": manifest["mode"],
                    "planned_question_ids": plan["question_ids"],
                    "embedding_model": embedding_info,
                    "generation_model": {"name": config["model"]},
                    "model_returned": response.get("model"),
                    "reader_prompt_version": dense.READER_PROMPT_VERSION,
                    "reader_prompt_sha256": digest(messages),
                    "generation_options": options,
                    "top_k": 5,
                    "retrieved": [
                        {"id": p["id"], "score": score}
                        for p, (_, score) in zip(passages, ranked)
                    ],
                    "answer": answer,
                    "raw_answer": raw,
                    "answer_extraction_status": status,
                    "answer_parser_version": dense.TARGET_ANSWER_PARSER_VERSION,
                    "prompt_tokens": response["usage"]["prompt_tokens"],
                    "completion_tokens": response["usage"]["completion_tokens"],
                    "query_embedding_prompt_tokens": query_tokens,
                    "done_reason": choice["finish_reason"],
                    "done": True,
                    "question_end_to_end_seconds": time.perf_counter() - began,
                }
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                rows.append(row)
        manifest["status"] = "completed"
        manifest["results_sha256"] = dense.sha256_file(output)
        metrics = evaluator.evaluate(rows, labels, manifest=manifest)
        dense.write_json_atomic(output.with_suffix(".metrics.json"), metrics)
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["errors"] = [
            {
                "question_id": current,
                "code": type(exc).__name__,
                "reason": str(exc)
                if isinstance(exc, ValueError)
                else "transport_or_response_error",
            }
        ]
    finally:
        for attempt in manifest["reader_attempts"]:
            saved_response = output.parent / attempt["response_file"]
            if saved_response.exists():
                attempt["response_sha256"] = dense.sha256_file(saved_response)
                attempt["diagnostics"] = response_diagnostics(
                    dense.read_json(saved_response)
                )
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["observed_question_ids"] = [row["question_id"] for row in rows]
        manifest["uncompleted_question_ids"] = [
            i
            for i in plan["question_ids"]
            if i not in manifest["observed_question_ids"]
        ]
        manifest["token_accounting"] = journal.reference()
        manifest["question_outcomes"] = [
            {
                "question_id": qid,
                "status": "completed"
                if qid in manifest["observed_question_ids"]
                else "failed"
                if qid == current
                else "not_attempted_after_stop",
            }
            for qid in plan["question_ids"]
        ]
        dense.write_json_atomic(manifest_path, manifest)
    return manifest_path, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--dataset", choices=DATASETS, help="restrict to one dataset")
    parser.add_argument(
        "--diagnostic-question", help="one ID from the frozen five-question plan"
    )
    parser.add_argument(
        "--diagnostic-prior-run",
        type=Path,
        help="verified first diagnostic manifest; cumulative budget 20000",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="spend tokens: at most 5 sequential reader calls per dataset",
    )
    args = parser.parse_args()
    prepared = [prepare(dataset, args.data_root) for dataset in DATASETS]
    plan_path = ROOT / "results" / "summary" / "dense-target-smoke-plan.json"
    plans = {"datasets": [item[0] for item in prepared]}
    if (
        plan_path.exists()
        and dense.read_json(plan_path).get("datasets") != plans["datasets"]
    ):
        raise SystemExit("Refusing to change an existing smoke plan")
    if not plan_path.exists():
        dense.write_json_atomic(plan_path, plans)
    if args.dataset:
        prepared = [item for item in prepared if item[0]["dataset"] == args.dataset]
    if args.diagnostic_question:
        if not args.dataset:
            raise SystemExit("Diagnostic requires --dataset")
        plan, queries, corpus, labels = prepared[0]
        if args.diagnostic_question not in plan["question_ids"]:
            raise SystemExit(
                "Diagnostic ID must belong to the frozen five-question plan"
            )
        parent_sha = digest(plan)
        plan = dict(
            plan,
            kind="dense_target_reader_diagnostic",
            parent_plan_sha256=parent_sha,
            question_ids=[args.diagnostic_question],
            token_limit_per_dataset=20000,
        )
        plan["ordered_question_ids_sha256"] = ordered_ids_sha256(plan["question_ids"])
        plan["queries_sha256"] = digest(
            select_in_view(queries, plan["question_ids"], "query")
        )
        if args.diagnostic_prior_run:
            from scripts.token_accounting import verified_reference

            prior = dense.read_json(args.diagnostic_prior_run)
            prior_summary = verified_reference(prior, args.diagnostic_prior_run)[
                "summary"
            ]
            if (
                not prior_summary["complete"]
                or prior["plan"].get("kind") != plan["kind"]
                or prior["plan"].get("parent_plan_sha256") != parent_sha
                or prior["expected_question_ids"] != plan["question_ids"]
                or prior["plan"].get("diagnostic_prior_run_id")
                or sum(
                    p["attempts"]
                    for p in prior_summary["phases"]
                    if p["phase"] == "reader"
                )
                != 1
                or any(p["errors"] for p in prior_summary["phases"])
            ):
                raise SystemExit("Prior diagnostic is not eligible for another attempt")
            plan["diagnostic_prior_run_id"] = prior["run_id"]
            plan["token_limit_per_dataset"] -= sum(
                prior_summary["known_subtotal"].values()
            )
        prepared = [
            (
                plan,
                select_in_view(queries, plan["question_ids"], "query"),
                corpus,
                select_in_view(labels, plan["question_ids"], "label"),
            )
        ]
    elif args.diagnostic_prior_run:
        raise SystemExit("Prior run requires --diagnostic-question")
    prepared = [
        (
            dict(
                plan,
                answer_parser_version=dense.TARGET_ANSWER_PARSER_VERSION,
                embedding_batch_size=8,
            ),
            queries,
            corpus,
            labels,
        )
        for plan, queries, corpus, labels in prepared
    ]
    stored_plans = dense.read_json(plan_path)
    version = {
        "answer_parser_version": dense.TARGET_ANSWER_PARSER_VERSION,
        "parent_plans_sha256": digest(stored_plans["datasets"]),
        "embedding_batch_size": 8,
        "generation_options": OPTIONS,
        "reader_template_sha256": dense.reader_template_sha256(),
    }
    versions = stored_plans.setdefault("execution_versions", {})
    if (
        dense.TARGET_ANSWER_PARSER_VERSION in versions
        and versions[dense.TARGET_ANSWER_PARSER_VERSION] != version
    ):
        raise SystemExit("Refusing to change a frozen execution version")
    versions[dense.TARGET_ANSWER_PARSER_VERSION] = version
    dense.write_json_atomic(plan_path, stored_plans)
    if not args.execute:
        print("Plan verified; no model requests.")
        return
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    config = api.settings(os.environ)
    if (
        config["model"] != "iairlab/qwen3.8-27b"
        or config["embedding_model"] != "bge-m3:latest"
    ):
        raise SystemExit("Target smoke requires the pinned Qwen3.8 and BGE-M3")
    with requests.Session() as local, requests.Session() as remote:
        for plan, queries, corpus, labels in prepared:
            path, manifest = execute(
                plan,
                queries,
                corpus,
                labels,
                config,
                local,
                remote,
                ROOT / "results" / "raw",
            )
            print(f"{plan['dataset']}: {manifest['status']}; {path}")
            if manifest["status"] != "completed":
                raise SystemExit(
                    "Stopped at first failed dataset; inspect manifest before any further requests"
                )


if __name__ == "__main__":
    main()
