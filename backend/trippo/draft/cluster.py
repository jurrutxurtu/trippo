"""Time-and-space clustering of observations into candidate stops.

This is what makes photo-only trips work (ADR-0005). With no timeline export, a folder of
photos still yields day structure and event candidates.

IMPORTANT: positions are optional. All 1,097 photos in the reference dataset had no GPS
(pathology P6), so clustering must degrade cleanly to time-only. It does: the distance
test is simply skipped when either side lacks a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from trippo.config.heuristics import CLUSTER_DIST_M, CLUSTER_TIME_GAP_MIN
from trippo.domain.geo import centroid, haversine_m
from trippo.observe.models import NormalizedObservation, ObservationKind


@dataclass(slots=True)
class Cluster:
    start: datetime
    end: datetime
    observations: list[NormalizedObservation] = field(default_factory=list)
    positioned: bool = False

    @property
    def coord(self) -> tuple[float, float] | None:
        pts = [o.coord for o in self.observations if o.has_position]
        return centroid([p for p in pts if p]) if pts else None  # type: ignore[arg-type]

    @property
    def media_refs(self) -> list[str]:
        return [
            o.ref
            for o in self.observations
            if o.kind is ObservationKind.MEDIA and o.ref is not None
        ]

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()


def cluster_media(observations: list[NormalizedObservation]) -> list[Cluster]:
    """Group media observations into candidate stops by time gap and displacement."""
    media = sorted((o for o in observations if o.kind is ObservationKind.MEDIA), key=lambda o: o.t)
    if not media:
        return []

    clusters: list[Cluster] = []
    current = Cluster(start=media[0].t, end=media[0].t, observations=[media[0]])

    for o in media[1:]:
        if _breaks(current, o):
            clusters.append(current)
            current = Cluster(start=o.t, end=o.t, observations=[o])
        else:
            current.observations.append(o)
            current.end = o.t

    clusters.append(current)
    for c in clusters:
        c.positioned = any(o.has_position for o in c.observations)
    return clusters


def _breaks(current: Cluster, o: NormalizedObservation) -> bool:
    gap_min = (o.t - current.end).total_seconds() / 60.0
    if gap_min > CLUSTER_TIME_GAP_MIN:
        return True
    # Spatial test only when both sides actually have a position.
    here, there = current.coord, o.coord
    return bool(here and there and haversine_m(here, there) > CLUSTER_DIST_M)
