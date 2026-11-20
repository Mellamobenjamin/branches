"""Generate a deterministic GEDCOM validation report.

Examples:
    python tools/audit_genealogy.py data/family-tree.ged
    python tools/audit_genealogy.py data/family-tree.ged --format json
"""

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.genealogy import GedcomRepository  # noqa: E402
from app.validation import validate_repository  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Audit a GEDCOM without modifying it.")
    parser.add_argument("gedcom", type=Path)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    report = validate_repository(GedcomRepository(args.gedcom, show_living=True))
    rendered = report.to_json() if args.format == "json" else report.to_markdown()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 1 if args.fail_on_error and not report.publishable else 0


if __name__ == "__main__":
    raise SystemExit(main())
