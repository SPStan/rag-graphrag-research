"""Offline E4 token cost: complete values remain null when history is incomplete."""

import argparse
import copy
import csv
import json
import math
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from scripts import run_dense as dense, run_e1 as e1, token_accounting as accounting

NS = (100, 1000, 10000, 100000)
CHANNELS = ("llm", "embedding")
METHODS = ("dense", "hipporag2", "raptor")
FIELDS = accounting.TOKEN_FIELDS


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def crossover(i_dense, q_dense, i_graph, q_graph):
    """Compare graph-minus-Dense affine costs for all real N>0."""
    require(
        all(math.isfinite(x) and x >= 0 for x in (i_dense, q_dense, i_graph, q_graph)),
        "invalid_cost",
    )
    intercept, slope = i_graph - i_dense, q_graph - q_dense
    if slope == 0:
        return {
            "status": "equal_all_N"
            if intercept == 0
            else "dense_cheaper_all_N"
            if intercept > 0
            else "graph_cheaper_all_N",
            "N_star": None,
            "direction": None,
        }
    point = -intercept / slope
    if not math.isfinite(point):
        return {"status": "unrepresentable_crossing", "N_star": None, "direction": None}
    if point > 0:
        return {
            "status": "positive_crossing",
            "N_star": point,
            "direction": "graph_cheaper_after" if slope < 0 else "graph_cheaper_before",
        }
    return {
        "status": "dense_cheaper_all_positive_N"
        if slope > 0
        else "graph_cheaper_all_positive_N",
        "N_star": None,
        "direction": None,
    }


def projection(i, q, n, em):
    require(n > 0 and 0 <= em <= 1, "invalid_N_or_EM")
    require(i >= 0 and q >= 0 and math.isfinite(i + q), "invalid_cost")
    total, mean = i + n * q, i / n + q
    return {"T": total, "C": mean, "tokens_per_exact": mean / em if em else None}


def pin_by_name(metadata, name):
    pins = [
        sha
        for path, sha in metadata["files"].items()
        if PureWindowsPath(path).name == name
    ]
    require(len(pins) == 1, "missing_or_ambiguous_E3_pin")
    return pins[0]


def component(tokens, complete, channel):
    known = (
        sum(tokens[k] for k in FIELDS[:2]) if channel == "llm" else tokens[FIELDS[2]]
    )
    require(
        isinstance(known, (float, int)) and math.isfinite(known) and known >= 0,
        "invalid_known_tokens",
    )
    return {
        "known": known,
        "complete": bool(complete),
        "value": known if complete else None,
    }


def index_complete(row, channel, rows):
    fields = FIELDS[:2] if channel == "llm" else FIELDS[2:]

    def measured(r):
        summary = e1.row_usage(r)
        return (
            summary.get("historical_cache_cost_complete", False)
            and not summary.get("journal_corrupt_tail", False)
            and all(
                not phase.get("unfinished", 0)
                and all(phase["unknown_fields"][k] == 0 for k in fields)
                for phase in summary["phases"]
            )
        )

    complete = measured(row)
    if row["method"] == "raptor":
        producer = next(
            r for r in rows if r["run_id"] == row["validation"]["leaf_producer_run_id"]
        )
        complete = complete and measured(producer)
    return complete


def bounded_crossover(dense_cost, graph_cost):
    """Unknown nonnegative costs can establish dominance, not a numeric crossing."""
    a, b = dense_cost, graph_cost
    exact_a = a["I"]["complete"] and a["q"]["complete"]
    exact_b = b["I"]["complete"] and b["q"]["complete"]
    if exact_a and exact_b:
        return crossover(
            a["I"]["known"], a["q"]["known"], b["I"]["known"], b["q"]["known"]
        )
    if (
        exact_a
        and b["I"]["known"] >= a["I"]["known"]
        and b["q"]["known"] >= a["q"]["known"]
    ):
        if b["I"]["known"] > a["I"]["known"] or b["q"]["known"] > a["q"]["known"]:
            return {
                "status": "dense_cheaper_all_positive_N",
                "N_star": None,
                "proof": "exact Dense cost below graph known lower bounds",
            }
    if (
        exact_b
        and a["I"]["known"] >= b["I"]["known"]
        and a["q"]["known"] >= b["q"]["known"]
    ):
        if a["I"]["known"] > b["I"]["known"] or a["q"]["known"] > b["q"]["known"]:
            return {
                "status": "graph_cheaper_all_positive_N",
                "N_star": None,
                "proof": "exact graph cost below Dense known lower bounds",
            }
    return {"status": "unidentified_incomplete_cost", "N_star": None}


