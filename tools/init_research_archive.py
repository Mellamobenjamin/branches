"""Create the private, Git-ignored research archive directory structure."""

from __future__ import annotations

import argparse
from pathlib import Path


ARCHIVE_FOLDERS = (
    "inbox",
    "originals",
    "derivatives",
    "transcripts",
    "exports",
)


def initialize_archive(root: Path) -> list[Path]:
    created = []
    for folder in ARCHIVE_FOLDERS:
        path = root / folder
        if not path.exists():
            path.mkdir(parents=True)
            created.append(path)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the private research archive folders."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/research_archive"),
        help="archive root (default: data/research_archive)",
    )
    args = parser.parse_args()
    created = initialize_archive(args.root)
    if created:
        print("Created:")
        for path in created:
            print(f"  {path}")
    else:
        print(f"Archive already initialized at {args.root}")


if __name__ == "__main__":
    main()
