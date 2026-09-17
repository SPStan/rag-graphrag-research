"""Create local service credentials once; never overwrite an existing .env."""

import json
from pathlib import Path
import re
import secrets


ROOT = Path(__file__).resolve().parents[1]
IMAGE_VARIABLES = {
    "docker.langfuse.com/langfuse/langfuse:4": "LANGFUSE_WEB_IMAGE",
    "docker.langfuse.com/langfuse/langfuse-worker:4": "LANGFUSE_WORKER_IMAGE",
    "docker.io/clickhouse/clickhouse-server:25.12": "CLICKHOUSE_IMAGE",
    "cgr.dev/chainguard/minio:latest": "MINIO_IMAGE",
    "docker.io/redis:7": "REDIS_IMAGE",
    "docker.io/postgres:17": "POSTGRES_IMAGE",
}
SECRET_VARIABLES = (
    "POSTGRES_PASSWORD",
    "CLICKHOUSE_PASSWORD",
    "REDIS_PASSWORD",
    "MINIO_PASSWORD",
    "LANGFUSE_SALT",
    "LANGFUSE_ENCRYPTION_KEY",
    "LANGFUSE_AUTH_SECRET",
)


def main():
    env_path = ROOT / ".env"
    if env_path.exists():
        print("Existing .env preserved; no credentials changed.")
        return
    entries = json.loads(
        (ROOT / "infra/langfuse/images.lock.json").read_text(encoding="utf-8-sig")
    )
    images = {entry["image"]: entry for entry in entries}
    lines = ["# Generated locally. Keep this file private and back it up."]
    for image, variable in IMAGE_VARIABLES.items():
        digest = images.get(image, {}).get("digest", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise SystemExit(f"Missing valid locked digest for {image}")
        # The public Chainguard endpoint may reject digest-only pulls with 403.
        # Keep its observed digest in the lock file, but download by public tag.
        reference = image if variable == "MINIO_IMAGE" else f"{image}@{digest}"
        lines.append(f"{variable}={reference}")
    lines.append("")
    lines.extend(f"{name}={secrets.token_hex(32)}" for name in SECRET_VARIABLES)
    with env_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print("Created .env with image references and random service credentials.")
    print("Credentials were not printed. Existing data requires the same .env.")


if __name__ == "__main__":
    main()