def exact_answer_crossover(dense_cost, dense_em, graph_cost, graph_em):
    """C/EM compares I/EM and q/EM, not the unadjusted per-question costs."""
    require(
        all(math.isfinite(em) and 0 <= em <= 1 for em in (dense_em, graph_em)),
        "invalid_EM",
    )
    if dense_em == 0 or graph_em == 0:
        undefined = {"status": "undefined_EM_zero", "N_star": None}
        return {
            "known_minimum_scenario": dict(undefined),
            "full_cost_result": dict(undefined),
        }

    def scaled(cost, em):
        return {
            k: {"known": cost[k]["known"] / em, "complete": cost[k]["complete"]}
            for k in ("I", "q")
        }

    a, b = scaled(dense_cost, dense_em), scaled(graph_cost, graph_em)
    return {
        "known_minimum_scenario": crossover(
            a["I"]["known"], a["q"]["known"], b["I"]["known"], b["q"]["known"]
        ),
        "full_cost_result": bounded_crossover(a, b),
    }


def load_inputs(root):
    """Aggregate-only inputs; never open labels, questions, or control per-case scores."""
    paths = {
        "E1": root / "results/summary/e1-indexing.json",
        "freeze": root / "results/summary/full-experiment.json",
        "E3": root / "results/summary/e3.json",
        **{
            d: root / f"results/summary/e2-{d}-s500.json"
            for d in ("musique", "hotpotqa")
        },
    }
    values = {k: dense.read_json(p) for k, p in paths.items()}
    require(
        dense.sha256_file(paths["E1"])
        == values["freeze"]["verification"]["E1_accounting_report_sha256"],
        "E1_freeze_pin_mismatch",
    )
    require(
        values["E1"]["complete"] and values["E3"]["comparison_complete"],
        "incomplete_experiment",
    )
    rows = copy.deepcopy(values["E1"]["rows"])
    e1.attribute_costs(
        rows
    )  # Existing accounting includes failed histories + Dense leaf attribution.
    configs = []
    for row in rows:
        dataset, method = row["dataset"], row["method"]
        original = next(
            r
            for r in values["E1"]["rows"]
            if (r["dataset"], r["method"]) == (dataset, method)
        )
        require(
            row["standalone_known_subtotal"] == original["standalone_known_subtotal"]
            and row["standalone_cost_complete"] == original["standalone_cost_complete"],
            "E1_standalone_attribution_mismatch",
        )
        query_report = values[dataset]
        require(
            dense.sha256_file(paths[dataset])
            == pin_by_name(values["E3"]["inputs"][dataset], paths[dataset].name),
            "E2_E3_pin_mismatch",
        )
        require(query_report["comparison_complete"], "incomplete_E2")
        query = next(r for r in query_report["rows"] if r["method"] == method)
        score = next(
            r
            for d in values["E3"]["datasets"]
            if d["dataset"] == dataset
            for r in d["rows"]
            if r["method"] == method
        )
        require(
            query["planned"] == 500
            and query["not_attempted"] == 0
            and query["completed"] + query["attempted_failed"] == 500
            and query["completed"] == score["completed"]
            and query["attempted_failed"] == score["attempted_failed"]
            and math.isclose(
                query["em"], score["metrics"]["em"]["mean"], abs_tol=1e-12
            ),
            "EM_or_coverage_mismatch",
        )
        phases = query["usage_by_operation"]
        require(
            set(phases)
            == (
                {"reader", "query_embedding", "filter"}
                if method == "hipporag2"
                else {"reader", "query_embedding"}
            ),
            "missing_or_unexpected_query_phase",
        )
        totals = {
            k: sum(op["known_subtotal"][k] for op in phases.values()) for k in FIELDS
        }
        models = query["logical_usage_by_model"]
        require(
            totals
            == {
                k: sum(x["known_subtotal"][k] for x in models.values()) for k in FIELDS
            },
            "query_phase_model_mismatch",
        )
        require(
            set(models)
            == {
                values["E1"]["models"]["model"],
                values["E1"]["models"]["embedding_model"],
            },
            "query_model_mismatch",
        )
        own = e1.row_usage(row)
        producers = [row["run_id"]]
        if method == "raptor":
            producers.append(row["validation"]["leaf_producer_run_id"])
        channels = {}
        for channel in CHANNELS:
            model = values["E1"]["models"][
                "embedding_model" if channel == "embedding" else "model"
            ]
            channels[channel] = {
                "I": component(
                    row["standalone_known_subtotal"],
                    index_complete(row, channel, rows),
                    channel,
                ),
                "q": component(
                    {k: v / 500 for k, v in totals.items()},
                    models[model]["complete"],
                    channel,
                ),
                "query_unknown_operations": models[model]["unknown_operations"],
            }
        configs.append(
            {
                "dataset": dataset,
                "method": method,
                "EM": query["em"],
                "completed": query["completed"],
                "attempted_failed": query["attempted_failed"],
                "query_denominator": 500,
                "channels": channels,
                "index_run_ids": producers,
                "E2_child_run_id": query_report["run_id"],
                "index_physical_own": own,
                "index_phases_current": row["operations"],
                "query_logical_phases": phases,
                "query_logical_models": models,
                "query_manifest_sha256": query_report["manifest_sha256"],
                "query_plan_sha256": query_report["plan_sha256"],
                "leaf_reuse_attribution": row.get("reused_leaf_build_cost"),
            }
        )
    require(
        len(configs) == 6 and len({(x["dataset"], x["method"]) for x in configs}) == 6,
        "expected_six_configurations",
    )
    own_total = sum(sum(e1.row_usage(r)["known_subtotal"].values()) for r in rows)
    require(
        own_total == values["E1"]["physical_known_tokens"], "E1_physical_total_mismatch"
    )
    return configs, {
        "files": {
            str(p.relative_to(root)): dense.sha256_file(p) for p in paths.values()
        },
        "E1_batch_id": values["E1"]["batch_id"],
        "E1_known_physical_tokens": own_total,
        "E1_unknown_reserve_not_usage": values["E1"]["budget_charge_upper_bound"]
        - own_total,
        "E1_cost_complete": values["E1"]["cost_complete"],
        "E2_physical_by_dataset": {
            d: {
                "child_run_id": values[d]["run_id"],
                "new_physical": values[d]["new_physical_accounting"],
                "S500_physical": values[d]["S500_physical_accounting"],
            }
            for d in ("musique", "hotpotqa")
        },
        "E2_cumulative_physical_once": values["hotpotqa"]["cumulative_E2_accounting"],
    }


