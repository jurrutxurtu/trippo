"""The normalized observation -- the abstraction that makes the pipeline source-agnostic.

Every source (timeline, GPX, media, manual) is reduced to these before any reasoning
happens. The draft builder never asks which source produced an observation. ADR-0005.

`lat` and `lon` are OPTIONAL and frequently absent: all 1,097 photos in the reference
dataset had no GPS (pathology P6). Code consuming observations must handle that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ObservationKind(StrEnum):
    VISIT = "visit"  # stationary period asserted by a provider
    MOVE = "move"  # movement segment asserted by a provider
    BREADCRUMB = "breadcrumb"  # a raw position fix; never creates an event (ADR-0009)
    MEDIA = "media"  # a photo or video was taken at this instant
    TRACKPOINT = "trackpoint"  # a GPX point


@dataclass(slots=True)
class NormalizedObservation:
    t: datetime  # always timezone-aware
    kind: ObservationKind
    source_id: str
    lat: float | None = None
    lon: float | None = None
    end_t: datetime | None = None  # for visit and move
    end_lat: float | None = None
    end_lon: float | None = None
    utc_offset_minutes: int | None = None
    ref: str | None = None  # media id, segment index, trackpoint index
    #: Provider hints. NEVER treated as truth -- see pathology P2.
    hints: dict[str, object] = field(default_factory=dict)

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def duration_s(self) -> float:
        return (self.end_t - self.t).total_seconds() if self.end_t else 0.0

    @property
    def coord(self) -> tuple[float, float] | None:
        if self.lat is None or self.lon is None:
            return None
        return (self.lat, self.lon)

    @property
    def end_coord(self) -> tuple[float, float] | None:
        if self.end_lat is None or self.end_lon is None:
            return None
        return (self.end_lat, self.end_lon)
