"""GPX absolute precedence. ADR-0004.

For any interval covered by a track, the track IS the geometry and the telemetry.
Overlapping timeline observations are masked: retained for provenance, excluded from
rendering and from every statistic. No scoring, no negotiation, no confidence UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise

from trippo.config.heuristics import GPX_ABSORB_OVERLAP, TRACK_MERGE_GAP_MIN
from trippo.ingest.gpx.parse import ParsedTrack
from trippo.observe.models import NormalizedObservation, ObservationKind


@dataclass(slots=True)
class MaskResult:
    kept: list[NormalizedObservation] = field(default_factory=list)
    masked: list[tuple[NormalizedObservation, str]] = field(default_factory=list)
    absorbed_by_track: dict[str, list[str]] = field(default_factory=dict)


def mask_covered(
    observations: list[NormalizedObservation], tracks: list[ParsedTrack]
) -> MaskResult:
    """Remove timeline observations whose interval a GPX track already describes."""
    result = MaskResult()
    spans = [(t, t.start, t.end) for t in tracks if t.start and t.end]

    for o in observations:
        if o.kind is ObservationKind.MEDIA:
            result.kept.append(o)  # media are never masked; they are attached later
            continue

        o_start, o_end = o.t, (o.end_t or o.t)
        hit = None
        for trk, ts, te in spans:
            if _overlap_fraction(o_start, o_end, ts, te) >= GPX_ABSORB_OVERLAP:
                hit = trk
                break

        if hit is None:
            result.kept.append(o)
        else:
            result.masked.append((o, f"superseded by GPX track '{hit.name}'"))
            result.absorbed_by_track.setdefault(hit.id, []).append(o.ref or "?")

    return result


def _overlap_fraction(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> float:
    """Overlap as a fraction of the observation's own duration.

    Zero-length observations (breadcrumbs) count as covered when they fall inside the track.
    """
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    overlap = (earliest_end - latest_start).total_seconds()
    if overlap <= 0:
        return 0.0
    own = (a_end - a_start).total_seconds()
    return 1.0 if own <= 0 else overlap / own


def find_mergeable(tracks: list[ParsedTrack]) -> dict[str, list[str]]:
    """Adjacent tracks that are really one outing. Pathology P9.

    Two Kerry tracks in the reference set ran 18:02-19:16 and 19:17-20:10 -- a single walk
    split by a pause. Trippo offers the merge; it never merges silently.
    """
    dated = sorted(((t, t.start, t.end) for t in tracks if t.start and t.end), key=lambda x: x[1])
    out: dict[str, list[str]] = {}
    limit = timedelta(minutes=TRACK_MERGE_GAP_MIN)
    for (a, _as, ae), (b, bs, _be) in pairwise(dated):
        if timedelta(0) <= bs - ae <= limit:
            out.setdefault(a.id, []).append(b.id)
            out.setdefault(b.id, []).append(a.id)
    return out
