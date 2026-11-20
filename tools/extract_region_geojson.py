"""Extract one state/province outline for the home map from Natural Earth.

Download Natural Earth's 1:50m "Admin 1 – States, Provinces" GeoJSON, then:

    python tools/extract_region_geojson.py ne_50m_admin_1_states_provinces.geojson Minnesota

and set HOME_REGION["outline"] = "/static/data/home-region.geojson" in your
site profile.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="Natural Earth admin-1 GeoJSON")
    parser.add_argument("name", help='feature name, e.g. "Minnesota"')
    parser.add_argument(
        "--out", type=Path,
        default=Path(__file__).resolve().parent.parent / "app" / "static" / "data" / "home-region.geojson",
    )
    args = parser.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8"))
    features = [feature for feature in data["features"] if feature["properties"].get("name") == args.name]
    if len(features) != 1:
        raise SystemExit(f"Expected one {args.name!r} feature, found {len(features)}")
    args.out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {args.out} ({args.out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
