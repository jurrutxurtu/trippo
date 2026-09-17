"""Geocoder port and the candidate model shared by every provider. ADR-0008.

The on-device Google export contains no place names, so this is core functionality rather
than enrichment: without it the curation screen is a list of latitudes.

Providers return *candidates*; they never decide. Selection happens in `enrich/rank.py`,
which knows the event's type, duration and media -- context no geocoder has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from trippo.domain.models import PlaceSource


@dataclass(slots=True)
class PlaceCandidate:
    """One possible answer to "what is this place?"."""

    name: str
    lat: float | None = None
    lon: float | None = None
    source: PlaceSource = PlaceSource.OSM
    #: OSM primary tag, e.g. ``natural=peak``, ``tourism=camp_site``.
    kind: str | None = None
    osm_id: str | None = None
    address: str | None = None
    #: Administrative context: city, county, country.
    locality: str | None = None
    country: str | None = None
    #: True when OSM carries a wikidata/wikipedia/heritage tag -- a cheap, reliable
    #: proxy for "this is a real destination" rather than a plaque or a signboard.
    notable: bool = False
    #: Metres from the query point. None when the provider gave no geometry.
    distance_m: float | None = None
    raw: dict = field(default_factory=dict)

    @property
    def tag_key(self) -> str:
        return (self.kind or "").split("=")[0]

    @property
    def tag_value(self) -> str:
        parts = (self.kind or "").split("=", 1)
        return parts[1] if len(parts) > 1 else ""


@dataclass(slots=True)
class GeocodeQuery:
    """A request for candidates around a point.

    `radius_m` is widened by the caller for events whose own position is weak -- one
    derived from photos that were themselves interpolated may be hundreds of metres out.
    """

    lat: float
    lon: float
    radius_m: float
    #: Free-form label used only for logging and progress reporting.
    label: str = ""


@runtime_checkable
class Geocoder(Protocol):
    name: str

    def lookup(self, queries: list[GeocodeQuery]) -> dict[int, list[PlaceCandidate]]:
        """Resolve a batch of queries.

        Returns a mapping of *query index* to candidates. A provider that fails, times
        out or is blocked returns partial results or `{}` -- never raises. Network
        failure is a degradation, not an error (AGENTS.md section 5).
        """
        ...