def build(root):
    configs, inputs = load_inputs(root)
    table, crossings = [], []
    for config in configs:
        for channel, cost in config["channels"].items():
            complete = cost["I"]["complete"] and cost["q"]["complete"]
            for n in NS:
                lower = projection(
                    cost["I"]["known"], cost["q"]["known"], n, config["EM"]
                )
                table.append(
                    {
                        "dataset": config["dataset"],
                        "method": config["method"],
                        "channel": channel,
                        "N": n,
                        "EM": config["EM"],
                        "complete": complete,
                        "known_minimum": lower,
                        "full_cost": lower if complete else None,
                    }
                )
        if config["method"] != "dense":
            baseline = next(
                c
                for c in configs
                if c["dataset"] == config["dataset"] and c["method"] == "dense"
            )
            for channel in CHANNELS:
                a, b = baseline["channels"][channel], config["channels"][channel]
                known = crossover(
                    a["I"]["known"], a["q"]["known"], b["I"]["known"], b["q"]["known"]
                )
                crossings.append(
                    {
                        "dataset": config["dataset"],
                        "method": config["method"],
                        "channel": channel,
                        "known_minimum_scenario": known,
                        "full_cost_result": bounded_crossover(a, b),
                        "per_exact_answer": exact_answer_crossover(
                            a, baseline["EM"], b, config["EM"]
                        ),
                    }
                )
    return {
        "version": "e4-token-cost-v1",
        "code_sha256": {
            name: dense.sha256_file(Path(__file__).with_name(name))
            for name in ("e4_cost.py", "run_e1.py")
        },
        "inputs": inputs,
        "N": NS,
        "configurations": configs,
        "projections": table,
        "crossovers": crossings,
        "assumptions": [
            "I is standalone attributed construction including recorded failed histories and RAPTOR Dense leaves.",
            "q is logical request usage/500, not fresh physical POST expense; reusable pilot usage is not charged again.",
            "Reader/filter/query embedding included; failures remain in the offered-question denominator.",
            "EM is aggregate exact match on the same500 IDs, including failures; not F1.",
            "Quality and mean request mix are assumed stationary for projected N; no additional inference.",
            "Known minima are lower bounds, not measurements of full cost; reservations are not usage.",
            "LLM and local BGE tokens are separate units, not money; LLM input/output and mixed indexing models retained.",
            "Development S500 and historical control-score disclosure retained; no signal selection or control per-case export.",
        ],
    }


