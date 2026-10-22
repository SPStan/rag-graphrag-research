import copy
import json
from pathlib import Path
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
        ("second_duplicate", 2),
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
    if outcome in ("second_unknown", "second_duplicate"):
        second = Mock(status_code=200)
        second.json.return_value = (
            {**body, "usage": {"prompt_tokens": 10}}
            if outcome == "second_unknown"
            else {
                **body,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"triples":[["A","in","B"],["A","in","B"]]}'
                        },
                    }
                ],
            }
        )
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
        return (
            sent_responses.pop(0)
            if outcome in ("second_unknown", "second_duplicate")
            else response
        )

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
            if outcome == "second_duplicate":
                diag = report["rows"][0][
                    "schema_shape_probe" if compatible else "schema_probe"
                ]["failure_diagnostic"]
                assert diag["finish_reason"] == "stop"
                assert diag["repetition"]["complete_tuples"] == 2
                assert diag["repetition"]["unique_tuples"] == 1
                assert diag["request_sha256"] == prepared["cases"][1]["request_sha256"]
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


@pytest.fixture
def adoption_case(tmp_path, monkeypatch):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    prior = tmp_path / "prior.json"
    dense.write_json_atomic(
        prior,
        {
            "model": "qwen",
            "rows": [
                {"method": "hipporag2", "dataset": "musique", "output": "hippo/stopped"}
            ],
        },
    )
    directory = tmp_path / "hippo/musique-schema-shape-probe1"
    (directory / "requests").mkdir(parents=True)
    journal = Journal(
        directory / "usage.jsonl",
        run_id="producer",
        method="hipporag2",
        dataset="musique",
    )
    prepared = {"code_commit": "old", "failed_manifest_sha256": "parent", "cases": []}
    for i in range(2):
        payload, _ = e1.schema_probe_payload(
            {
                **e1.target.OPTIONS,
                "model": "qwen",
                "messages": [{"role": "user", "content": str(i)}],
                "max_tokens": 3072,
                "response_format": {"type": "json_object"},
            },
            compatible=True,
        )
        key = e1.target.digest(
            {"payload": payload, "kind": "llm", "operation": "openie_triples"}
        )
        prepared["cases"].append(
            {
                "payload": payload,
                "request_sha256": key,
                "original_request_sha256": f"original{i}",
                "ner_response_sha256": f"ner{i}",
                "source_id": str(i),
            }
        )
        body = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": '{"triples":[["A","in","B"],["A","in","B"]]}'
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }
        dense.write_json_atomic(directory / f"requests/{key}.response.json", body)
        attempt = journal.start(
            phase="index",
            operation="openie_triples",
            provider="target_api",
            model="qwen",
            kind="llm",
            object_id=key,
        )
        journal.finish(
            attempt, status="success", usage=e1.extract_usage(body, "llm", "target_api")
        )
    probe = tmp_path / "probe.json"
    dense.write_json_atomic(probe, prepared)
    manifest = {
        "status": "failed",
        "run_id": "producer",
        "schema_variant": "shape_local_unique_v2",
        "approved_plan_sha256": dense.sha256_file(probe),
        "parent_manifest_sha256": "parent",
        "unknown_reserved_upper_bound": 0,
        "token_accounting": journal.reference(),
        "artifacts": {
            p.relative_to(directory).as_posix(): dense.sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file()
        },
    }
    dense.write_json_atomic(directory / "manifest.json", manifest)
    monkeypatch.setattr(
        e1,
        "prepare_schema_probe",
        lambda *a, **kw: {**prepared, "code_commit": "current"},
    )

    def parse(stage, text, *, recover_partial):
        assert stage == "openie_triples" and recover_partial is False
        return [
            list(t)
            for t in dict.fromkeys(tuple(t) for t in json.loads(text)["triples"])
        ]

    monkeypatch.setattr(
        "scripts.hipporag_repair_executor.make_pinned_openie_parser", lambda: parse
    )
    monkeypatch.setattr(
        "requests.sessions.Session.request",
        lambda *a, **k: pytest.fail("HTTP forbidden"),
    )
    return prior, probe, directory, prepared


def test_offline_adoption_keeps_failed_and_physical_cost(adoption_case):
    prior, probe, directory, _ = adoption_case
    old = (directory / "manifest.json").read_bytes()
    record, cache = e1.schema_adoption(probe, prior, Path("sdk"))
    assert [(c["raw_triples"], c["unique_triples"]) for c in record["cases"]] == [
        (2, 1),
        (2, 1),
    ]
    assert record["physical_known_tokens"] == 36
    assert record["new_http_calls"] == 0
    assert len(cache) == 2
    assert (directory / "manifest.json").read_bytes() == old
    assert record["probe_status"] == "failed"


