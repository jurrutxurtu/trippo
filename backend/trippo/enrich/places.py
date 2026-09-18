"""Google Places -- exact resolution of the place ids Google already gave us.

The on-device Timeline export contains no place *names*, but it does contain Google's own
`placeId` for every visit. That is a direct lookup, not a search: no ranking, no radius,
no ambiguity. Where Overpass guesses between fifteen nearby features and Nominatim answers
with a road number, Places answers with the name Google Maps itself would show.

It is therefore tried **first** when a key is configured -- and only for events that
actually carry a placeId, which is what keeps the cost bounded and predictable.

Paid, so off unless `GOOGLE_PLACES_API_KEY` is set. Everything degrades to the free
cascade without it (ADR-0008).
"""

from __future__ import annotations

import os

import httpx

from trippo.domain.models import PlaceSource
from trippo.ports.geocoder import PlaceCandidate

ENDPOINT = "https://places.googleapis.com/v1/places"
#: Only the fields we use. Places bills by field mask, so asking for less costs less.
FIELD_MASK = "displayName,formattedAddress,location,primaryType,types"

#: Google's place types mapped onto the OSM-style `key=value` the ranker understands, so
#: a Places result competes on the same terms as an Overpass one.
_TYPE_MAP: dict[str, str] = {
    "campground": "tourism=camp_site",
    "rv_park": "tourism=caravan_site",
    "lodging": "tourism=hotel",
    "hotel": "tourism=hotel",
    "guest_house": "tourism=guest_house",
    "hostel": "tourism=hostel",
    "museum": "tourism=museum",
    "tourist_attraction": "tourism=attraction",
    "historical_landmark": "historic=monument",
    "historical_place": "historic=monument",
    "church": "historic=church",
    "restaurant": "amenity=restaurant",
    "cafe": "amenity=cafe",
    "bar": "amenity=pub",
    "pub": "amenity=pub",
    "park": "leisure=park",
    "national_park": "leisure=nature_reserve",
    "hiking_area": "leisure=nature_reserve",
    "beach": "natural=beach",
    "parking": "amenity=parking",
    "ferry_terminal": "amenity=ferry_terminal",
    "airport": "aeroway=aerodrome",
}


class PlacesResolver:
    """Resolves a Google `placeId` to a name. Never raises; failures are degradations."""

    name = "google"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self._key = api_key if api_key is not None else os.environ.get(
            "GOOGLE_PLACES_API_KEY", ""
        )
        self._client = client or httpx.Client(timeout=15.0)
        self.failures = 0
        self.lookups = 0

    @property
    def available(self) -> bool:
        return bool(self._key)

    def resolve(self, place_id: str) -> PlaceCandidate | None:
        if not self.available or not place_id:
            return None
        self.lookups += 1
        try:
            r = self._client.get(
                f"{ENDPOINT}/{place_id}",
                headers={
                    "X-Goog-Api-Key": self._key,
                    "X-Goog-FieldMask": FIELD_MASK,
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

        display = (data.get("displayName") or {}).get("text")
        if not display:
            return None
        loc = data.get("location") or {}

        return PlaceCandidate(
            name=display,
            lat=loc.get("latitude"),
            lon=loc.get("longitude"),
            source=PlaceSource.GOOGLE,
            kind=_kind_of(data),
            address=data.get("formattedAddress"),
            osm_id=None,
            # A direct id lookup is exact: it is the same place, not a nearby one.
            distance_m=0.0,
            notable=True,
        )


def _kind_of(data: dict) -> str | None:
    primary = data.get("primaryType")
    if primary and primary in _TYPE_MAP:
        return _TYPE_MAP[primary]
    for t in data.get("types", []):
        if t in _TYPE_MAP:
            return _TYPE_MAP[t]
    return f"google={primary}" if primary else None


def resolver_from_env() -> PlacesResolver | None:
    """A resolver when a key exists, otherwise None and the free cascade is used."""
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    return PlacesResolver(key) if key else None
