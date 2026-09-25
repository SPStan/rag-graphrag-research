"""Pure planning helpers for a future copy-only HippoRAG index repair."""


def filter_embedding_table_to_ids(table, expected_ids, *, id_column="hash_id"):
    """Keep reusable vector rows and report vectors that must be added/removed.

    This function does not write files, embed text, or touch an index. Missing
    rows are reported so a caller cannot mistake the filtered partial table for
    a complete vector store.
    """
    if id_column not in table.column_names:
        raise ValueError(f"Embedding table is missing {id_column!r}")
    current = table.column(id_column).to_pylist()
    if len(current) != len(set(current)):
        raise ValueError("Embedding table contains duplicate vector IDs")
    expected = set(expected_ids)
    present = set(current)
    retained_ids = present & expected
    obsolete_ids = present - expected
    missing_ids = expected - present
    mask = [value in expected for value in current]
    filtered = table.filter(mask)
    return filtered, {
        "source_rows": len(current),
        "target_rows": len(expected),
        "retained_rows": len(retained_ids),
        "obsolete_rows": len(obsolete_ids),
        "missing_rows": len(missing_ids),
        "complete": not obsolete_ids and not missing_ids,
    }
