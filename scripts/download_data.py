"""Download pinned public HippoRAG data using only the Python standard library."""

import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def verify(payload, entry):
    if len(payload) != entry["size"]:
        raise ValueError(f"Size mismatch: {entry['name']}")
    sha256 = hashlib.sha256(payload).hexdigest()
    if entry.get("sha256") and sha256 != entry["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {entry['name']}")
    if entry.get("git_blob_sha1"):
        header = f"blob {len(payload)}\0".encode("ascii")
        blob = hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()
        if blob != entry["git_blob_sha1"]:
            raise ValueError(f"Git blob mismatch: {entry['name']}")
    if not entry.get("sha256") and not entry.get("git_blob_sha1"):
        raise ValueError("Source checksum is required")
    if not isinstance(json.loads(payload), list):
        raise ValueError(f"Expected a JSON list: {entry['name']}")
    return sha256


def main():
    lock = json.loads((ROOT / "data/sources.lock.json").read_text(encoding="utf-8"))
    folder = ROOT / "data/raw"
    folder.mkdir(parents=True, exist_ok=True)
    for entry in lock["files"]:
        name = entry["name"]
        if Path(name).name != name or not name.endswith(".json"):
            raise ValueError("Invalid source filename")
        path = folder / name
        if path.exists():
            digest = verify(path.read_bytes(), entry)
            print(f"Verified cached {name}: sha256={digest}", flush=True)
            continue
        url = f"https://huggingface.co/datasets/{lock['repository']}/resolve/{lock['revision']}/{name}"
        print(f"Downloading {name} ({entry['size']} bytes)...", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "rag-graphrag-research/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read(entry["size"] + 1)
        digest = verify(payload, entry)
        temporary = path.with_suffix(".json.part")
        temporary.write_bytes(payload)
        temporary.replace(path)
        print(f"Verified {name}: sha256={digest}", flush=True)


if __name__ == "__main__":
    main()
