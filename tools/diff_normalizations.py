"""Compare the semantic content of two canonical normalization runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.editorial_store import EditorialStore  # noqa: E402


def markdown(report):
    summary = report["summary"]
    lines = [
        "# Canonical import diff",
        "",
        f"- Base run: `{report['base_run']['id']}`",
        f"- Target run: `{report['target_run']['id']}`",
        "",
        "| Change | Count |",
        "| --- | ---: |",
    ]
    labels = {
        "people_added": "People added",
        "people_removed": "People removed",
        "people_reused": "Stable people reused",
        "privacy_changes": "Privacy changes",
        "claims_changed": "Claims changed",
        "claims_added": "Claims added",
        "claims_removed": "Claims removed",
        "relationships_added": "Relationships added",
        "relationships_removed": "Relationships removed",
    }
    lines.extend(
        f"| {labels[key]} | {summary[key]} |" for key in labels
    )
    if report["details"]["privacy_changes"]:
        lines.extend(["", "## Privacy changes", ""])
        lines.extend(
            f"- {item['name']}: {item['before']} → {item['after']}"
            for item in report["details"]["privacy_changes"]
        )
    if report["details"]["claims_changed"]:
        lines.extend(["", "## Changed claims", ""])
        lines.extend(
            f"- `{item['person_id']}` {item['claim_type']}: "
            f"{item['before']} → {item['after']}"
            for item in report["details"]["claims_changed"]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_run_id")
    parser.add_argument("target_run_id")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument(
        "--database", type=Path,
        default=PROJECT_ROOT / "data" / "editorial.sqlite3",
    )
    args = parser.parse_args()
    report = EditorialStore(args.database).compare_normalization_runs(
        args.base_run_id, args.target_run_id
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else markdown(report))


if __name__ == "__main__":
    main()
