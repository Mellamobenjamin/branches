"""Validate and import public name forms from the curated CSV."""
import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.editorial_store import EditorialStore
from app.genealogy import GedcomRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path, default=PROJECT_ROOT / 'data/curated/names.csv')
    parser.add_argument('--gedcom', type=Path, default=PROJECT_ROOT / 'data/family-tree.ged')
    parser.add_argument('--database', type=Path, default=PROJECT_ROOT / 'data/editorial.sqlite3')
    args = parser.parse_args()
    try:
        result = EditorialStore(args.database).import_names(args.path, GedcomRepository(args.gedcom))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
