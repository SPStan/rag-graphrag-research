"""Read-only coverage audit for a saved HippoRAG OpenIE state and LLM cache.

The report deliberately contains only aggregate counts and SHA-256 fingerprints
of sampled passages.  It never writes to the OpenIE JSON or SQLite cache and
does not send requests to an LLM endpoint.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile


CATEGORY_ORDER = (
    "entities_empty_triples_present",
    "entities_present_triples_empty",
    "both_empty",
    "both_present",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_list(value, field, position):
    if not isinstance(value, list):
        raise ValueError(f"Document {position} has a non-list {field}")
    return value


def passage_fingerprint(document):
    passage = document.get("passage")
    if not isinstance(passage, str):
        raise ValueError("OpenIE document is missing string passage text")
    return hashlib.sha256(passage.encode("utf-8")).hexdigest()


def table_like_features(passage):
    """Return conservative structural flags; they are not a document label."""
    lines = [line for line in passage.splitlines() if line.strip()]
    pipe_lines = sum("|" in line for line in lines)
    tab_lines = sum("\t" in line for line in lines)
    return {
        "line_count": len(lines),
        "pipe_lines": pipe_lines,
        "tab_lines": tab_lines,
        "table_like": pipe_lines >= 2 or tab_lines >= 2,
    }


def classify_documents(state, seed=42, sample_size=3):
    if not isinstance(state, dict) or not isinstance(state.get("docs"), list):
        raise ValueError("OpenIE state must be an object with a docs list")
    if sample_size < 1:
        raise ValueError("sample_size must be positive")

    categories = Counter()
    records = defaultdict(list)
    for position, document in enumerate(state["docs"]):
        if not isinstance(document, dict):
            raise ValueError(f"Document {position} is not an object")
        entities = _require_list(document.get("extracted_entities"), "extracted_entities", position)
        triples = _require_list(document.get("extracted_triples"), "extracted_triples", position)
        if not entities and triples:
            category = "entities_empty_triples_present"
        elif entities and not triples:
            category = "entities_present_triples_empty"
        elif not entities and not triples:
            category = "both_empty"
        else:
            category = "both_present"
        features = table_like_features(document["passage"])
        record = {
            "passage_sha256": passage_fingerprint(document),
            "entity_count": len(entities),
            "triple_count": len(triples),
            **features,
        }
        categories[category] += 1
        records[category].append(record)

    samples = {}
    for category in CATEGORY_ORDER:
        ranked = sorted(
            records[category],
            key=lambda record: hashlib.sha256(
                f"{seed}:{record['passage_sha256']}".encode("utf-8")
            ).hexdigest(),
        )
        samples[category] = ranked[:sample_size]
    return {
        "documents": sum(categories.values()),
        "categories": {category: categories[category] for category in CATEGORY_ORDER},
        "table_like_by_category": {
            category: sum(record["table_like"] for record in records[category])
            for category in CATEGORY_ORDER
        },
        "spot_check": {
            "seed": seed,
            "sample_size_per_category": sample_size,
            "records": samples,
            "note": (
                "Fingerprints and structural flags support local follow-up without "
                "publishing passage text or titles. table_like is a heuristic, not "
                "a manual judgement."
            ),
        },
    }


def _response_kind(message):
    try:
        value = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return "non_json"
    if not isinstance(value, dict):
        return "json_other"
    if isinstance(value.get("named_entities"), list):
        return "ner_empty" if not value["named_entities"] else "ner_present"
    if isinstance(value.get("triples"), list):
        return "triples_empty" if not value["triples"] else "triples_present"
    return "json_other"


def inspect_cache(cache_path):
    """Return aggregate cache diagnostics without exposing messages or keys."""
    if cache_path is None:
        return {
            "available": False,
            "linkage_to_passages": "not_attempted",
        }
    cache_path = Path(cache_path)
    if not cache_path.is_file():
        raise ValueError(f"LLM cache does not exist: {cache_path}")
    connection = sqlite3.connect(f"{cache_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "cache" not in tables:
            raise ValueError("LLM cache has no cache table")
        kinds = Counter()
        finish_reasons = Counter()
        finish_by_kind = defaultdict(Counter)
        malformed_metadata = 0
        for message, metadata_text in connection.execute("SELECT message, metadata FROM cache"):
            kind = _response_kind(message)
            kinds[kind] += 1
            try:
                metadata = json.loads(metadata_text)
            except (TypeError, json.JSONDecodeError):
                malformed_metadata += 1
                finish_reason = "metadata_unreadable"
            else:
                finish_reason = metadata.get("finish_reason") or "missing"
            finish_reasons[finish_reason] += 1
            finish_by_kind[kind][finish_reason] += 1
        return {
            "available": True,
            "entries": sum(kinds.values()),
            "response_kinds": dict(sorted(kinds.items())),
            "finish_reasons": dict(sorted(finish_reasons.items())),
            "finish_reasons_by_response_kind": {
                kind: dict(sorted(values.items()))
                for kind, values in sorted(finish_by_kind.items())
            },
            "malformed_metadata": malformed_metadata,
            "linkage_to_passages": (
                "unavailable: this cache stores request hashes, responses and metadata, "
                "but not the original prompts or passage identifiers"
            ),
        }
    finally:
        connection.close()


def build_report(state_path, cache_path=None, seed=42, sample_size=3, source_run_id=None):
    state_path = Path(state_path)
    state = read_json(state_path)
    report = {
        "schema_version": 1,
        "audit_kind": "hipporag_openie_coverage_read_only",
        "source": {
            "openie_state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
            "source_run_id": source_run_id,
        },
        "coverage": classify_documents(state, seed=seed, sample_size=sample_size),
        "cache": inspect_cache(cache_path),
        "limitations": [
            "Empty entities or triples are coverage observations, not proven extraction failures.",
            "The final cache-replay manifest cannot prove that an earlier index build had no OpenIE failures.",
            "Cache rows cannot be linked to passages from the stored SQLite schema alone.",
        ],
    }
    return report


def write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="OpenIE state JSON")
    parser.add_argument("--cache", type=Path, help="optional HippoRAG SQLite LLM cache")
    parser.add_argument("--output", type=Path, required=True, help="safe compact JSON report")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-size", type=int, default=3)
    parser.add_argument("--source-run-id")
    args = parser.parse_args(argv)
    report = build_report(args.state, args.cache, args.seed, args.sample_size, args.source_run_id)
    write_json_atomic(args.output, report)
    print(json.dumps({
        "status": "verified",
        "documents": report["coverage"]["documents"],
        "categories": report["coverage"]["categories"],
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
