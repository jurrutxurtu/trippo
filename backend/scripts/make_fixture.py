"""Generate the redacted golden fixture from a real export.

Run manually when the fixture needs regenerating:

    python scripts/make_fixture.py --timeline <export.json> --gpx <folder> \
        --out ../fixtures/golden/ireland-2023

Coordinates are offset by a fixed delta and track points are thinned, so the fixture
preserves every structural pathology (docs/technical/ingestion.md) without publishing
anyone's real movements. The offset is constant, so distances and speeds -- and therefore
every heuristic under test -- are unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

LAT_OFFSET = 1.5
LON_OFFSET = -2.25
THIN = 12  # keep 1 trackpoint in N

_LATLNG = re.compile(r"(-?\d+\.\d+)\D+?(-?\d+\.\d+)")


def shift_latlng(value: str) -> str:
    m = _LATLNG.search(value)
    if not m:
        return value
    lat = float(m.group(1)) + LAT_OFFSET
    lon = float(m.group(2)) + LON_OFFSET
    return f"{lat:.7f}\u00b0, {lon:.7f}\u00b0"


def walk(node):
    if isinstance(node, dict):
        return {
            k: (shift_latlng(v) if k in {"latLng", "point"} and isinstance(v, str) else walk(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [walk(v) for v in node]
    return node


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--gpx", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--from", dest="start", default="2023-09-20")
    ap.add_argument("--to", dest="end", default="2023-10-17")
    a = ap.parse_args()

    out = Path(a.out)
    (out / "tracks").mkdir(parents=True, exist_ok=True)

    payload = json.loads(Path(a.timeline).read_text(encoding="utf-8", errors="replace"))
    segs = [
        s
        for s in payload.get("semanticSegments", [])
        if a.start <= str(s.get("startTime", ""))[:10] <= a.end
    ]
    (out / "timeline.json").write_text(
        json.dumps({"semanticSegments": walk(segs)}, indent=1), encoding="utf-8"
    )
    print(f"timeline: {len(segs)} segments -> {out / 'timeline.json'}")

    gpx_root = Path(a.gpx)
    files = sorted(gpx_root.rglob("*.gpx")) if gpx_root.is_dir() else [gpx_root]
    for f in files:
        tree = ET.parse(f)
        root = tree.getroot()
        for seg in [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "trkseg"]:
            pts = [c for c in list(seg) if c.tag.rsplit("}", 1)[-1] == "trkpt"]
            for i, p in enumerate(pts):
                if i % THIN and i != len(pts) - 1:
                    seg.remove(p)
                    continue
                p.set("lat", f"{float(p.get('lat', 0)) + LAT_OFFSET:.6f}")
                p.set("lon", f"{float(p.get('lon', 0)) + LON_OFFSET:.6f}")
        tree.write(out / "tracks" / f.name, encoding="utf-8", xml_declaration=True)
    print(f"gpx: {len(files)} file(s) thinned 1:{THIN} -> {out / 'tracks'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
