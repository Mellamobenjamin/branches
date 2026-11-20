"""Verify private research artifacts against the accession register."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(register_path: Path, originals_root: Path) -> list[str]:
    register = json.loads(register_path.read_text(encoding="utf-8"))
    problems = []
    seen_ids = set()
    seen_hashes = set()
    for artifact in register["artifacts"]:
        artifact_id = artifact["artifact_id"]
        if artifact_id in seen_ids:
            problems.append(f"duplicate artifact ID: {artifact_id}")
        seen_ids.add(artifact_id)
        expected_hash = artifact["sha256"].lower()
        if expected_hash in seen_hashes:
            problems.append(f"duplicate payload checksum: {artifact_id}")
        seen_hashes.add(expected_hash)
        path = originals_root / artifact_id / artifact["original_filename"]
        if not path.is_file():
            problems.append(f"missing file: {path}")
            continue
        if path.stat().st_size != artifact["byte_size"]:
            problems.append(f"size mismatch: {artifact_id}")
        if sha256(path) != expected_hash:
            problems.append(f"checksum mismatch: {artifact_id}")
        for alternate in artifact.get("alternate_files", []):
            alternate_hash = alternate["sha256"].lower()
            if alternate_hash in seen_hashes:
                problems.append(f"duplicate payload checksum: {artifact_id}/{alternate['filename']}")
            seen_hashes.add(alternate_hash)
            alternate_path = originals_root / artifact_id / alternate["filename"]
            if not alternate_path.is_file():
                problems.append(f"missing file: {alternate_path}")
                continue
            if alternate_path.stat().st_size != alternate["byte_size"]:
                problems.append(f"size mismatch: {artifact_id}/{alternate['filename']}")
            if sha256(alternate_path) != alternate_hash:
                problems.append(f"checksum mismatch: {artifact_id}/{alternate['filename']}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register",
        type=Path,
        default=Path("data/research_archive/accession-register.json"),
    )
    parser.add_argument(
        "--originals",
        type=Path,
        default=Path("data/research_archive/originals"),
    )
    args = parser.parse_args()
    problems = verify(args.register, args.originals)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        raise SystemExit(1)
    register = json.loads(args.register.read_text(encoding="utf-8"))
    print(f"Verified {len(register['artifacts'])} artifacts with unique checksums.")


if __name__ == "__main__":
    main()
