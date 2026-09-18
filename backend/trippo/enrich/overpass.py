"""Overpass provider -- "what is actually here?".

Tried before Nominatim because for a travel app a POI beats an address. Measured on real
coordinates at Glendalough:

    Nominatim  ->  "R757"                      (a regional road number)
    Overpass   ->  "Glendalough", "Glendalough Round Tower",
                   "Saint Kevin's Church", "Lower Lake", ...

Batching, measured against the public instance:

    6 points, nodes only    ->  200,  9.3 s, 120 features
    6 points, nodes + ways  ->  504
    3 points, nodes + ways  ->  504
    1 point,  nodes + ways  ->  200

So: batch nodes, and fall back to single-point queries including ways only for points
that got nothing. `way` elements carry lakes, large sites and many churches, so the
fallback is worth having -- it is just too heavy to batch.
"""

from __future__ import annotations

import time

import httpx

from trippo.config.heuristics import (
    OVERPASS_BATCH_SIZE,
    OVERPASS_CLIENT_TIMEOUT_S,
    OVERPASS_ENDPOINTS,
    OVERPASS_MAX_FEATURES,
    OVERPASS_TIMEOUT_S,
)
from trippo.domain.geo import haversine_m
from trippo.domain.models import PlaceSource
from trippo.ports.geocoder import GeocodeQuery, PlaceCandidate

#: OSM keys worth a traveller's attention, in rough order of interest.
POI_KEYS = ("tourism", "historic", "natural", "leisure", "amenity", "place", "waterway")
#: Keys cheap enough to batch. `amenity` is huge in cities and blows the timeout.
BATCH_KEYS = ("tourism", "historic", "natural", "place")


class OverpassGeocoder:
    name = "overpass"

    def __init__(self, client: httpx.Client | None = None, endpoints=None) -> None:
        self._client = client or httpx.Client(
            timeout=OVERPASS_CLIENT_TIMEOUT_S,
            headers={"User-Agent": "trippo/0.1 (personal)"},
        )
        self._endpoints = list(endpoints or OVERPASS_ENDPOINTS)
        #: Mirrors that have already failed this run, in failure order. A mirror that just
        #: timed out will almost certainly time out again, and re-trying it first on every
        #: batch is how one bad mirror turns a ten-minute import into an hour.
        self._demoted: list[str] = []
        self.failures = 0

    def _ordered(self) -> list[str]:
        healthy = [e for e in self._endpoints if e not in self._demoted]
        return healthy + self._demoted

    def _demote(self, endpoint: str) -> None:
        if endpoint in self._demoted:
            return
        # Never demote the last healthy mirror -- something has to be tried.
        if len([e for e in self._endpoints if e not in self._demoted]) > 1:
            self._demoted.append(endpoint)

    def lookup(self, queries: list[GeocodeQuery]) -> dict[int, list[PlaceCandidate]]:
        out: dict[int, list[PlaceCandidate]] = {}
        for start in range(0, len(queries), OVERPASS_BATCH_SIZE):
            chunk = list(enumerate(queries))[start : start + OVERPASS_BATCH_SIZE]
            elements = self._run(self._build(q for _, q in chunk), ways=False)
            for idx, q in chunk:
                out[idx] = self._assign(elements, q)
        return out

    def lookup_single_deep(self, query: GeocodeQuery) -> list[PlaceCandidate]:
        """Single point including `way` elements. Only for points a batch missed."""
        elements = self._run(self._build([query], ways=True, keys=POI_KEYS), ways=True)
        return self._assign(elements, query)

    # ------------------------------------------------------------------ internals

    def _build(self, queries, ways: bool = False, keys=BATCH_KEYS) -> str:
        parts: list[str] = []
        for q in queries:
            radius = int(q.radius_m)
            for key in keys:
                parts.append(f"node(around:{radius},{q.lat:.6f},{q.lon:.6f})[name][{key}];")
                if ways:
                    parts.append(f"way(around:{radius},{q.lat:.6f},{q.lon:.6f})[name][{key}];")
        return (
            f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];"
            f"({''.join(parts)});out tags center {OVERPASS_MAX_FEATURES};"
        )

    def _run(self, query: str, ways: bool) -> list[dict]:
        """Try each mirror in turn. Returns [] on total failure -- never raises."""
        for endpoint in self._ordered():
            try:
                r = self._client.post(endpoint, data={"data": query})
            except (httpx.HTTPError, OSError):
                # A timeout or refused connection means this mirror is unwell right now.
                self.failures += 1
                self._demote(endpoint)
                continue
            if r.status_code == 200:
                try:
                    return r.json().get("elements", [])
                except ValueError:
                    self.failures += 1
                    continue
            # 429 = rate limited, 504 = query too heavy. Both mean "back off", but only
            # rate limiting says anything about the mirror itself.
            self.failures += 1
            if r.status_code == 429:
                self._demote(endpoint)
                time.sleep(2.0)
        return []

    def _assign(self, elements: list[dict], q: GeocodeQuery) -> list[PlaceCandidate]:
        """Attribute features to a query point by distance.

        A batched union returns one flat list for every point in the chunk, so each
        feature has to be re-associated with the point it belongs to.
        """
        out: list[PlaceCandidate] = []
        seen: set[str] = set()
        for el in elements:
            tags = el.get("tags") or {}
            name = tags.get("name")
            if not name:
                continue
            lat, lon = _coords_of(el)
            if lat is None or lon is None:
                continue
            dist = haversine_m((q.lat, q.lon), (lat, lon))
            if dist > q.radius_m:
                continue
            key = f"{name}|{round(lat, 5)}"
            if key in seen:
                continue
            seen.add(key)
            out.append(
                PlaceCandidate(
                    name=name,
                    lat=lat,
                    lon=lon,
                    source=PlaceSource.OSM,
                    kind=_primary_tag(tags),
                    osm_id=f"{el.get('type')}/{el.get('id')}",
                    notable=bool(
                        tags.get("wikidata") or tags.get("wikipedia") or tags.get("heritage")
                    ),
                    distance_m=round(dist, 1),
                )
            )
        out.sort(key=lambda c: c.distance_m or 0.0)
        return out


def _coords_of(el: dict) -> tuple[float | None, float | None]:
    if "lat" in el and "lon" in el:
        return (el["lat"], el["lon"])
    centre = el.get("center") or {}
    return (centre.get("lat"), centre.get("lon"))


def _primary_tag(tags: dict) -> str | None:
    for key in POI_KEYS:
        if key in tags:
            return f"{key}={tags[key]}"
    return None
