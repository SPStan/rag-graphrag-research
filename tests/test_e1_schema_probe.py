import copy
import json
from unittest.mock import patch

import pytest
import requests

from scripts import run_dense as dense
from scripts import run_e1 as e1
from scripts.token_accounting import Journal


def test_probe_changes_only_format_and_reserves_before_http():
    original = {
        **e1.target.OPTIONS,
        "model": "qwen",
        "max_tokens": 3072,
        "messages": [{"role": "user", "content": "текст"}],
        "response_format": {"type": "json_object"},
    }
    before = copy.deepcopy(original)
    payload, reserve = e1.schema_probe_payload(original)
    assert original == before
    assert {k: v for k, v in payload.items() if k != "response_format"} == {
        k: v for k, v in original.items() if k != "response_format"
    }
    assert (
        reserve == len(json.dumps(payload, ensure_ascii=False).encode()) + 2048 + 3072
    )
    assert (
        payload["response_format"]["json_schema"]["schema"]["properties"]["triples"][
            "uniqueItems"
        ]
        is True
    )
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError, match="context"):
            e1.schema_probe_payload(
                {**original, "messages": [{"role": "user", "content": "x" * 262144}]}
            )


@pytest.mark.parametrize(
    "change",
    [
        "length",
        "unknown",
        "duplicate",
        "empty_string",
        "ragged",
        "extra",
        "partial",
        "duplicate_field",
    ],
)
def test_probe_never_accepts_partial_duplicate_or_unknown(change):
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"triples":[["A","in","B"]]}'},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    if change == "length":
        body["choices"][0]["finish_reason"] = "length"
    elif change == "unknown":
        body["usage"].pop("prompt_tokens")
    else:
        body["choices"][0]["message"]["content"] = {
            "duplicate": '{"triples":[["A","in","B"],["A","in","B"]]}',
            "empty_string": '{"triples":[["A","in"," "]]}',
            "ragged": '{"triples":[["A","B"]]}',
            "extra": '{"triples":[],"named_entities":[]}',
            "partial": '{"triples":[["A","in","B"]',
            "duplicate_field": '{"triples":[],"triples":[]}',
        }[change]
    with pytest.raises(ValueError):
        e1.validate_schema_probe_response(body)


def test_probe_accepts_strict_unique_json_but_does_not_assert_fact_support():
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"triples":[["A","in","B"]]}'},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    assert e1.validate_schema_probe_response(body) == [["A", "in", "B"]]