@pytest.mark.parametrize(
    "change",
    [
        "sha",
        "length",
        "partial",
        "unknown",
        "duplicate_field",
        "shape",
        "parser",
        "empty",
    ],
)
def test_adoption_rejects_corruption_and_incomplete_output(
    adoption_case, change, monkeypatch
):
    prior, probe, directory, prepared = adoption_case
    path = (
        directory / f"requests/{prepared['cases'][0]['request_sha256']}.response.json"
    )
    body = dense.read_json(path)
    if change == "length":
        body["choices"][0]["finish_reason"] = "length"
    elif change == "unknown":
        body["usage"].pop("completion_tokens")
    elif change == "parser":
        monkeypatch.setattr(
            "scripts.hipporag_repair_executor.make_pinned_openie_parser",
            lambda: lambda *a, **k: [],
        )
    elif change in ("partial", "duplicate_field", "shape", "empty"):
        body["choices"][0]["message"]["content"] = {
            "partial": '{"triples":[',
            "duplicate_field": '{"triples":[],"triples":[]}',
            "shape": '{"triples":[["A","B"]]}',
            "empty": '{"triples":[]}',
        }[change]
    else:
        body["id"] = "changed"
    dense.write_json_atomic(path, body)
    if change != "sha":
        manifest = dense.read_json(directory / "manifest.json")
        manifest["artifacts"][path.relative_to(directory).as_posix()] = (
            dense.sha256_file(path)
        )
        dense.write_json_atomic(directory / "manifest.json", manifest)
    with pytest.raises(ValueError):
        e1.schema_adoption(probe, prior, Path("sdk"))


def test_adopted_replay_names_actual_schema_request_and_cost_once(
    adoption_case, tmp_path
):
    prior, probe, _, prepared = adoption_case
    record, cache = e1.schema_adoption(probe, prior, Path("sdk"))
    original = {
        **prepared["cases"][0]["payload"],
        "response_format": {"type": "json_object"},
    }
    original_key = e1.target.digest(
        {"payload": original, "kind": "llm", "operation": "openie_triples"}
    )
    row = {
        "method": "hipporag2",
        "dataset": "musique",
        "run_id": "child",
        "resume_kind": "native_schema",
        "token_limit": 1000,
    }
    plan = {
        "model": "qwen",
        "embedding_model": "bge",
        "hippo_schema_policy": e1.HIPPO_SCHEMA_POLICY,
        "raptor_summary_network_resume": True,
        "independent_raptor": True,
    }
    child = tmp_path / "child"
    child.mkdir()
    journal = Journal(
        child / "usage.jsonl", run_id="child", method="hipporag2", dataset="musique"
    )
    with patch.object(e1, "verify_schema_recovery", return_value=(record, cache)):
        transport = e1.Transport(plan, row, {}, child, journal)
    transport.schema_aliases = {original_key: prepared["cases"][0]["request_sha256"]}
    for _ in range(2):
        text, metadata = transport.generate(
            original["messages"], 3072, "openie_triples", {"type": "json_object"}
        )
        assert metadata["cache_hit"] is True
        assert (
            len(json.loads(text)["triples"]) == 2
        )  # Raw preserved; SDK normalizes later.
    summary = journal.summary()
    assert summary["attempts"] == 0
    assert sum(summary["known_subtotal"].values()) == 0
    assert sum(p["cache_hits"] for p in summary["phases"]) == 2
    from scripts.token_accounting import read_records, summarize

    hits = [r for r in read_records(journal.path) if r["event"] == "finished"]
    assert all(
        r["object_id"] == prepared["cases"][0]["request_sha256"]
        and r["producer_run_id"] == "producer"
        for r in hits
    )
    combined = summarize(
        [
            *read_records(
                next(iter(cache.values()))["path"].parent.parent / "usage.jsonl"
            ),
            *read_records(journal.path),
        ]
    )
    assert sum(combined["known_subtotal"].values()) == 36
    transport.close()


