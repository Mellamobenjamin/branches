"""Normalize a staged GEDCOM into canonical editorial records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.import_store import ImportStore  # noqa: E402
from app.normalization import CanonicalNormalizer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "gedcom", type=Path,
        nargs="?", default=PROJECT_ROOT / "data" / "family-tree.ged",
    )
    parser.add_argument("--import-id")
    parser.add_argument(
        "--database", type=Path,
        default=PROJECT_ROOT / "data" / "editorial.sqlite3",
    )
    args = parser.parse_args()
    store = ImportStore(args.database)
    import_id = args.import_id
    if not import_id:
        imports = store.list_imports()
        if not imports:
            raise SystemExit("No staged imports found; run tools/stage_import.py first")
        import_id = imports[0]["id"]
    result = CanonicalNormalizer(args.database).normalize(import_id, args.gedcom)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
