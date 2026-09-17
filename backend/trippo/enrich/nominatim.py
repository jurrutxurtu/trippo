"""Nominatim provider -- address and administrative context.

Second in the cascade. It reliably answers "where is this?" but rarely "what is this?":
at Glendalough it returns `R757`, a road number. Its real value here is the admin
hierarchy -- town, county, country -- which gives every event a readable fallback label
and supplies the `countries` trip statistic.

Hard constraints from the usage policy: one request per second, and a genuine
`User-Agent`. Both are enforced here rather than trusted to callers.
"""

from __future__ import annotations

import time

import httpx

from trippo.config.heuristics import NOMINATIM_MIN_INTERVAL_S, NOMINATIM_URL
from trippo.domain.models import PlaceSource
from trippo.ports.geocoder import GeocodeQuery, PlaceCandidate

#: Address fields that make a decent place label, most specific first.
_NAME_FIELDS = (
    "attraction",
    "tourism",
    "historic",
    "natural",
    "peak",
    "building",
    "amenity",
    "hamlet",
    "village",
    "town",
    "suburb",
    "city",
    "municipality",
    "county",
)


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, client: httpx.Client | None = None, url: str = NOMINATIM_URL) -> None:
        self._client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": "trippo/0.1 (personal travel studio; local use)"},
        )
        self._url = url
        self._last_call = 0.0
        self.failures = 0

    def lookup(self, queries: list[GeocodeQuery]) -> dict[int, list[PlaceCandidate]]:
        out: dict[int, list[PlaceCandidate]] = {}
        for i, q in enumerate(queries):
            cand = self._one(q)
            out[i] = [cand] if cand else []
        return out

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < NOMINATIM_MIN_INTERVAL_S:
            time.sleep(NOMINATIM_MIN_INTERVAL_S - elapsed)
        self._last_call = time.monotonic()

    def _one(self, q: GeocodeQuery) -> PlaceCandidate | None:
        self._throttle()
        try:
            r = self._client.get(
                self._url,
                params={
                    "lat": q.lat,
                    "lon": q.lon,
                    "format": "jsonv2",
                    "zoom": 17,
                    "addressdetails": 1,
                },
            )
        except (httpx.HTTPError, OSError):
            self.failures += 1
            return None
        if r.status_code != 200:
            self.failures += 1
            return None
        try:
            data = r.json()
        except ValueError:
            self.failures += 1
            return None
        if not isinstance(data, dict) or "error" in data:
            return None

        addr = data.get("address") or {}
        name = data.get("name") or _best_name(addr) or data.get("display_name", "").split(",")[0]
        if not name:
            return None

        return PlaceCandidate(
            name=name,
            lat=_f(data.get("lat")),
            lon=_f(data.get("lon")),
            source=PlaceSource.NOMINATIM,
            kind=f"{data.get('category')}={data.get('type')}"
            if data.get("category")
            else None,
            osm_id=f"{data.get('osm_type')}/{data.get('osm_id')}"
            if data.get("osm_id")
            else None,
            address=data.get("display_name"),
            locality=_locality(addr),
            country=addr.get("country"),
            distance_m=0.0,
        )


def _f(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _best_name(addr: dict) -> str | None:
    for field in _NAME_FIELDS:
        if addr.get(field):
            return str(addr[field])
    return None


def _locality(addr: dict) -> str | None:
    for field in ("village", "town", "city", "municipality", "county", "state"):
        if addr.get(field):
            return str(addr[field])
    return None
