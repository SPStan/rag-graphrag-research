"""E4 formula limits and the aggregate-only offline CLI."""

import copy
import socket
from pathlib import Path, PureWindowsPath

import pytest

from scripts import e4_cost as e4, run_dense as dense

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "args,status,point",
    [
        ((10, 5, 110, 3), "positive_crossing", 50),
        ((10, 5, 0, 7), "positive_crossing", 5),
        ((10, 5, 20, 5), "dense_cheaper_all_N", None),
        ((10, 5, 0, 5), "graph_cheaper_all_N", None),
        ((10, 5, 10, 5), "equal_all_N", None),
        ((10, 5, 20, 7), "dense_cheaper_all_positive_N", None),
        ((10, 5, 0, 3), "graph_cheaper_all_positive_N", None),
        ((10, 5, 10, 7), "dense_cheaper_all_positive_N", None),
    ],
)
def test_crossovers(args, status, point):
    result = e4.crossover(*args)
    assert result["status"] == status and result["N_star"] == point
    if point:
        di, dq, gi, gq = args
        assert di + point * dq == gi + point * gq


def test_projection_uses_fractional_EM_not_F1_and_handles_zero():
    assert e4.projection(100, 2, 100, 0.5) == {"T": 300, "C": 3, "tokens_per_exact": 6}
    assert e4.projection(100, 2, 100, 0)["tokens_per_exact"] is None
    with pytest.raises(ValueError):
        e4.projection(100, 2, 0, 0.5)
    with pytest.raises(ValueError):
        e4.projection(100, 2, 100, 50)


def cost(i, q, complete=True):
    return {
        "I": {"known": i, "complete": complete},
        "q": {"known": q, "complete": complete},
    }


def test_unknown_cannot_be_a_numeric_break_even_but_bounds_can_prove_dominance():
    assert (
        e4.bounded_crossover(cost(0, 5), cost(10, 3, False))["status"]
        == "unidentified_incomplete_cost"
    )
    r = e4.bounded_crossover(cost(0, 2), cost(10, 3, False))
    assert r["status"] == "dense_cheaper_all_positive_N" and r["N_star"] is None
    r = e4.bounded_crossover(cost(10, 3, False), cost(0, 2))
    assert r["status"] == "graph_cheaper_all_positive_N"


def test_existing_E1_leaf_attribution_and_no_physical_double_count():
    configs, inputs = e4.load_inputs(ROOT)
    assert len(configs) == 6
    assert inputs["E1_known_physical_tokens"] == 32601955
    assert inputs["E1_unknown_reserve_not_usage"] == 61588
    assert not inputs["E1_cost_complete"]
    assert (
        sum(sum(c["index_physical_own"]["known_subtotal"].values()) for c in configs)
        == 32601955
    )
    for c in configs:
        if c["method"] == "raptor":
            assert len(c["index_run_ids"]) == 2
            assert c["leaf_reuse_attribution"]["embedding_input_tokens"] > 0


