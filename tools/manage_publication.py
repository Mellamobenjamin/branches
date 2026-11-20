"""Inspect, publish, or roll back canonical releases."""

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
        "--database", type=Path,
        default=PROJECT_ROOT / "data" / "editorial.sqlite3",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    publish = subparsers.add_parser("publish")
    publish.add_argument("run_id")
    publish.add_argument("--reviewer", required=True)
    publish.add_argument("--rationale", required=True)
    review = subparsers.add_parser("review")
    review.add_argument("run_id")
    review.add_argument("decision", choices=("approved", "rejected"))
    review.add_argument("--reviewer", required=True)
    review.add_argument("--rationale", required=True)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("release_id")
    rollback.add_argument("--reviewer", required=True)
    rollback.add_argument("--rationale", required=True)
    args = parser.parse_args()
    store = EditorialStore(args.database)
    if args.command == "status":
        result = store.current_release()
    elif args.command == "review":
        result = store.record_normalization_approval(
            args.run_id, args.decision, args.reviewer, args.rationale
        )
    elif args.command == "publish":
        result = store.publish_normalization(
            args.run_id, args.reviewer, args.rationale
        )
    else:
        result = store.rollback_to_release(
            args.release_id, args.reviewer, args.rationale
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