@pytest.mark.parametrize("change", ["length", "unknown", "partial"])
def test_new_schema_failure_keeps_usage_and_forbids_next_post(
    tmp_path, monkeypatch, change
):
    row = {
        "method": "hipporag2",
        "dataset": "hotpotqa",
        "run_id": "child",
        "resume_kind": "native_schema",
        "token_limit": 20000,
        "max_new_posts": 2,
    }
    plan = {
        "model": "qwen",
        "embedding_model": "bge",
        "hippo_schema_policy": e1.HIPPO_SCHEMA_POLICY,
        "endpoint": "https://example.invalid/v1",
    }
    journal = Journal(
        tmp_path / "usage.jsonl", run_id="child", method="hipporag2", dataset="hotpotqa"
    )
    with patch.object(e1, "verify_schema_recovery", return_value=({"cases": []}, {})):
        transport = e1.Transport(
            plan, row, {"LITELLM_API_KEY": "fake"}, tmp_path, journal
        )
    body = {
        "choices": [
            {
                "finish_reason": "length" if change == "length" else "stop",
                "message": {
                    "content": '{"triples":['
                    if change == "partial"
                    else '{"triples":[["A","in","B"]]}'
                },
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            **({} if change == "unknown" else {"completion_tokens": 8}),
        },
    }
    from unittest.mock import Mock

    response = Mock(status_code=200)
    response.json.return_value = body
    transport.session.post = Mock(return_value=response)
    args = (
        [{"role": "user", "content": "text"}],
        3072,
        "openie_triples",
        {"type": "json_object"},
    )
    with pytest.raises(ValueError):
        transport.generate(*args)
    assert journal.summary()["known_subtotal"]["llm_input_tokens"] == 10
    with pytest.raises(ValueError, match="schema_failure_cannot_continue"):
        transport.generate(
            [{"role": "user", "content": "another passage"}],
            3072,
            "openie_triples",
            {"type": "json_object"},
        )
    assert transport.session.post.call_count == 1
    transport.close()


def test_native_schema_plan_claim_shared_across_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr(e1, "code_dirty", lambda: False)
    monkeypatch.setattr(e1, "git", lambda *a: "code")
    monkeypatch.setattr(e1, "schema_adoption", lambda *a: ({"accepted": True}, {}))
    monkeypatch.setattr(e1, "schema_resume_history", lambda *a: ([], []))
    (tmp_path / "old-mu").mkdir()
    prior = tmp_path / "prior.json"
    dense.write_json_atomic(
        prior,
        {
            "workspace": str(tmp_path),
            "batch_id": "batch",
            "rows": [
                {
                    "method": "hipporag2",
                    "dataset": d,
                    "output": "old-mu" if d == "musique" else "old-hot",
                }
                for d in e1.DATASETS
            ],
        },
    )
    probe, adoption = tmp_path / "probe.json", tmp_path / "adoption.json"
    dense.write_json_atomic(probe, {})
    dense.write_json_atomic(adoption, {"accepted": True})
    plan = e1.prepare_native_schema_continuation(prior, probe, adoption, tmp_path)
    assert [r["token_limit"] for r in plan["rows"]] == [20000000, 20000000]
    assert (tmp_path / "old-mu/schema-resume-once.claim.json").exists()
    assert not (tmp_path / plan["rows"][0]["output"]).exists()
    with pytest.raises(FileExistsError):
        e1.prepare_native_schema_continuation(prior, probe, adoption, tmp_path)


@pytest.mark.parametrize("change", ["adoption_sha", "probe_sha", "policy"])
def test_recovery_input_changes_fail_before_http(adoption_case, tmp_path, change):
    prior, probe, _, _ = adoption_case
    record, _ = e1.schema_adoption(probe, prior, Path("sdk"))
    adoption = tmp_path / "adoption.json"
    dense.write_json_atomic(adoption, record)
    plan = {
        "hippo_schema_policy": e1.HIPPO_SCHEMA_POLICY,
        "hippo_schema_inputs": {
            "prior": {"path": str(prior), "sha256": dense.sha256_file(prior)},
            "probe": {"path": str(probe), "sha256": dense.sha256_file(probe)},
            "source": {"path": "sdk"},
        },
    }
    row = {
        "schema_adoption": {
            "path": "adoption.json",
            "sha256": dense.sha256_file(adoption),
        }
    }
    if change == "adoption_sha":
        dense.write_json_atomic(adoption, {**record, "physical_known_tokens": 0})
    elif change == "probe_sha":
        dense.write_json_atomic(probe, {})
    else:
        plan["hippo_schema_policy"] = {**e1.HIPPO_SCHEMA_POLICY, "retry": 1}
    with pytest.raises(ValueError):
        e1.verify_schema_recovery(plan, row)


@pytest.mark.parametrize("change", ["budget", "sources", "claim", "post_limit"])
def test_schema_plan_tampering_rejected_before_http(tmp_path, monkeypatch, change):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr(e1, "schema_resume_history", lambda *a: ([], []))
    monkeypatch.setattr(
        "requests.sessions.Session.request",
        lambda *a, **k: pytest.fail("HTTP forbidden"),
    )
    prior = tmp_path / "prior.json"
    dense.write_json_atomic(
        prior,
        {"rows": [{"method": "hipporag2", "dataset": "musique", "output": "old"}]},
    )
    probe = tmp_path / "probe.json"
    dense.write_json_atomic(probe, {})
    row = {
        "method": "hipporag2",
        "dataset": "musique",
        "run_id": "child",
        "max_new_posts": 40000,
        "history_runs": [],
        "resume_sources": [],
        "prior_budget_charge": 0,
        "token_limit": 20000000,
        "diagnostics_in_history": True,
        "schema_adoption": {"sha256": "adoption"},
    }
    plan = {
        "hippo_schema_policy": e1.HIPPO_SCHEMA_POLICY,
        "hippo_schema_inputs": {
            "prior": {"path": str(prior), "sha256": dense.sha256_file(prior)},
            "probe": {"path": str(probe)},
        },
        "rows": [row],
    }
    (tmp_path / "old").mkdir()
    claim_path = tmp_path / "old/schema-resume-once.claim.json"
    dense.write_json_atomic(claim_path, e1.schema_claim(plan))
    e1.verify_native_schema_plan(plan, row)
    if change == "budget":
        row["prior_budget_charge"] = -1
    elif change == "sources":
        row["resume_sources"] = [{"output": "elsewhere"}]
    elif change == "claim":
        row["run_id"] = "different_child"
    else:
        row["max_new_posts"] = 40001
    with pytest.raises(ValueError):
        e1.verify_native_schema_plan(plan, row)


def test_legacy_json_object_cache_keeps_its_original_contract(adoption_case, tmp_path):
    prior, probe, _, prepared = adoption_case
    record, cache = e1.schema_adoption(probe, prior, Path("sdk"))
    original = {
        **prepared["cases"][0]["payload"],
        "response_format": {"type": "json_object"},
    }
    key = e1.target.digest(
        {"payload": original, "kind": "llm", "operation": "openie_triples"}
    )
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": '{"named_entities":["A","B"],"triples":[["A","in","B"]]}'
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    old = tmp_path / "old.response.json"
    dense.write_json_atomic(old, body)
    row = {"method": "hipporag2", "dataset": "musique", "resume_kind": "native_schema"}
    child = tmp_path / "legacy-child"
    child.mkdir()
    journal = Journal(
        child / "usage.jsonl", run_id="child", method="hipporag2", dataset="musique"
    )
    with patch.object(e1, "verify_schema_recovery", return_value=(record, cache)):
        transport = e1.Transport({"model": "qwen"}, row, {}, child, journal)
    transport.parent_cache[key] = {
        **next(iter(cache.values())),
        "path": old,
        "sha256": dense.sha256_file(old),
        "run_id": "old-producer",
    }
    text, metadata = transport.generate(
        original["messages"], 3072, "openie_triples", {"type": "json_object"}
    )
    assert json.loads(text) == json.loads(body["choices"][0]["message"]["content"])
    assert metadata["cache_hit"] is True
    assert journal.summary()["attempts"] == 0
    from scripts.token_accounting import read_records

    assert read_records(journal.path)[-1]["object_id"] == key
    transport.close()


@pytest.mark.parametrize("physical", [False, True])
def test_preflight_child_only_for_zero_physical_attempts(
    tmp_path, monkeypatch, physical
):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    directory = tmp_path / "failed"
    directory.mkdir()
    journal = Journal(
        directory / "usage.jsonl",
        run_id="failed",
        method="hipporag2",
        dataset="musique",
    )
    if physical:
        a = journal.start(
            phase="index",
            operation="openie_triples",
            provider="target_api",
            model="qwen",
            kind="llm",
        )
        journal.finish(
            a, status="success", usage={"llm_input_tokens": 1, "llm_output_tokens": 1}
        )
    else:
        journal.cache_hit(
            phase="index",
            operation="openie_triples",
            provider="target_api",
            model="qwen",
            kind="llm",
            object_id="cached",
            producer_run_id="old",
            producer_usage_complete=False,
        )
    dense.write_json_atomic(
        directory / "manifest.json",
        {
            "run_id": "failed",
            "status": "failed",
            "token_accounting": journal.reference(),
            "artifacts": {"usage.jsonl": dense.sha256_file(journal.path)},
        },
    )
    pin = {
        "output": "failed",
        "manifest_sha256": dense.sha256_file(directory / "manifest.json"),
    }
    if physical:
        with pytest.raises(ValueError, match="zero_physical"):
            e1.schema_preflight_history(pin)
    else:
        history = e1.schema_preflight_history(pin)
        assert history["unknown_reserved_upper_bound"] == 0
        assert history["summary"]["attempts"] == 0
        assert (directory / "manifest.json").exists()


def test_zero_attempt_child_preserves_ancestor_budget_and_claims_once(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr(e1, "code_dirty", lambda: False)
    monkeypatch.setattr(e1, "git", lambda *a: "fixed-code")
    monkeypatch.setattr(e1, "verify_native_schema_plan", lambda *a: None)
    monkeypatch.setattr(e1, "verify_schema_recovery", lambda *a: None)
    directory = tmp_path / "mu-schema1"
    directory.mkdir()
    journal = Journal(
        directory / "usage.jsonl",
        run_id="old-child",
        method="hipporag2",
        dataset="musique",
    )
    journal.cache_hit(
        phase="index",
        operation="openie_triples",
        provider="target_api",
        model="qwen",
        kind="llm",
        object_id="cached",
        producer_run_id="producer",
        producer_usage_complete=True,
    )
    dense.write_json_atomic(
        directory / "manifest.json",
        {
            "status": "failed",
            "run_id": "old-child",
            "token_accounting": journal.reference(),
            "artifacts": {"usage.jsonl": dense.sha256_file(journal.path)},
        },
    )
    prior = tmp_path / "approved-plan.json"
    original = {
        "workspace": str(tmp_path),
        "batch_id": "batch",
        "hippo_schema_policy": e1.HIPPO_SCHEMA_POLICY,
        "hippo_schema_inputs": {"prior": {"sha256": "root"}},
        "rows": [
            {
                "method": "hipporag2",
                "dataset": d,
                "output": "mu-schema1" if d == "musique" else "hot-schema1",
                "run_id": d,
                "history_runs": [],
                "token_limit": 12345,
                "prior_budget_charge": 678,
                "schema_adoption": {"sha256": "adoption"},
            }
            for d in e1.DATASETS
        ],
    }
    dense.write_json_atomic(prior, original)
    old_bytes = prior.read_bytes()
    old_manifest = (directory / "manifest.json").read_bytes()
    plan = e1.prepare_schema_preflight_continuation(prior)
    assert prior.read_bytes() == old_bytes
    assert (directory / "manifest.json").read_bytes() == old_manifest
    assert plan["parent_plan"]["sha256"] == dense.sha256_file(prior)
    for row in plan["rows"]:
        assert row["token_limit"] == 12345 and row["prior_budget_charge"] == 678
        assert row["code_commit"] == "fixed-code"
        assert row["output"].endswith("-schema-preflight1")
        assert not (tmp_path / row["output"]).exists()
    assert len(plan["rows"][0]["history_runs"]) == 1
    assert (directory / "preflight-resume-once.claim.json").exists()
    with pytest.raises(FileExistsError):
        e1.prepare_schema_preflight_continuation(prior)
    next_path = tmp_path / "child-plan.json"
    dense.write_json_atomic(next_path, plan)
    with pytest.raises(ValueError, match="clean_first_schema_plan"):
        e1.prepare_schema_preflight_continuation(next_path)


def test_gpt_diagnostic_payload_preserves_source_and_omits_qwen_options():
    original, _ = e1.schema_probe_payload(
        {
            **e1.target.OPTIONS,
            "model": "qwen",
            "max_tokens": 3072,
            "messages": [{"role": "user", "content": "source"}],
            "response_format": {"type": "json_object"},
        },
        compatible=True,
    )
    before = copy.deepcopy(original)
    payload, reserve = e1.gpt_extractor_payload(original)
    assert original == before
    assert payload["messages"] == original["messages"]
    assert payload["response_format"] == original["response_format"]
    assert payload["model"] == "iairlab/gpt-oss-120b"
    assert payload["reasoning_effort"] == "low"
    assert "chat_template_kwargs" not in payload
    assert payload["max_tokens"] == 3072
    assert (
        reserve == len(json.dumps(payload, ensure_ascii=False).encode()) + 2048 + 3072
    )


@pytest.mark.parametrize(
    "outcome,posts",
    [
        ("success", 5),
        ("unknown", 1),
        ("length", 1),
        ("cycle", 1),
        ("bad_sha", 0),
        ("bad_head", 0),
    ],
)
def test_gpt_diagnostic_one_claim_no_retry_and_cost_export(
    tmp_path, monkeypatch, outcome, posts
):
    from unittest.mock import Mock

    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr(e1, "code_dirty", lambda: False)
    monkeypatch.setattr(e1, "git", lambda *a: "head")
    old = tmp_path / "stopped"
    old.mkdir()
    journal = Journal(
        old / "usage.jsonl", run_id="old", method="hipporag2", dataset="musique"
    )
    a = journal.start(
        phase="index",
        operation="openie_triples",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    journal.finish(
        a, status="success", usage={"llm_input_tokens": 7, "llm_output_tokens": 0}
    )
    dense.write_json_atomic(
        old / "manifest.json",
        {
            "run_id": "old",
            "status": "failed",
            "seconds": 1,
            "token_accounting": journal.reference(),
            "artifacts": {"usage.jsonl": dense.sha256_file(journal.path)},
        },
    )
    original = (old / "manifest.json").read_bytes()
    plan = {
        "workspace": str(tmp_path),
        "model": "qwen",
        "endpoint": "https://example.invalid/v1",
        "batch_id": "batch",
        "embedding_model": "bge",
        "embedding_digest": "digest",
        "parameters": {},
        "combined_token_limit": 68000000,
        "rows": [
            {
                "method": "hipporag2",
                "dataset": "musique",
                "output": "stopped",
                "run_id": "old",
                "diagnostics_in_history": True,
            }
        ],
    }
    prior = tmp_path / "prior.json"
    dense.write_json_atomic(prior, plan)
    prepared = {
        **e1.EXTRACTOR_DIAGNOSTIC,
        "code_commit": "head",
        "cases": [],
        "failed_manifest_sha256": dense.sha256_file(old / "manifest.json"),
    }
    for i in range(5):
        payload, reserve = e1.gpt_extractor_payload(
            {
                **e1.target.OPTIONS,
                "model": "qwen",
                "max_tokens": 3072,
                "messages": [{"role": "user", "content": str(i)}],
                "response_format": {"type": "json_schema"},
            }
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
    if outcome == "bad_head":
        prepared["code_commit"] = "other"
    probe = tmp_path / "probe.json"
    dense.write_json_atomic(probe, prepared)
    monkeypatch.setattr(e1, "prepare_extractor_diagnostic", lambda *a: prepared)
    body = {
        "choices": [
            {
                "finish_reason": "length" if outcome == "length" else "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "triples": [["A", "in", "B"]]
                            * (12 if outcome == "cycle" else 1)
                        }
                    )
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    if outcome == "unknown":
        body["usage"].pop("completion_tokens")
    response = Mock(status_code=200)
    response.json.return_value = body
    session = requests.Session()

    def post(*a, **kw):
        assert (old / "gpt-oss-probe-once.claim.json").exists()
        return response

    session.post = Mock(side_effect=post)
    monkeypatch.setattr(e1.requests, "Session", lambda: session)
    config = {
        "TARGET_API_MODEL": "qwen",
        "TARGET_API_BASE_URL": plan["endpoint"],
        "LITELLM_API_KEY": "fake",
    }
    approval = "wrong" if outcome == "bad_sha" else dense.sha256_file(probe)
    if outcome == "success":
        e1.execute_schema_probe(
            probe, prior, tmp_path, config, approval, compatible=True
        )
    else:
        with pytest.raises(ValueError):
            e1.execute_schema_probe(
                probe, prior, tmp_path, config, approval, compatible=True
            )
    assert session.post.call_count == posts
    assert (old / "manifest.json").read_bytes() == original
    if not posts:
        return
    manifest = dense.read_json(tmp_path / "musique-gpt-oss-probe1/manifest.json")
    assert manifest["status"] == (
        "awaiting_source_review" if outcome == "success" else "failed"
    )
    assert manifest["full_index_authorized"] is False
    assert manifest["model"] == e1.EXTRACTOR_DIAGNOSTIC["model"]
    for call in session.post.call_args_list:
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["timeout"] == (30, 300)
    with pytest.raises(ValueError, match="output_already_exists"):
        e1.execute_schema_probe(
            probe, prior, tmp_path, config, approval, compatible=True
        )
    assert session.post.call_count == posts
    (tmp_path / "results/summary").mkdir(parents=True)
    first = e1.export(plan, prior)
    second = e1.export(plan, prior)
    assert (
        first["physical_known_tokens"]
        == second["physical_known_tokens"]
        == 7 + posts * (10 if outcome == "unknown" else 18)
    )
    assert first["cost_complete"] is (outcome != "unknown")
    if outcome == "unknown":
        assert first["budget_charge_upper_bound"] > first["physical_known_tokens"]


@pytest.fixture
def rejected_extractor_probe(tmp_path):
    import hashlib

    directory = tmp_path / "musique-gpt-oss-probe1"
    (directory / "requests").mkdir(parents=True)
    stopped = tmp_path / "stopped"
    stopped.mkdir()
    old = Journal(
        stopped / "usage.jsonl", run_id="old", method="hipporag2", dataset="musique"
    )
    attempt = old.start(
        phase="index",
        operation="openie_triples",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    old.finish(
        attempt, status="success", usage={"llm_input_tokens": 7, "llm_output_tokens": 0}
    )
    dense.write_json_atomic(
        stopped / "manifest.json",
        {
            "run_id": "old",
            "status": "failed",
            "seconds": 1,
            "token_accounting": old.reference(),
            "artifacts": {"usage.jsonl": dense.sha256_file(old.path)},
        },
    )
    prior = tmp_path / "index-plan.json"
    dense.write_json_atomic(
        prior,
        {
            "workspace": str(tmp_path),
            "model": "qwen",
            "endpoint": "https://example.invalid/v1",
            "batch_id": "batch",
            "embedding_model": "bge",
            "embedding_digest": "digest",
            "parameters": {},
            "combined_token_limit": 68000000,
            "rows": [
                {
                    "method": "hipporag2",
                    "dataset": "musique",
                    "output": "stopped",
                    "run_id": "old",
                    "token_limit": 100007,
                    "diagnostics_in_history": True,
                }
            ],
        },
    )
    journal = Journal(
        directory / "usage.jsonl",
        run_id="gpt-producer",
        method="hipporag2",
        dataset="musique",
    )
    plan = {
        **e1.EXTRACTOR_DIAGNOSTIC,
        "parent_plan_sha256": dense.sha256_file(prior),
        "failed_manifest_sha256": dense.sha256_file(stopped / "manifest.json"),
        "cases": [],
        "remaining_hippo_budget_before_probe": 100000,
        "semantic_acceptance": "Review full source, qualifiers, dates; no gold",
    }
    reviews = []
    for i in range(5):
        source = f"Synthetic source {i}: A supposedly visited B."
        payload, reserve = e1.gpt_extractor_payload(
            {
                **e1.target.OPTIONS,
                "model": "qwen",
                "max_tokens": 3072,
                "messages": [
                    {"role": "system", "content": "Extract source triples."},
                    {"role": "user", "content": source},
                ],
                "response_format": {"type": "json_schema"},
            }
        )
        key = e1.target.digest(
            {"payload": payload, "kind": "llm", "operation": "openie_triples"}
        )
        body = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"triples":[["A","visited","B"]]}'},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }
        response = directory / "requests" / f"{key}.response.json"
        dense.write_json_atomic(response, body)
        a = journal.start(
            phase="index",
            operation="openie_triples",
            provider="target_api",
            model=payload["model"],
            kind="llm",
            object_id=key,
        )
        journal.finish(
            a, status="success", usage={"llm_input_tokens": 10, "llm_output_tokens": 8}
        )
        sha = hashlib.sha256(source.encode()).hexdigest()
        plan["cases"].append(
            {
                "source_id": str(i),
                "source_text": source,
                "source_text_sha256": sha,
                "payload": payload,
                "request_sha256": key,
                "reserved_tokens_upper_bound": reserve,
            }
        )
        reviews.append(
            {
                "source_id": str(i),
                "source_text_sha256": sha,
                "request_sha256": key,
                "response_sha256": dense.sha256_file(response),
                "status": "not_accepted",
                "source_evidence": "supposedly",
                "response_evidence": ["A", "visited", "B"],
            }
        )
    pp = tmp_path / "plan.json"
    dense.write_json_atomic(pp, plan)
    mp = directory / "manifest.json"
    dense.write_json_atomic(
        mp,
        {
            "parent_manifest_sha256": dense.sha256_file(stopped / "manifest.json"),
            "full_index_authorized": False,
            "seconds": 1,
            "approved_plan_sha256": dense.sha256_file(pp),
            "model": plan["model"],
            "status": "awaiting_source_review",
            "run_id": "gpt-producer",
            "unknown_reserved_upper_bound": 0,
            "token_accounting": journal.reference(),
            "cases": [{"request_sha256": c["request_sha256"]} for c in plan["cases"]],
            "artifacts": {
                p.relative_to(directory).as_posix(): dense.sha256_file(p)
                for p in directory.rglob("*")
                if p.is_file()
            },
        },
    )
    dense.write_json_atomic(
        directory / "source-review.json",
        {
            "producer_manifest_sha256": dense.sha256_file(mp),
            "approved_plan_sha256": dense.sha256_file(pp),
            "producer_run_id": "gpt-producer",
            "semantic_status": "not_accepted_for_continuation",
            "full_index_authorized": False,
            "cases": reviews,
        },
    )
    return pp, directory


def test_source_fidelity_candidate_changes_only_system_and_cannot_execute(
    rejected_extractor_probe, monkeypatch
):
    pp, directory = rejected_extractor_probe
    monkeypatch.setattr(e1, "git", lambda *a: "head")
    monkeypatch.setattr(e1, "code_dirty", lambda: False)
    originals = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    original_plan = dense.read_json(pp)
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        candidate = e1.prepare_extractor_policy(pp, directory)
        assert candidate["remaining_hippo_budget_snapshot"] == 100000 - 90
        assert candidate["new_http_calls"] == 0
        assert candidate["execution_authorized"] is False
        assert candidate["full_index_authorized"] is False
        assert candidate["reserved_tokens_upper_bound"] == sum(
            c["reserved_tokens_upper_bound"] for c in candidate["cases"]
        )
        for old, new in zip(original_plan["cases"], candidate["cases"], strict=True):
            assert new["request_sha256"] != old["request_sha256"]
            assert new["payload"]["messages"][1:] == old["payload"]["messages"][1:]
            assert {k: v for k, v in new["payload"].items() if k != "messages"} == {
                k: v for k, v in old["payload"].items() if k != "messages"
            }
            assert (
                new["payload"]["messages"][0]["content"]
                == old["payload"]["messages"][0]["content"]
                + "\n\n"
                + e1.SOURCE_FAITHFULNESS_POLICY
            )
        out = pp.with_name("candidate.json")
        dense.write_json_atomic(out, candidate)
        with pytest.raises(ValueError, match="offline_policy_candidate_not_executable"):
            e1.execute_schema_probe(
                out, pp, directory, {}, dense.sha256_file(out), compatible=True
            )
    assert all(p.read_bytes() == content for p, content in originals.items())


@pytest.mark.parametrize(
    "change",
    [
        "response",
        "source",
        "quote",
        "triple",
        "missing_case",
        "duplicate_case",
        "accepted",
        "manifest",
    ],
)
def test_source_review_rejects_stale_or_incomplete_evidence(
    rejected_extractor_probe, change
):
    pp, directory = rejected_extractor_probe
    rp = directory / "source-review.json"
    review = dense.read_json(rp)
    if change == "response":
        response = next((directory / "requests").glob("*.json"))
        response.write_text("{}", encoding="utf-8")
    elif change == "source":
        review["cases"][0]["source_text_sha256"] = "changed"
    elif change == "quote":
        review["cases"][0]["source_evidence"] = "not actually in the source"
    elif change == "triple":
        review["cases"][0]["response_evidence"] = ["Invented", "in", "B"]
    elif change == "missing_case":
        review["cases"].pop()
    elif change == "duplicate_case":
        review["cases"][-1] = review["cases"][0]
    elif change == "accepted":
        review["semantic_status"] = "accepted"
    elif change == "manifest":
        review["producer_manifest_sha256"] = "other"
    dense.write_json_atomic(rp, review)
    with (
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
        pytest.raises(ValueError),
    ):
        e1.prepare_extractor_policy(pp, directory)


@pytest.mark.parametrize(
    "outcome,posts",
    [
        ("success", 5),
        ("length", 1),
        ("unknown", 1),
        ("connection", 1),
        ("payload_changed", 0),
        ("review_changed", 0),
        ("claimed", 0),
        ("other_directory", 0),
    ],
)
def test_policy_followup_canonical_claim_and_cumulative_cost(
    rejected_extractor_probe, tmp_path, monkeypatch, outcome, posts
):
    from unittest.mock import Mock

    pp, parent = rejected_extractor_probe
    prior = tmp_path / "index-plan.json"
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr(e1, "code_dirty", lambda: False)
    monkeypatch.setattr(e1, "git", lambda *a: "head")
    prepared = e1.prepare_extractor_policy_probe(pp, parent, prior)
    assert prepared["remaining_hippo_budget_snapshot"] == 99910
    proposal = tmp_path / "policy.json"
    if outcome == "payload_changed":
        prepared["cases"][0]["payload"]["seed"] = 43
    if outcome == "other_directory":
        prepared["parent_probe_output"] = "another-output"
    dense.write_json_atomic(proposal, prepared)
    if outcome == "review_changed":
        review = dense.read_json(parent / "source-review.json")
        review["cases"][0]["reason"] = "another review"
        dense.write_json_atomic(parent / "source-review.json", review)
    if outcome == "claimed":
        (parent / "source-policy-probe-once.claim.json").write_text(
            "claimed", encoding="utf-8"
        )
    body = {
        "choices": [
            {
                "finish_reason": "length" if outcome == "length" else "stop",
                "message": {"content": '{"triples":[["A","supposedly visited","B"]]}'},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }
    if outcome == "unknown":
        body["usage"].pop("completion_tokens")
    response = Mock(status_code=200)
    response.json.return_value = body
    session = requests.Session()

    def send(*a, **kw):
        assert (parent / "source-policy-probe-once.claim.json").exists()
        if outcome == "connection":
            raise requests.ConnectionError("synthetic")
        return response

    session.post = Mock(side_effect=send)
    monkeypatch.setattr(e1.requests, "Session", lambda: session)
    config = {
        "TARGET_API_MODEL": "qwen",
        "TARGET_API_BASE_URL": "https://example.invalid/v1",
        "LITELLM_API_KEY": "fake",
    }
    before = (parent / "manifest.json").read_bytes()
    if outcome == "success":
        output = e1.execute_schema_probe(
            proposal,
            prior,
            tmp_path,
            config,
            dense.sha256_file(proposal),
            compatible=True,
        )
    else:
        with pytest.raises((ValueError, requests.ConnectionError, FileNotFoundError)):
            e1.execute_schema_probe(
                proposal,
                prior,
                tmp_path,
                config,
                dense.sha256_file(proposal),
                compatible=True,
            )
        output = tmp_path / "musique-gpt-oss-policy-probe1"
    assert session.post.call_count == posts
    assert (parent / "manifest.json").read_bytes() == before
    if not posts:
        return
    manifest = dense.read_json(output / "manifest.json")
    assert manifest["model"] == "iairlab/gpt-oss-120b"
    assert manifest["schema_variant"] == "gpt_oss_source_faithfulness_v1"
    assert manifest["status"] == (
        "awaiting_source_review" if outcome == "success" else "failed"
    )
    with pytest.raises(ValueError, match="already_claimed"):
        e1.execute_schema_probe(
            proposal,
            prior,
            tmp_path,
            config,
            dense.sha256_file(proposal),
            compatible=True,
        )
    assert session.post.call_count == posts
    (tmp_path / "results/summary").mkdir(parents=True)
    a = e1.export(dense.read_json(prior), prior)
    b = e1.export(dense.read_json(prior), prior)
    expected = 97 + (
        90
        if outcome == "success"
        else 10
        if outcome == "unknown"
        else 0
        if outcome == "connection"
        else 18
    )
    assert a["physical_known_tokens"] == b["physical_known_tokens"] == expected
    assert a["cost_complete"] is (outcome not in ("unknown", "connection"))
    if outcome in ("unknown", "connection"):
        assert (
            a["budget_charge_upper_bound"]
            == expected + prepared["cases"][0]["reserved_tokens_upper_bound"]
        )
    # Even losing/moving the new output cannot permit another follow-up of this producer.
    output.rename(tmp_path / "archived-new-output")
    with pytest.raises(ValueError, match="already_claimed"):
        e1.prepare_extractor_policy_probe(pp, parent, prior)
