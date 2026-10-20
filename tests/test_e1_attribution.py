"""No model calls: physical totals and standalone attribution are distinct."""

from copy import deepcopy

from scripts.run_e1 import attribute_costs, row_usage


def row(method, run, tokens, complete=True, historical=True):
    return {
        "method": method,
        "run_id": run,
        "seconds": 2,
        "token_accounting": {
            "summary": {
                "complete": complete,
                "historical_cache_cost_complete": historical,
                "known_subtotal": {"embedding_input_tokens": tokens},
            }
        },
    }


def test_standalone_includes_failed_producer_history_without_physical_double_count():
    producer = row("dense", "p", 100)
    producer["cumulative_accounting"] = deepcopy(row_usage(producer))
    producer["cumulative_accounting"]["known_subtotal"]["embedding_input_tokens"] = 119
    producer["cumulative_accounting"]["complete"] = False
    producer["cumulative_seconds"] = 5
    consumer = row("raptor", "c", 10)
    consumer["validation"] = {"leaf_producer_run_id": "p"}
    rows = [producer, consumer]
    before = deepcopy(rows)
    attribute_costs(rows)
    assert consumer["standalone_known_subtotal"]["embedding_input_tokens"] == 129
    assert consumer["attributed_construction_seconds"] == 7
    assert consumer["measured_run_seconds"] == 2
    assert not consumer["standalone_cost_complete"]
    assert (
        sum(row_usage(r)["known_subtotal"]["embedding_input_tokens"] for r in rows)
        == 129
    )
    assert [row_usage(r) for r in rows] == [row_usage(r) for r in before]


def test_historical_unknown_is_not_complete():
    rows = [row("hipporag2", "h", 20, historical=False)]
    attribute_costs(rows)
    assert not rows[0]["standalone_cost_complete"]


def test_missing_producer_and_unknown_time_are_explicit():
    consumer = row("raptor", "c", 10)
    attribute_costs([consumer])
    assert not consumer["standalone_cost_complete"]
    producer = row("dense", "p", 100)
    del producer["seconds"]
    consumer["validation"] = {"leaf_producer_run_id": "p"}
    attribute_costs([producer, consumer])
    assert consumer["attributed_construction_seconds"] is None
    assert consumer["standalone_cost_complete"]
