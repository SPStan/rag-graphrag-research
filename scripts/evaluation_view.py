"""Load and apply a frozen ordered evaluation ID view."""

import hashlib
import json
from pathlib import Path


def ordered_ids_sha256(question_ids):
    payload = json.dumps(question_ids, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_view(path, dataset, labels_path):
    if labels_path is None:
        raise ValueError("A separate pinned labels file is required for an evaluation view")
    path = Path(path)
    view = json.loads(path.read_text(encoding="utf-8"))
    ids = view.get("question_ids")
    if view.get("dataset") != dataset:
        raise ValueError("Evaluation view dataset does not match the run")
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
        raise ValueError("Evaluation view must contain a non-empty string question_ids list")
    if len(set(ids)) != len(ids):
        raise ValueError("Evaluation view contains duplicate question IDs")
    if ordered_ids_sha256(ids) != view.get("ordered_question_ids_sha256"):
        raise ValueError("Evaluation view ordered ID hash does not match its contents")
    labels_hash = hashlib.sha256(Path(labels_path).read_bytes()).hexdigest()
    if labels_hash != view.get("labels_sha256"):
        raise ValueError("Pinned labels do not match the frozen evaluation view")
    return {
        "name": view.get("view"),
        "path": path.name,
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "ordered_question_ids_sha256": view["ordered_question_ids_sha256"],
        "question_ids": ids,
    }


def select_in_view(rows, question_ids, kind):
    by_id = {}
    for row in rows:
        row_id = row.get("id")
        if row_id in by_id:
            raise ValueError(f"Duplicate {kind} ID in pinned data: {row_id}")
        by_id[row_id] = row
    missing = [row_id for row_id in question_ids if row_id not in by_id]
    if missing:
        raise ValueError(f"Evaluation view contains unknown {kind} IDs: {missing[:3]}")
    return [by_id[row_id] for row_id in question_ids]