def markdown(report):
    def number(value):
        return "неизвестно" if value is None else f"{value:,.1f}".replace(",", " ")

    lines = [
        "# E4: токенная стоимость и окупаемость",
        "",
        "При неполном учёте показан известный минимум; полная стоимость остаётся неизвестной.",
        "LLM input+output и локальные BGE input tokens считаются отдельно; это не денежные цены.",
        "",
        "| Dataset | Method | EM | I LLM known | q LLM known | I BGE known | q BGE known | I LLM complete | I BGE complete |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for c in report["configurations"]:
        a, b = c["channels"]["llm"], c["channels"]["embedding"]
        lines.append(
            f"| {c['dataset']} | {c['method']} | {100 * c['EM']:.1f}% | {number(a['I']['known'])} | {number(a['q']['known'])} | {number(b['I']['known'])} | {number(b['q']['known'])} | {a['I']['complete']} | {b['I']['complete']} |"
        )
    for channel in CHANNELS:
        lines += [
            "",
            f"## {channel}: projected tokens",
            "",
            "| Dataset | Method | N | T known minimum | C known minimum | C/EM known minimum | Full cost |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for r in report["projections"]:
            if r["channel"] != channel:
                continue
            k = r["known_minimum"]
            lines.append(
                f"| {r['dataset']} | {r['method']} | {r['N']} | {number(k['T'])} | {number(k['C'])} | {number(k['tokens_per_exact'])} | {'complete' if r['complete'] else 'неизвестно'} |"
            )
    lines += [
        "",
        "## Окупаемость относительно Dense",
        "",
        "| Dataset | Method | Unit | Показатель | Known-cost scenario | N* | Full-cost conclusion |",
        "|---|---|---|---|---|---:|---|",
    ]
    descriptions = {
        "dense_cheaper_all_positive_N": "Dense дешевле при всех N>0",
        "graph_cheaper_all_positive_N": "граф дешевле при всех N>0",
        "dense_cheaper_all_N": "Dense дешевле при равных q",
        "graph_cheaper_all_N": "граф дешевле при равных q",
        "equal_all_N": "стоимости равны при всех N",
        "positive_crossing": "положительное пересечение",
        "unrepresentable_crossing": "вне численного диапазона",
        "unidentified_incomplete_cost": "не определяется: неполный учёт",
        "undefined_EM_zero": "не определено: EM=0",
    }
    for x in report["crossovers"]:
        for basis, view in (("C(N)", x), ("C(N)/EM", x["per_exact_answer"])):
            k, f = view["known_minimum_scenario"], view["full_cost_result"]
            star = number(k["N_star"]) if k["N_star"] is not None else "нет"
            if k["status"] in ("undefined_EM_zero", "unidentified_incomplete_cost"):
                star = "не определено"
            lines.append(
                f"| {x['dataset']} | {x['method']} | {x['channel']} | {basis} | {descriptions[k['status']]} | {star} | {descriptions[f['status']]} |"
            )
    lines += [
        "",
        "[График C(N): пунктир — известный минимум](e4-cost.svg)",
        "",
        "Источники, фазы, повторы и неизвестные части: [JSON](e4-cost.json).",
        "Формулы и выводы: [протокол](../../docs/E4_COST.md).",
        "",
        *["- " + x for x in report["assumptions"]],
        "",
    ]
    return chr(10).join(lines)


def plot(report, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context({"svg.hashsalt": "e4-token-cost-v1", "font.size": 9}):
        fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), sharex=True)
        for i, dataset in enumerate(("musique", "hotpotqa")):
            for j, channel in enumerate(CHANNELS):
                ax = axes[i, j]
                for method in METHODS:
                    rows = [
                        r
                        for r in report["projections"]
                        if (r["dataset"], r["method"], r["channel"])
                        == (dataset, method, channel)
                    ]
                    complete = all(r["complete"] for r in rows)
                    ax.plot(
                        [r["N"] for r in rows],
                        [r["known_minimum"]["C"] for r in rows],
                        marker="o",
                        linestyle="-" if complete else "--",
                        label=method + ("" if complete else " (known minimum)"),
                    )
                ax.set_xscale("log")
                ax.set_yscale("log")
                ax.set_title(f"{dataset}: {channel}")
                ax.set_ylabel("Tokens per offered question")
                ax.grid(alpha=0.25)
                ax.legend(fontsize=7)
                if i == 1:
                    ax.set_xlabel("N (log scale)")
        fig.suptitle(
            "C(N) = I/N + q; dashed curves are known-cost minima, not full estimates"
        )
        fig.tight_layout()
        fig.savefig(path, metadata={"Date": None, "Creator": "e4-token-cost-v1"})
        plt.close(fig)
    if path.suffix.lower() == ".svg":
        # Normalize Matplotlib path-line whitespace; keep the figure unchanged.
        path.write_text(
            chr(10).join(
                line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()
            )
            + chr(10),
            encoding="utf-8",
            newline="\n",
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path, default=Path("results/summary/e4-cost"))
    parser.add_argument(
        "--plot", action="store_true", help="Use existing matplotlib installation"
    )
    args = parser.parse_args(argv)
    with (
        patch(
            "socket.socket.connect", side_effect=AssertionError("E4_network_forbidden")
        ),
        patch(
            "socket.socket.connect_ex",
            side_effect=AssertionError("E4_network_forbidden"),
        ),
    ):
        report = build(args.root.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        dense.write_json_atomic(args.output.with_suffix(".json"), report)
        args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
        with args.output.with_suffix(".csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "dataset",
                    "method",
                    "channel",
                    "N",
                    "complete",
                    "T_known_minimum",
                    "C_known_minimum",
                    "tokens_per_exact_known_minimum",
                    "T_full",
                    "C_full",
                ),
            )
            writer.writeheader()
            for row in report["projections"]:
                full, lower = row["full_cost"], row["known_minimum"]
                writer.writerow(
                    {
                        **{
                            k: row[k]
                            for k in ("dataset", "method", "channel", "N", "complete")
                        },
                        "T_known_minimum": lower["T"],
                        "C_known_minimum": lower["C"],
                        "tokens_per_exact_known_minimum": lower["tokens_per_exact"],
                        "T_full": full["T"] if full else None,
                        "C_full": full["C"] if full else None,
                    }
                )
        if args.plot:
            plot(report, args.output.with_suffix(".svg"))
    print(
        json.dumps(
            {
                "configurations": len(report["configurations"]),
                "projection_rows": len(report["projections"]),
                "HTTP": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