@pytest.mark.parametrize("changed_ner", [False, True])
def test_prepare_reconstructs_both_original_hashes_without_http(tmp_path, changed_ner):
    corpus = [
        {"id": str(i), "title": f"Title{i}", "text": f"text{i}"} for i in range(2)
    ]
    output = tmp_path / "stopped"
    (output / "requests").mkdir(parents=True)
    dense.write_json_atomic(output / "manifest.json", {"status": "failed"})

    class Manager:
        def __init__(self, **kwargs):
            pass

        def render(self, *, name, passage, **kwargs):
            return [{"role": "user", "content": f"{name}:{passage}:{kwargs}"}]

    cache, failures, repairs = {}, [], {}
    for doc in corpus:
        passage = f"{doc['title']}\n{doc['text']}"
        ner = {
            **e1.target.OPTIONS,
            "model": "qwen",
            "messages": Manager().render(name="ner", passage=passage),
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }
        ner_key = e1.target.digest(
            {"payload": ner, "kind": "llm", "operation": "openie_ner"}
        )
        path = tmp_path / f"ner-{doc['id']}.json"
        dense.write_json_atomic(
            path,
            {
                "choices": [
                    {"message": {"content": json.dumps({"named_entities": ["A"]})}}
                ]
            },
        )
        cache[ner_key] = {
            "path": path,
            "sha256": dense.sha256_file(path),
            "run_id": "producer",
        }
        original = {
            **ner,
            "messages": Manager().render(
                name="triple_extraction",
                passage=passage,
                named_entity_json=json.dumps({"named_entities": ["A"]}),
            ),
            "max_tokens": 3072,
        }
        key = e1.target.digest(
            {"payload": original, "kind": "llm", "operation": "openie_triples"}
        )
        failures.append(({"object_id": key}, {"usage_status": "complete"}, {}))
        repairs[key] = {"status": "started"}
        dense.write_json_atomic(
            output / "requests" / f"{key}.response.json",
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": json.dumps({"triples": [["A", "in", "B"]] * 15})[
                                :-2
                            ]
                        },
                    }
                ]
            },
        )
    dense.write_json_atomic(output / "cycle-repairs.json", repairs)
    if changed_ner:
        dense.write_json_atomic(
            tmp_path / "ner-0.json",
            {"choices": [{"message": {"content": '{"named_entities":["Changed"]}'}}]},
        )
    row = {
        "method": "hipporag2",
        "dataset": "musique",
        "output": "stopped",
        "resume_sources": [],
        "corpus": {},
        "corpus_fingerprint": dense.corpus_fingerprint(corpus),
        "token_limit": 100000,
    }
    prior = tmp_path / "plan.json"
    dense.write_json_atomic(
        prior,
        {
            "workspace": str(tmp_path),
            "data_root": str(tmp_path),
            "model": "qwen",
            "rows": [row],
        },
    )
    with (
        patch(
            "scripts.preflight_hipporag_repair_prompts.verify_target_prompt_installation",
            return_value=(Manager, 61),
        ),
        patch.object(
            e1,
            "verified_checkpoints",
            return_value=(
                cache,
                failures,
                {"summary": {"known_subtotal": {"llm_input_tokens": 20}}},
            ),
        ),
        patch.object(e1, "load_corpus", return_value=(corpus, {})),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        if changed_ner:
            with pytest.raises(ValueError, match="sha_not_reconstructed"):
                e1.prepare_schema_probe(prior, tmp_path)
        else:
            prepared = e1.prepare_schema_probe(prior, tmp_path)
            assert prepared["status"] == "prepared_offline_requires_approval"
            assert prepared["max_new_posts"] == 2
            assert prepared["ner_posts"] == 0
            assert prepared["remaining_hippo_budget_before_probe"] == 99980
            assert set(repairs) == {
                c["original_request_sha256"] for c in prepared["cases"]
            }
            assert prepared["reserved_tokens_upper_bound"] == sum(
                c["reserved_tokens_upper_bound"] for c in prepared["cases"]
            )


@pytest.mark.parametrize("compatible", [False, True])
@pytest.mark.parametrize(
    "outcome,posts",
    [
        ("success", 2),
        ("bounded_success", 2),
        ("length", 1),
        ("unknown", 1),
        ("http_error", 1),
        ("second_unknown", 2),
        ("connection_error", 1),
        ("bad_approval", 0),
        ("active_worker", 0),
    ],
)
def test_approved_probe_bounds_posts_claims_and_preserves_spending(
    tmp_path, outcome, posts, compatible
):
    from unittest.mock import Mock

    failed = tmp_path / "stopped"
    failed.mkdir()
    journal = Journal(
        failed / "usage.jsonl", run_id="old", method="hipporag2", dataset="musique"
    )
    a = journal.start(
        phase="index",
        operation="openie_triples",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    journal.finish(
        a,
        status="success" if outcome == "bounded_success" else "unknown",
        usage={
            "llm_input_tokens": 7,
            **({"llm_output_tokens": 0} if outcome == "bounded_success" else {}),
        },
    )
    dense.write_json_atomic(
        failed / "manifest.json",
        {
            "run_id": "old",
            "status": "failed",
            "seconds": 1,
            "token_accounting": journal.reference(),
            "artifacts": {"usage.jsonl": dense.sha256_file(journal.path)},
        },
    )
    row = {
        "method": "hipporag2",
        "dataset": "musique",
        "run_id": "old",
        "output": "stopped",
    }
    plan = {
        "workspace": str(tmp_path),
        "model": "qwen",
        "endpoint": "https://example.invalid/v1",
        "batch_id": "batch",
        "embedding_model": "bge",
        "embedding_digest": "digest",
        "parameters": {},
        "combined_token_limit": 68000000,
        "rows": [row],
    }
    if outcome == "active_worker":
        plan["rows"].append(
            {"method": "raptor", "dataset": "musique", "output": "busy"}
        )
        (tmp_path / "busy").mkdir()
        (tmp_path / "busy/running.lock").write_text("123", encoding="utf-8")
    prior = tmp_path / "prior.json"
    dense.write_json_atomic(prior, plan)
    legacy = tmp_path / "musique-schema-probe1"
    if compatible:
        legacy.mkdir()
        old_journal = Journal(
            legacy / "usage.jsonl",
            run_id="legacy-schema",
            method="hipporag2",
            dataset="musique",
        )
        old_attempt = old_journal.start(
            phase="index",
            operation="openie_triples",
            provider="target_api",
            model="qwen",
            kind="llm",
        )
        old_journal.finish(old_attempt, status="unknown")
        dense.write_json_atomic(
            legacy / "manifest.json",
            {
                "status": "failed",
                "run_id": "legacy-schema",
                "seconds": 1,
                "parent_manifest_sha256": dense.sha256_file(failed / "manifest.json"),
                "token_accounting": old_journal.reference(),
                "unknown_reserved_upper_bound": 8679,
                "artifacts": {"usage.jsonl": dense.sha256_file(old_journal.path)},
                "full_index_authorized": False,
                "cases": [],
            },
        )
    prepared = {
        "max_new_posts": 2,
        "failed_manifest_sha256": dense.sha256_file(failed / "manifest.json"),
        "cases": [],
    }
    for i in range(2):
        payload, reserve = e1.schema_probe_payload(
            {
                "model": "qwen",
                "max_tokens": 3072,
                "messages": [{"role": "user", "content": str(i)}],
                "response_format": {"type": "json_object"},
            },
            compatible=compatible,
        )
        prepared["cases"].append(
            {
                "source_id": str(i),
                "payload": payload,
                "request_sha256": e1.target.digest(
                    {"payload": payload, "kind": "llm", "operation": "openie_triples"}
                ),
                "reserved_tokens_upper_bound": reserve,
            }
        )
    prepared["reserved_tokens_upper_bound"] = sum(
        c["reserved_tokens_upper_bound"] for c in prepared["cases"]
    )
    if compatible:
        prepared.update(
            variant="shape_local_unique_v2",
            code_commit="new",
            timeout_seconds=[30, 300],
            execution_authorized=False,
            prior_failed_schema_manifest_sha256=dense.sha256_file(
                legacy / "manifest.json"
            ),
        )
    probe_path = tmp_path / "probe.json"
    dense.write_json_atomic(probe_path, prepared)
    sha = dense.sha256_file(probe_path)
    body = {
        "choices": [
            {
                "finish_reason": "length" if outcome == "length" else "stop",
                "message": {"content": '{"triples":[["A","in","B"]]}'},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    if outcome == "unknown":
        body["usage"].pop("completion_tokens")
    session = requests.Session()
    response = Mock(status_code=200)
    response.json.return_value = body
    if outcome == "http_error":
        response.status_code = 400
        response.raise_for_status.side_effect = requests.HTTPError("schema unsupported")
    sent_responses = [response]
    if outcome == "second_unknown":
        second = Mock(status_code=200)
        second.json.return_value = {**body, "usage": {"prompt_tokens": 10}}
        sent_responses.append(second)

    def post(*args, **kwargs):
        assert (
            failed
            / (
                "schema-shape-probe-once.claim.json"
                if compatible
                else "schema-probe-once.claim.json"
            )
        ).exists()
        if outcome == "connection_error":
            raise requests.ConnectionError("transport unavailable")
        return sent_responses.pop(0) if outcome == "second_unknown" else response

    session.post = Mock(side_effect=post)
    config = {
        "TARGET_API_MODEL": "qwen",
        "TARGET_API_BASE_URL": plan["endpoint"],
        "LITELLM_API_KEY": "test-secret",
    }
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "git", return_value="new"),
        patch.object(e1, "prepare_schema_probe", return_value=prepared),
        patch.object(e1.requests, "Session", return_value=session),
    ):
        if outcome in ("success", "bounded_success"):
            output = e1.execute_schema_probe(
                probe_path, prior, tmp_path, config, sha, compatible=compatible
            )
        else:
            with pytest.raises(
                (ValueError, requests.HTTPError, requests.ConnectionError)
            ):
                e1.execute_schema_probe(
                    probe_path,
                    prior,
                    tmp_path,
                    config,
                    "wrong" if outcome == "bad_approval" else sha,
                    compatible=compatible,
                )
            output = tmp_path / (
                "musique-schema-shape-probe1" if compatible else "musique-schema-probe1"
            )
        assert session.post.call_count == posts
        if posts:
            manifest = dense.read_json(output / "manifest.json")
            assert manifest["full_index_authorized"] is False
            assert manifest["token_accounting"]["summary"]["attempts"] == posts
            assert manifest["status"] == (
                "completed" if outcome in ("success", "bounded_success") else "failed"
            )
            for call in session.post.call_args_list:
                assert call.kwargs["allow_redirects"] is False
                assert call.kwargs["timeout"] == ((30, 300) if compatible else (5, 300))
                assert call.kwargs["json"]["max_tokens"] == 3072
            with pytest.raises(ValueError, match="output_already_exists"):
                e1.execute_schema_probe(
                    probe_path, prior, tmp_path, config, sha, compatible=compatible
                )
            assert session.post.call_count == posts
            (tmp_path / "results/summary").mkdir(parents=True)
            report = e1.export(plan, prior)
            expected = (
                7 + posts * 18
                if outcome
                not in ("unknown", "http_error", "second_unknown", "connection_error")
                else 35
                if outcome == "second_unknown"
                else 17
                if outcome == "unknown"
                else 7
            )
            assert report["physical_known_tokens"] == expected
            assert report["cost_complete"] == (
                outcome == "bounded_success" and not compatible
            )
            if outcome == "bounded_success":
                assert report["budget_charge_upper_bound"] == expected + (
                    8679 if compatible else 0
                )
                assert report["budget_reservation_complete"] is True
            assert (
                report["rows"][0][
                    "schema_shape_probe" if compatible else "schema_probe"
                ]["status"]
                == manifest["status"]
            )
            if compatible:
                assert (
                    report["rows"][0]["schema_probe"]["unknown_reserved_upper_bound"]
                    == 8679
                )
                assert (
                    report["rows"][0]["cumulative_accounting"]["attempts"] == posts + 2
                )
                for call in session.post.call_args_list:
                    assert "uniqueItems" not in json.dumps(
                        call.kwargs["json"]["response_format"]
                    )
            if outcome in (
                "unknown",
                "http_error",
                "second_unknown",
                "connection_error",
            ):
                assert manifest["unknown_reserved_upper_bound"] > 0
                # The synthetic parent has unknown usage without a saved bound.
                # A probe reserve cannot make the whole history's bound complete.
                assert report["budget_charge_upper_bound"] is None
                assert report["budget_reservation_complete"] is False
        else:
            assert not (
                failed
                / (
                    "schema-shape-probe-once.claim.json"
                    if compatible
                    else "schema-probe-once.claim.json"
                )
            ).exists()


def test_compatible_schema_keeps_shape_and_local_duplicate_rejection():
    original = {
        **e1.target.OPTIONS,
        "model": "qwen",
        "max_tokens": 3072,
        "messages": [{"role": "user", "content": "passage + cached NER"}],
        "response_format": {"type": "json_object"},
    }
    payload, reserve = e1.schema_probe_payload(original, compatible=True)
    schema = payload["response_format"]["json_schema"]
    assert "uniqueItems" not in json.dumps(schema)
    assert schema["schema"]["properties"]["triples"]["items"]["minItems"] == 3
    assert payload["messages"] == original["messages"]
    assert payload["max_tokens"] == 3072
    assert reserve > 3072
    duplicated = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"triples":[["A","in","B"],["A","in","B"]]}'},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    with pytest.raises(ValueError, match="duplicate"):
        e1.validate_schema_probe_response(duplicated)


@pytest.mark.parametrize(
    "field,value", [("completion_tokens", 3073), ("prompt_tokens", 262144)]
)
def test_schema_probe_rejects_reported_usage_beyond_output_or_context_cap(field, value):
    body = {
        "choices": [
            {"finish_reason": "stop", "message": {"content": '{"triples":[]}'}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    body["usage"][field] = value
    with pytest.raises(ValueError, match="exceeds_cap"):
        e1.validate_schema_probe_response(body)
