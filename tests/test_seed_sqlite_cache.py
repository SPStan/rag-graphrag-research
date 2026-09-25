import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.seed_sqlite_cache import seed_sqlite_cache, sha256_file


class SeedSQLiteCacheTests(unittest.TestCase):
    def test_seed_copies_consistent_database_and_leaves_source_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "source.sqlite", root / "new" / "copy.sqlite"
            conn = sqlite3.connect(source)
            conn.execute("CREATE TABLE cache (request_hash TEXT, response TEXT)")
            conn.executemany("INSERT INTO cache VALUES (?, ?)", [("a", "one"), ("b", "two")])
            conn.commit()
            conn.close()
            original_hash = sha256_file(source)

            info = seed_sqlite_cache(source, destination)

            self.assertEqual(sha256_file(source), original_hash)
            self.assertEqual(info["source_sha256"], original_hash)
            self.assertEqual(info["copied_sha256"], sha256_file(destination))
            self.assertEqual(info["source_row_counts"], {"cache": 2})
            self.assertEqual(info["sqlite_row_counts"], {"cache": 2})
            copied = sqlite3.connect(destination)
            try:
                self.assertEqual(copied.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                copied.close()

    def test_seed_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "source.sqlite", root / "copy.sqlite"
            sqlite3.connect(source).close()
            destination.write_bytes(b"keep")
            with self.assertRaisesRegex(ValueError, "already exists"):
                seed_sqlite_cache(source, destination)
            self.assertEqual(destination.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
