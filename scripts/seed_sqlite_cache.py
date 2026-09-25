"""Copy a stopped SQLite LLM cache into a fresh run without changing the source."""

import hashlib
from pathlib import Path
import sqlite3
from urllib.parse import quote


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _table_row_counts(connection):
    counts = {}
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    for (table_name,) in tables:
        escaped = table_name.replace('"', '""')
        counts[table_name] = connection.execute(
            f'SELECT count(*) FROM "{escaped}"').fetchone()[0]
    return counts


def seed_sqlite_cache(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise ValueError("LLM cache seed must be an existing file")
    if destination.exists():
        raise ValueError("LLM cache destination already exists; refusing to overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash_before = sha256_file(source)
    source_uri = "file:" + quote(source.resolve().as_posix(), safe="/:\\") + "?mode=ro"
    src = sqlite3.connect(source_uri, uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.execute("PRAGMA query_only = ON")
        integrity = src.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("Source LLM cache failed SQLite integrity_check")
        source_row_counts = _table_row_counts(src)
        src.backup(dst)
        target_integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if target_integrity != "ok":
            raise ValueError("Copied LLM cache failed SQLite integrity_check")
        table_count = dst.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        copied_row_counts = _table_row_counts(dst)
        if source_row_counts != copied_row_counts:
            raise ValueError("Copied LLM cache row counts do not match the read-only source")
    except Exception:
        dst.close()
        src.close()
        raise
    else:
        dst.close()
        src.close()
    source_hash_after = sha256_file(source)
    if source_hash_before != source_hash_after:
        raise ValueError("Source LLM cache changed while it was being copied")
    return {
        "source_sha256": source_hash_before,
        "copied_sha256": sha256_file(destination),
        "sqlite_table_count": table_count,
        "source_row_counts": source_row_counts,
        "sqlite_row_counts": copied_row_counts,
    }
