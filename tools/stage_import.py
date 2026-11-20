"""Stage a GEDCOM and its validation report in the immutable import database."""

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.import_store import ImportStore  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gedcom", type=Path)
    parser.add_argument("--database", type=Path,
                        default=PROJECT_ROOT / "data" / "editorial.sqlite3")
    args = parser.parse_args()
    result = ImportStore(args.database).stage(args.gedcom)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
