"""Offline regression of shared E2 on synthetic transport and existing artifacts."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from scripts import e2_evaluation as e2
from scripts import e1_indexers as indexes
from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts import run_e1 as e1
from scripts.token_accounting import Journal


def plan():
    return {
        "max_combined_tokens": e2.LIMIT,
        "max_posts": 140,
        "max_llm_posts": 80,
        "max_embedding_posts": 60,
        "embedding_model": "bge-m3:latest",
        "embedding_digest": "bge",
    }


def body(text="Answer: Paris", finish="stop", usage=True):
    result = {"choices": [{"finish_reason": finish, "message": {"content": text}}]}
    if usage:
        result["usage"] = {"prompt_tokens": 10, "completion_tokens": 4}
    return result


class Session:
    def __init__(self, response=None, error=None):
        self.body = response
        self.error = error
        self.posts = 0

    def post(self, *args, **kwargs):
        self.posts += 1
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] == (30, 300)
        if self.error:
            raise self.error

        class Response:
            status_code = 200

            def json(inner):
                return self.body

            def raise_for_status(inner):
                pass

        return Response()


def call(calls, session=None, payload=None):
    return calls.call(
        payload or e2.reader_payload("Where?", {"passages": []}),
        method="dense",
        dataset="musique",
        qid="q",
        operation="reader",
        session=session,
        url="https://example.invalid",
    )


def test_common_reader_projects_no_gold_and_preserves_order():
    passages = [
        {
            "title": "Z",
            "text": "first",
            "answer": "SECRET_GOLD",
            "supporting_ids": ["hidden"],
        },
        {"title": "A", "text": "second"},
    ]
    payload = e2.reader_payload(
        "Where?", {"passages": passages, "answer": "SECRET_GOLD"}
    )
    rendered = json.dumps(payload)
    assert "SECRET_GOLD" not in rendered and "hidden" not in rendered
    assert rendered.index("first") < rendered.index("second")
    assert payload["model"] == e2.MODEL and payload["max_tokens"] == 512
    with pytest.raises(ValueError, match="overflow"):
        e2.reader_payload(
            "?", {"passages": [{"title": "T", "text": "x" * e2.MESSAGE_BYTES}]}
        )


def test_success_replay_no_http_or_double_usage(tmp_path):
    calls = e2.Calls(tmp_path, plan(), run_id="r")
    session = Session(body())
    result, hit = call(calls, session)
    before = calls.journal.reference()
    assert hit is False
    resumed = e2.Calls(tmp_path, plan(), run_id="r", resume=True)
    assert call(resumed) == (result, True)
    assert calls.journal.reference() == before and session.posts == 1
    assert before["summary"]["known_subtotal"]["llm_input_tokens"] == 10


@pytest.mark.parametrize("response", [body(finish="length"), body(usage=False)])
def test_length_unknown_never_reused(tmp_path, response):
    calls = e2.Calls(tmp_path, plan(), run_id="r")
    session = Session(response)
    with pytest.raises(ValueError):
        call(calls, session)
    with pytest.raises(ValueError, match="uncertain"):
        call(calls, session)
    assert session.posts == 1


def test_transport_error_duration_and_unknown_preserved(tmp_path):
    calls = e2.Calls(tmp_path, plan(), run_id="r")
    session = Session(error=target.requests.exceptions.ReadTimeout("test"))
    with pytest.raises(target.requests.exceptions.ReadTimeout):
        call(calls, session)
    from scripts.token_accounting import read_records

    rows = read_records(calls.journal.path)
    assert rows[-1]["wall_seconds"] >= 0 and rows[-1]["usage_status"] == "unknown"
    with pytest.raises(ValueError, match="uncertain"):
        call(calls, session)
    assert session.posts == 1


def test_tampered_completed_cache_refused(tmp_path):
    calls = e2.Calls(tmp_path, plan(), run_id="r")
    session = Session(body())
    call(calls, session)
    path = next(
        p for p in tmp_path.glob("*.json") if not p.name.endswith("response.json")
    )
    value = dense.read_json(path)
    value["response"]["choices"][0]["message"]["content"] = "tampered"
    dense.write_json_atomic(path, value)
    with pytest.raises(ValueError, match="changed"):
        call(calls, session)
    assert session.posts == 1


def test_cache_miss_without_transport_makes_no_claim(tmp_path):
    calls = e2.Calls(tmp_path, plan(), run_id="r")
    with pytest.raises(ValueError, match="HTTP_forbidden"):
        call(calls)
    assert not list(tmp_path.glob("*.json"))


def test_budget_exhausted_before_http(tmp_path):
    p = plan()
    p["max_combined_tokens"] = 1
    calls = e2.Calls(tmp_path, p, run_id="r")
    session = Session(body())
    with pytest.raises(ValueError, match="budget"):
        call(calls, session)
    assert session.posts == 0


def test_incompatible_index_rejected_before_loader_or_http(tmp_path):
    dense.write_json_atomic(tmp_path / "manifest.json", {"status": "failed"})
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError, match="not_completed"):
            indexes.load_ready_e1({}, {"output": "."}, [], tmp_path)


def test_e1_verify_is_read_only_and_export_separate(tmp_path, monkeypatch, capsys):
    journal = Journal(
        tmp_path / "usage.jsonl", run_id="r", method="dense", dataset="musique"
    )
    dense.write_json_atomic(
        tmp_path / "manifest.json",
        {
            "status": "completed",
            "token_accounting": journal.reference(),
            "artifacts": {"usage.jsonl": dense.sha256_file(journal.path)},
        },
    )
    pp = tmp_path / "plan.json"
    dense.write_json_atomic(pp, {"rows": [{"output": "."}]})
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["run_e1", "verify", "--plan", str(pp)])
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with patch.object(
        e1, "export", side_effect=AssertionError("verify must not export")
    ):
        e1.main()
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert '"verified": 1' in capsys.readouterr().out


def test_query_failure_keeps_latency_and_accounting(tmp_path):
    calls = e2.Calls(tmp_path, plan(), run_id="r")
    result = e2.question_result(
        plan(),
        {"manifest_sha256": "m"},
        {"id": "q", "question": "?"},
        calls,
        dataset="musique",
        method="dense",
    )
    assert result["status"] == "failed" and result["wall_seconds"] >= 0
    assert result["token_accounting"] == calls.journal.reference()
    assert (
        e2.score_result(result, {"id": "q", "answer": "x", "supporting_ids": ["p"]})[
            "f1"
        ]
        == 0
    )


@pytest.mark.skipif(
    not os.environ.get("E2_E1_PLAN"), reason="private completed E1 artifacts required"
)
def test_real_hippo_native_read_only_no_constructor_index_or_http():
    source = Path(os.environ["E1_HIPPO_SOURCE"])
    pp = Path(os.environ["E2_E1_PLAN"])
    e1plan = dense.read_json(pp)
    from hipporag import HippoRAG

    for dataset in target.DATASETS:
        row = next(
            r
            for r in e1plan["rows"]
            if r["method"] == "hipporag2" and r["dataset"] == dataset
        )
        corpus = dense.read_json(
            Path(e1plan["data_root"]) / f"data/processed/{dataset}/corpus.json"
        )
        directory = pp.parent.parent / row["output"]
        before = {
            p.relative_to(directory).as_posix(): dense.sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file()
        }
        with (
            patch(
                "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
            ),
            patch.object(
                HippoRAG,
                "__init__",
                side_effect=AssertionError("constructor forbidden"),
            ),
            patch.object(
                HippoRAG, "index", side_effect=AssertionError("index forbidden")
            ),
        ):
            loaded = indexes.load_ready_e1(e1plan, row, corpus, pp.parent.parent)

            def infer(messages):
                marker = "[[ ## fact_before_filter ## ]]\n"
                facts = json.loads(
                    messages[-1]["content"].split(marker)[1].split("\n\nRespond")[0]
                )
                return (
                    "[[ ## fact_after_filter ## ]]\n"
                    + json.dumps({"fact": facts["fact"][:1]})
                    + "\n[[ ## completed ## ]]"
                )

            rag = indexes.load_hippo_query_only(loaded, source, infer)
            vector = np.zeros(1024)
            vector[0] = 1
            result = indexes.retrieve_hippo_query_only(
                loaded,
                rag,
                "Synthetic offline question",
                vector,
                e1plan["embedding_digest"],
            )
            assert len(result["source_ids"]) == 5 and result["dense_fallback"] is False
            rag.extraction_llm.handler = (
                lambda messages: '[[ ## fact_after_filter ## ]]\n{"fact": []}\n[[ ## completed ## ]]'
            )
            assert (
                indexes.retrieve_hippo_query_only(
                    loaded,
                    rag,
                    "Synthetic offline empty filter",
                    vector,
                    e1plan["embedding_digest"],
                )["dense_fallback"]
                is True
            )

            def broken(messages):
                raise PermissionError("preserved filter IO error")

            rag.extraction_llm.handler = broken
            with pytest.raises(PermissionError, match="preserved"):
                indexes.retrieve_hippo_query_only(
                    loaded,
                    rag,
                    "Synthetic offline failure",
                    vector,
                    e1plan["embedding_digest"],
                )
        assert before == {
            p.relative_to(directory).as_posix(): dense.sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file()
        }


@pytest.mark.skipif(
    not os.environ.get("E2_RAPTOR_SOURCE"),
    reason="private E1 and pinned RAPTOR SDK required",
)
def test_real_raptor_dense_load_top5_and_provenance_without_http():
    pp = Path(os.environ["E2_E1_PLAN"])
    plan = dense.read_json(pp)
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        sdk = indexes.raptor.load_source(Path(os.environ["E2_RAPTOR_SOURCE"]))
        for dataset in target.DATASETS:
            corpus = dense.read_json(
                Path(plan["data_root"]) / f"data/processed/{dataset}/corpus.json"
            )
            rows = [
                r
                for r in plan["rows"]
                if r["dataset"] == dataset and r["method"] != "hipporag2"
            ]
            for row in rows:
                loaded = indexes.load_ready_e1(plan, row, corpus, pp.parent.parent)
                vector = np.zeros(1024)
                vector[0] = 1
                result = indexes.retrieve_ready_e1(
                    loaded,
                    "Synthetic offline question",
                    vector,
                    embedding_digest=plan["embedding_digest"],
                    sdk=sdk,
                )
                assert len(result["passages"]) == 5 and len(result["scores"]) == 5
                assert set(result["source_ids"]) <= {p["id"] for p in corpus}
                if row["method"] == "raptor":
                    assert len(result["nodes"]) == 5
                    assert all(n["source_ids"] for n in result["nodes"])


def test_synthetic_end_to_end_reader_evaluator_tracking_and_resume(
    tmp_path, monkeypatch
):
    p = plan()
    p["datasets"] = {
        "musique": {"question_ids": ["q"], "labels_sha256_evaluator_only": ""}
    }
    raw = tmp_path / "data/processed/musique"
    raw.mkdir(parents=True)
    lp = raw / "labels.json"
    dense.write_json_atomic(
        lp, [{"id": "q", "answer": "Paris", "supporting_ids": ["p"]}]
    )
    p["datasets"]["musique"]["labels_sha256_evaluator_only"] = dense.sha256_file(lp)
    pp = tmp_path / "e1.json"
    dense.write_json_atomic(pp, {"data_root": str(tmp_path)})
    p["e1_plan"] = str(pp)
    output = tmp_path / "output"
    calls = e2.Calls(output, p, run_id="r")
    vector = np.zeros(1024)
    vector[0] = 1
    loaded = {
        "kind": "dense",
        "manifest_sha256": "m",
        "embedding_digest": "bge",
        "vectors": np.asarray([vector]),
        "corpus": [{"id": "p", "title": "Paris", "text": "A city."}],
    }
    embedding = Session({"embeddings": [vector.tolist()], "prompt_eval_count": 3})
    reader = Session(body())
    query = {"id": "q", "question": "Which city?"}

    def send(operation):
        return {
            "session": embedding if operation == "query_embedding" else reader,
            "url": "https://example.invalid",
        }

    result = e2.question_result(
        p, loaded, query, calls, dataset="musique", method="dense", send=send
    )
    assert result["status"] == "completed" and result["answer"] == "Paris"
    assert len(result["operations"]) == 2
    assert (
        e2.score_result(
            result, {"id": "q", "answer": "Paris", "supporting_ids": ["p"]}
        )["em"]
        == 1
    )
    before = calls.journal.reference()
    replay = e2.question_result(
        p, loaded, query, calls, dataset="musique", method="dense"
    )
    assert replay["status"] == "completed" and all(replay["cache_hits"].values())
    assert calls.journal.reference() == before
    assert embedding.posts == reader.posts == 1
    key = target.digest(["musique", "dense", "q"])
    result_path = output / f"question-{key}.json"
    dense.write_json_atomic(result_path, result)
    dense.write_json_atomic(
        output / "manifest.json",
        {
            "run_id": "r",
            "status": "failed",
            "plan_sha256": target.digest(p),
            "results": {key: dense.sha256_file(result_path)},
            "token_accounting": calls.journal.reference(),
        },
    )
    report = e2.summary(p, output)
    assert report["rows"][0]["em"] == 1 and report["rows"][1]["em"] == 0
    assert report["rows"][2]["passage_recall_at_5"] is None
    payload = e2.tracking_payload(p, output, "musique", "dense")
    assert payload["system"] == "dense" and payload["metrics"]["token_f1"] == 1
    assert (
        payload["token_accounting"]["summary"]["known_subtotal"][
            "embedding_input_tokens"
        ]
        == 3
    )
    assert payload["questions"][0]["row"]["prompt_tokens"] == 10


def test_code_pin_rejected_without_HTTP(tmp_path, monkeypatch):
    monkeypatch.setattr(e2, "ROOT", tmp_path)
    (tmp_path / "code.py").write_text("new", encoding="utf-8")
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError, match="code_changed"):
            e2.verify({"version": e2.VERSION, "code_sha256": {"code.py": "old"}})


def test_http_error_keeps_reported_usage_and_elapsed(tmp_path):
    calls = e2.Calls(tmp_path, plan(), run_id="r")

    class HTTPErrorSession(Session):
        def post(self, *args, **kwargs):
            response = super().post(*args, **kwargs)

            def failure():
                raise target.requests.HTTPError("server failure")

            response.raise_for_status = failure
            return response

    session = HTTPErrorSession(body())
    with pytest.raises(target.requests.HTTPError):
        call(calls, session)
    from scripts.token_accounting import read_records

    terminal = read_records(calls.journal.path)[-1]
    assert terminal["status"] == "error" and terminal["llm_input_tokens"] == 10
    assert terminal["llm_output_tokens"] == 4 and terminal["wall_seconds"] >= 0


def test_execute_approval_worker_and_claim_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(e2, "verify", lambda p: True)
    p = plan()
    p.update(
        e1_workspace=str(tmp_path),
        tokenizer_cache={"directory": str(tmp_path), "sha256": {"cached": "sha"}},
    )
    pp = tmp_path / "plan.json"
    dense.write_json_atomic(pp, p)
    (tmp_path / ".cache").mkdir()
    config = {
        "model": e2.MODEL,
        "base_url": "https://api.duckduck.cloud/v1",
        "embedding_model": p["embedding_model"],
    }
    output = tmp_path / "output"
    output.mkdir()
    with patch(
        "requests.Session",
        side_effect=AssertionError("no HTTP or client before guards"),
    ):
        with pytest.raises(ValueError, match="approval"):
            e2.execute(pp, output, "dense", config=config)
        (output / "running.lock").write_text("live", encoding="utf-8")
        with pytest.raises(FileExistsError):
            e2.execute(
                pp, output, "dense", approved_sha=dense.sha256_file(pp), config=config
            )
        with pytest.raises(ValueError, match="already_claimed"):
            e2.execute(
                pp,
                tmp_path / "other",
                "dense",
                approved_sha=dense.sha256_file(pp),
                config=config,
            )
        assert (output / "running.lock").read_text(encoding="utf-8") == "live"