def test_actual_scope_missing_usage_filter_and_request_denominator():
    report = e4.build(ROOT)
    assert len(report["projections"]) == 48
    assert len(report["crossovers"]) == 8

    def aggregate_only(value):
        if isinstance(value, dict):
            assert not set(value) & {
                "question_id",
                "question_scores",
                "question_results",
                "answer",
                "supporting_ids",
                "labels",
            }
            for child in value.values():
                aggregate_only(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                aggregate_only(child)

    aggregate_only(report)
    for c in report["configurations"]:
        assert c["query_denominator"] == 500
        assert c["completed"] + c["attempted_failed"] == 500
        assert "question_scores" not in c and "question_id" not in c
        if c["method"] == "hipporag2":
            assert c["query_logical_phases"]["filter"]["calls"] == 500
        if c["method"] == "raptor":
            assert c["channels"]["llm"]["query_unknown_operations"] == 1
            assert c["channels"]["llm"]["q"]["value"] is None
    for row in report["projections"]:
        if not row["complete"]:
            assert row["full_cost"] is None


def test_offline_CLI_reproducible_and_network_forbidden(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("no network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    outputs = []
    for name in ("one", "two"):
        prefix = tmp_path / name
        e4.main(["--root", str(ROOT), "--output", str(prefix)])
        outputs.append(prefix.with_suffix(".json").read_bytes())
        assert prefix.with_suffix(".csv").exists()
        assert "неизвестно" in prefix.with_suffix(".md").read_text(encoding="utf-8")
    assert outputs[0] == outputs[1]
    # No labels/raw files are needed for this CLI.


@pytest.mark.parametrize("kind", ["E1", "E2", "E3"])
def test_tampered_sources_are_rejected_before_output(tmp_path, kind):
    import shutil

    files = [
        "e1-indexing.json",
        "full-experiment.json",
        "e3.json",
        "e2-musique-s500.json",
        "e2-hotpotqa-s500.json",
    ]
    for name in files:
        path = tmp_path / "results/summary" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "results/summary" / name, path)
    name = {"E1": "e1-indexing.json", "E2": "e2-musique-s500.json", "E3": "e3.json"}[
        kind
    ]
    path = tmp_path / "results/summary" / name
    value = dense.read_json(path)
    if kind == "E1":
        value["physical_known_tokens"] += 1
    elif kind == "E2":
        value["rows"][0]["em"] += 0.1
    else:
        value["datasets"][0]["rows"][0]["completed"] -= 1
    dense.write_json_atomic(path, value)
    with pytest.raises(ValueError):
        e4.main(["--root", str(tmp_path), "--output", str(tmp_path / "rejected")])
    assert not (tmp_path / "rejected.json").exists()


def test_EM_zero_build_is_undefined_not_zero(tmp_path, monkeypatch):
    configs, inputs = e4.load_inputs(ROOT)
    configs = copy.deepcopy(configs)
    configs[0]["EM"] = 0
    monkeypatch.setattr(e4, "load_inputs", lambda root: (configs, inputs))
    result = e4.build(tmp_path)
    assert all(
        r["known_minimum"]["tokens_per_exact"] is None
        for r in result["projections"]
        if (r["dataset"], r["method"]) == (configs[0]["dataset"], configs[0]["method"])
    )


def test_intersection_must_be_finite_and_direction_is_preserved():
    assert e4.crossover(0, 1e-308, 1e308, 0)["status"] == "unrepresentable_crossing"
    assert e4.crossover(0, 5, 100, 3)["direction"] == "graph_cheaper_after"
    assert e4.crossover(100, 3, 0, 5)["direction"] == "graph_cheaper_before"


def test_phase_mismatch_cannot_hide_behind_rebound_E3_pin(tmp_path):
    import shutil

    for name in (
        "e1-indexing.json",
        "full-experiment.json",
        "e3.json",
        "e2-musique-s500.json",
        "e2-hotpotqa-s500.json",
    ):
        path = tmp_path / "results/summary" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "results/summary" / name, path)
    p = tmp_path / "results/summary/e2-musique-s500.json"
    q = dense.read_json(p)
    q["rows"][0]["usage_by_operation"]["reader"]["known_subtotal"][
        "llm_input_tokens"
    ] += 1
    dense.write_json_atomic(p, q)
    ep = tmp_path / "results/summary/e3.json"
    e3 = dense.read_json(ep)
    for key in e3["inputs"]["musique"]["files"]:
        if PureWindowsPath(key).name == p.name:
            e3["inputs"]["musique"]["files"][key] = dense.sha256_file(p)
    dense.write_json_atomic(ep, e3)
    with pytest.raises(ValueError, match="query_phase_model_mismatch"):
        e4.build(tmp_path)


def test_windows_and_POSIX_metadata_pins_are_portable():
    for path in (
        "C:/work/results/e2.json",
        r"C:\work\results\e2.json",
        "/home/work/results/e2.json",
    ):
        assert e4.pin_by_name({"files": {path: "sha"}}, "e2.json") == "sha"


def test_raw_cost_dominance_does_not_imply_exact_answer_cost_dominance():
    a, b = cost(0, 2), cost(10, 3)
    assert e4.bounded_crossover(a, b)["status"] == "dense_cheaper_all_positive_N"
    adjusted = e4.exact_answer_crossover(a, 0.25, b, 1.0)
    assert adjusted["full_cost_result"]["status"] == "positive_crossing"
    assert adjusted["full_cost_result"]["N_star"] == 2.0
    assert adjusted["full_cost_result"]["direction"] == "graph_cheaper_after"


def test_exact_answer_unknown_and_zero_EM_keep_comparison_undefined():
    a, b = cost(0, 2), cost(10, 3, False)
    assert (
        e4.exact_answer_crossover(a, 0.25, b, 1.0)["full_cost_result"]["status"]
        == "unidentified_incomplete_cost"
    )
    for em_a, em_b in ((0, 1), (1, 0), (0, 0)):
        result = e4.exact_answer_crossover(a, em_a, b, em_b)
        assert result["full_cost_result"] == {
            "status": "undefined_EM_zero",
            "N_star": None,
        }


def test_real_LLM_dominance_is_verified_separately_per_exact_answer():
    report = e4.build(ROOT)
    for x in report["crossovers"]:
        if x["channel"] == "llm":
            assert (
                x["per_exact_answer"]["full_cost_result"]["status"]
                == "dense_cheaper_all_positive_N"
            )
    mu_hip_embedding = next(
        x
        for x in report["crossovers"]
        if (x["dataset"], x["method"], x["channel"])
        == ("musique", "hipporag2", "embedding")
    )
    assert (
        mu_hip_embedding["full_cost_result"]["status"] == "dense_cheaper_all_positive_N"
    )
    assert (
        mu_hip_embedding["per_exact_answer"]["full_cost_result"]["status"]
        == "unidentified_incomplete_cost"
    )
