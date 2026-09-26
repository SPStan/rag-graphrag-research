"""Small, deterministic helpers for OpenIE attempt status and index gating."""

OPENIE_STAGES = ("openie_ner", "openie_triples")
VALID_STATUSES = {"valid_empty", "valid_nonempty"}
UNRESOLVED_STATUSES = {
    "parse_error", "truncated", "raw_response_missing", "request_error",
    "completion_unknown",
}


def classify_openie_attempt(response, finish_reason, values, *, parse_error=False,
                            request_error=False):
    """Classify an extraction attempt without treating empty lists as failures."""
    if request_error:
        return "request_error"
    if response is None:
        return "raw_response_missing"
    if finish_reason == "length":
        return "truncated"
    if finish_reason != "stop":
        return "completion_unknown"
    if response == "" or parse_error or not isinstance(values, list):
        return "parse_error"
    return "valid_empty" if not values else "valid_nonempty"


def build_openie_acceptance_gate(expected_passage_ids, attempts):
    """Check complete passage/stage coverage and terminal extraction outcomes."""
    expected = list(expected_passage_ids)
    if len(expected) != len(set(expected)):
        raise ValueError("Expected passage IDs must be unique")
    grouped = {(pid, stage): [] for pid in expected for stage in OPENIE_STAGES}
    unexpected = []
    for item in attempts:
        key = (item.get("passage_id"), item.get("stage"))
        if key not in grouped:
            unexpected.append({"passage_id": key[0], "stage": key[1],
                               "reason": "unexpected_passage_or_stage"})
            continue
        grouped[key].append(item)

    missing = []
    unresolved = []
    ner_groups = {pid: grouped[(pid, "openie_ner")] for pid in expected}
    for (pid, stage), items in grouped.items():
        items.sort(key=lambda item: (item.get("attempt")
                                     if isinstance(item.get("attempt"), int) else -1))
        if not items:
            missing.append({"passage_id": pid, "stage": stage})
            continue
        if len(items) > 3:
            unresolved.append({"passage_id": pid, "stage": stage,
                               "reason": "maximum_attempts_exceeded"})
            continue
        numbers = [item.get("attempt") for item in items]
        if (any(not isinstance(number, int) or isinstance(number, bool)
                for number in numbers)
                or numbers != list(range(1, len(items) + 1))):
            unresolved.append({"passage_id": pid, "stage": stage,
                               "reason": "attempt_sequence_incomplete"})
            continue
        if any(item.get("status") not in VALID_STATUSES | UNRESOLVED_STATUSES
               for item in items):
            unresolved.append({"passage_id": pid, "stage": stage,
                               "reason": "unknown_attempt_status"})
            continue
        if any(item.get("source_provenance_complete") is not True for item in items):
            unresolved.append({"passage_id": pid, "stage": stage,
                               "reason": "source_provenance_missing"})
        for previous, retry in zip(items, items[1:]):
            dependency_attempt = retry.get("dependency_attempt")
            ner_history = ner_groups[pid]
            dependency = next((row for row in ner_history
                               if row.get("attempt") == dependency_attempt), None)
            prior_ner_failure = any(
                row.get("attempt", 0) < dependency_attempt
                and row.get("status") not in VALID_STATUSES
                for row in ner_history
            ) if (isinstance(dependency_attempt, int)
                 and not isinstance(dependency_attempt, bool)) else False
            if retry.get("operation") == "dependency_refresh" and not (
                    stage == "openie_triples"
                    and retry.get("dependency_stage") == "openie_ner"
                    and isinstance(dependency_attempt, int)
                    and not isinstance(dependency_attempt, bool)
                    and dependency is not None
                    and dependency.get("status") in VALID_STATUSES
                    and prior_ner_failure):
                unresolved.append({"passage_id": pid, "stage": stage,
                                   "reason": "dependency_refresh_link_invalid"})
                break
            if previous.get("status") in VALID_STATUSES:
                valid_dependency_refresh = (
                    stage == "openie_triples"
                    and retry.get("operation") == "dependency_refresh"
                    and (retry.get("attempt", 0) <= 2
                         or retry.get("remedial_retry") is True)
                )
                if not valid_dependency_refresh:
                    unresolved.append({"passage_id": pid, "stage": stage,
                                       "reason": "retry_after_valid_attempt"})
                    break
                if retry.get("retry_of_attempt") != previous["attempt"]:
                    unresolved.append({"passage_id": pid, "stage": stage,
                                       "reason": "retry_link_missing"})
                    break
                continue
            if retry.get("retry_of_attempt") != previous["attempt"]:
                unresolved.append({"passage_id": pid, "stage": stage,
                                   "reason": "retry_link_missing"})
                break
            if retry.get("attempt", 0) > 2 and retry.get("remedial_retry") is not True:
                unresolved.append({"passage_id": pid, "stage": stage,
                                   "reason": "remedial_retry_not_declared"})
                break
        if items[-1]["status"] not in VALID_STATUSES:
            unresolved.append({"passage_id": pid, "stage": stage,
                               "reason": items[-1]["status"]})

    return {
        "eligible": not missing and not unresolved and not unexpected,
        "expected_passages": len(expected),
        "expected_stage_outcomes": len(grouped),
        "recorded_attempts": len(attempts),
        "missing_stage_outcomes": missing,
        "unresolved_stage_outcomes": unresolved,
        "unexpected_attempts": unexpected,
    }
