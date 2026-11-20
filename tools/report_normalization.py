"""Report canonical normalization and publication status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.editorial_store import EditorialStore  # noqa: E402


def markdown(report):
    run = report["run"]
    rows = [
        "# Canonical normalization report",
        "",
        f"- Run: `{run['id']}`",
        f"- Import: `{run['import_id']}`",
        f"- Status: **{run['status']}**",
        f"- Publication: **{run['publication_status']}**",
        f"- Blocker: {run['blocked_reason'] or 'None'}",
        "",
        "## Normalized records",
        "",
        f"- People: {run['people_count']}",
        f"- Unions: {run['union_count']}",
        f"- Parent–child assertions: {run['relationship_count']}",
        f"- Fact claims: {run['claim_count']}",
        f"- Open identity candidates: {report['open_identity_candidates']}",
        f"- Missing preferred names: {report['missing_preferred_names']}",
        "",
        "## Identity matching",
        "",
    ]
    rows.extend(
        f"- {method.replace('_', ' ').title()}: {count}"
        for method, count in sorted(report["match_methods"].items())
    )
    rows.extend(["", "## Privacy", ""])
    rows.extend(
        f"- {status.title()}: {count}"
        for status, count in sorted(report["privacy"].items())
    )
    rows.extend(["", "## Evidence provenance", ""])
    rows.extend(
        f"- {classification.replace('_', ' ').title()}: {count} claims"
        for classification, count in report["evidence_classes"].items()
    )
    rows.append(f"- Record-level citations: {report['record_citation_count']}")
    rows.append(f"- Person-level citations: {report['person_citation_count']}")
    rows.extend(["", "## Active publication", ""])
    release = report["current_release"]
    rows.append(
        f"Release `{release['id']}` ({release['action']})."
        if release else "No canonical release has been published."
    )
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument(
        "--database", type=Path,
        default=PROJECT_ROOT / "data" / "editorial.sqlite3",
    )
    args = parser.parse_args()
    report = EditorialStore(args.database).normalization_report(args.run_id)
    if not report:
        raise SystemExit("No normalization runs found")
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else markdown(report))


if __name__ == "__main__":
    main()
