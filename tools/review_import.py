"""List or adjudicate findings from the latest validation run."""

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.import_store import ImportStore  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path,
                        default=PROJECT_ROOT / "data" / "editorial.sqlite3")
    subparsers = parser.add_subparsers(dest="command", required=True)
    listing = subparsers.add_parser("list")
    listing.add_argument("import_id")
    decide = subparsers.add_parser("decide")
    decide.add_argument("import_id")
    decide.add_argument("fingerprint")
    decide.add_argument("decision", choices=(
        "accepted", "false_positive", "corrected_upstream", "superseded"
    ))
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--rationale", required=True)
    args = parser.parse_args()

    store = ImportStore(args.database)
    if args.command == "list":
        result = store.review_queue(args.import_id)
    else:
        result = store.record_decision(
            args.import_id, args.fingerprint, args.decision,
            args.rationale, args.reviewer,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
