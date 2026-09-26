"""Resume a frozen repair schedule using a caller supplied extraction transport.

The checkpoint is private and must live under ignored results/raw storage.
No model transport is created here.
"""

from copy import deepcopy

from scripts.hipporag_repair import merge_attempt_ledgers, apply_openie_updates
from scripts.hipporag_repair_journal import RepairJournal


def run_repair_pass(journal, targets, source_attempts, source_state,
                    passage_id_to_index, execute):
    """Run remaining tasks, then return merged ledger and patched state.

    execute(task, named_entities) returns the existing executor's
    {attempt, values} result. It is called only for unfinished tasks.
    """
    keys = [RepairJournal.task_key(task) for task in targets]
    if keys != journal.expected_task_keys:
        raise ValueError("Targets differ from the frozen schedule")
    completed = journal.data["completed_task_keys"]
    for index in range(len(completed), len(targets)):
        planned = deepcopy(targets[index])
        if planned["stage"] == "openie_triples" and planned.get("operation") == "dependency_refresh":
            ner_rows = [row for row in journal.data["attempts"]
                        if row["task"]["passage_id"] == planned["passage_id"]
                        and row["task"]["stage"] == "openie_ner"]
            if len(ner_rows) != 1 or ner_rows[0]["attempt"]["status"] not in ("valid_empty", "valid_nonempty"):
                raise RuntimeError("Dependent triple requires a successful repaired NER")
            ner = ner_rows[0]
            planned.pop("dependency_attempt_pending", None)
            planned["dependency_attempt"] = ner["task"]["attempt"]
            entities = deepcopy(ner["values"])
        elif planned["stage"] == "openie_triples":
            index_in_state = passage_id_to_index[planned["passage_id"]]
            entities = deepcopy(next(doc["extracted_entities"] for doc in source_state["docs"]
                                     if doc["idx"] == index_in_state))
        else:
            entities = None
        journal.begin(planned)
        result = execute(planned, entities)
        journal.complete(planned, result["attempt"], result["values"])
    journal.finish(expected_task_keys=keys)
    rows = journal.data["attempts"]
    repair_attempts = [row["attempt"] for row in rows]
    merged = merge_attempt_ledgers(source_attempts, repair_attempts,
                                   list(passage_id_to_index))
    updates = [{"passage_id": row["task"]["passage_id"],
                "stage": row["task"]["stage"], "status": row["attempt"]["status"],
                "values": row["values"]} for row in rows
               if row["values"] is not None]
    state, summary = apply_openie_updates(source_state, passage_id_to_index, updates)
    return {"ledger": merged, "state": state, "state_summary": summary,
            "checkpoint_sha256": RepairJournal._output_sha(rows)}
