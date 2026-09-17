"""Summits, passes and lakes along a track.

"Slieve Donard, 850 m, 5.6 km in" is the single most useful sentence about a hike, and
neither the GPX nor the timeline contains it. The GPX knows the shape of the walk; OSM
knows what the shape went over.

One Overpass query per track, over the track's bounding box, then filtered by distance to
the line itself. Querying the bbox once is far cheaper than sampling the route -- a
3,000-point track covers a small area, and the filtering is local arithmetic.

Distance thresholds differ by feature, because they mean different things:

* a **summit** you stand on -- tens of metres, allowing for GPS drift
* a **pass or saddle** you walk through -- similar
* a **lake** you walk beside -- hundreds of metres, since the tagged centre of a lake may
  be far from its shore
"""

from __future__ import annotations

import httpx

from trippo.config.heuristics import (
    OVERPASS_ENDPOINTS,
    OVERPASS_TIMEOUT_S,
    PEAK_MAX_DIST_M,
    WATER_MAX_DIST_M,
)
from trippo.domain.geo import Coord, bbox, distance_to_path, offset_along_path, pad_bbox
from trippo.domain.models import TrackHighlight

#: (overpass filter, canonical kind, max distance from the line)
_FEATURES: tuple[tuple[str, str, float], ...] = (
    ('node["natural"="peak"]["name"]', "natural=peak", PEAK_MAX_DIST_M),
    ('node["natural"="saddle"]["name"]', "natural=saddle", PEAK_MAX_DIST_M),
    ('node["mountain_pass"="yes"]["name"]', "mountain_pass=yes", PEAK_MAX_DIST_M),
    ('node["natural"="water"]["name"]', "natural=water", WATER_MAX_DIST_M),
    ('way["natural"="water"]["name"]', "natural=water", WATER_MAX_DIST_M),
)


class PeakFinder:
    def __init__(self, client: httpx.Client | None = None, endpoints=None) -> None:
        self._client = client or httpx.Client(
            timeout=OVERPASS_TIMEOUT_S, headers={"User-Agent": "trippo/0.1 (personal)"}
        )
        self._endpoints = list(endpoints or OVERPASS_ENDPOINTS)
        self.failures = 0

    def find(
        self, path: list[Coord], elevations: list[float | None] | None = None
    ) -> list[TrackHighlight]:
        """Named features the route passed, ordered by distance along it."""
        if len(path) < 2:
            return []

        elements = self._query(pad_bbox(bbox(path), 500.0))
        if not elements:
            return []

        out: list[TrackHighlight] = []
        seen: set[str] = set()
        for el in elements:
            tags = el.get("tags") or {}
            name = tags.get("name")
            lat, lon = _coords_of(el)
            if not name or lat is None or lon is None:
                continue

            kind = _kind_of(tags)
            limit = next((lim for _f, k, lim in _FEATURES if k == kind), PEAK_MAX_DIST_M)
            dist = distance_to_path((lat, lon), path)
            if dist > limit:
                continue

            key = f"{name}|{kind}"
            if key in seen:
                continue
            seen.add(key)

            offset = offset_along_path((lat, lon), path)
            out.append(
                TrackHighlight(
                    name=name,
                    kind=kind,
                    lat=lat,
                    lon=lon,
                    ele_m=_elevation(tags, (lat, lon), path, elevations),
                    offset_m=round(offset, 1),
                    distance_from_track_m=round(dist, 1),
                    osm_id=f"{el.get('type')}/{el.get('id')}",
                )
            )

        out.sort(key=lambda h: h.offset_m)
        return out

    # ------------------------------------------------------------------ internals

    def _query(self, box: tuple[float, float, float, float]) -> list[dict]:
        south, west, north, east = box
        area = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
        body = "".join(f"{f}({area});" for f, _k, _d in _FEATURES)
        query = (
            f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];({body});out tags center 200;"
        )
        for endpoint in self._endpoints:
            try:
                r = self._client.post(endpoint, data={"data": query})
            except (httpx.HTTPError, OSError):
                self.failures += 1
                continue
            if r.status_code == 200:
                try:
                    return r.json().get("elements", [])
                except ValueError:
                    self.failures += 1
                    continue
            self.failures += 1
        return []


def _coords_of(el: dict) -> tuple[float | None, float | None]:
    if "lat" in el and "lon" in el:
        return (el["lat"], el["lon"])
    centre = el.get("center") or {}
    return (centre.get("lat"), centre.get("lon"))


def _kind_of(tags: dict) -> str:
    if tags.get("mountain_pass") == "yes":
        return "mountain_pass=yes"
    if "natural" in tags:
        return f"natural={tags['natural']}"
    return "unknown"


def _elevation(
    tags: dict,
    point: Coord,
    path: list[Coord],
    elevations: list[float | None] | None,
) -> float | None:
    """OSM's surveyed height where it exists, else the track's own altitude there.

    OSM `ele` is authoritative for a summit; a barometric GPX reading is a decent
    substitute and better than nothing.
    """
    raw = tags.get("ele")
    if raw:
        try:
            return round(float(str(raw).split()[0]), 1)
        except (ValueError, IndexError):
            pass

    if not elevations or len(elevations) != len(path):
        return None
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(path):
        d = (p[0] - point[0]) ** 2 + (p[1] - point[1]) ** 2
        if d < best_d:
            best_i, best_d = i, d
    ele = elevations[best_i]
    return round(ele, 1) if ele is not None else None
