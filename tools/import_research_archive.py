"""Import the private accession register into the editorial SQLite layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.editorial_store import EditorialStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register",
        type=Path,
        default=PROJECT_ROOT / "data" / "research_archive" / "accession-register.json",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "editorial.sqlite3",
    )
    args = parser.parse_args()
    store = EditorialStore(args.database)
    result = store.import_accession_register(args.register)
    print(json.dumps({**result, "counts": store.counts()}, indent=2))


if __name__ == "__main__":
    main()
