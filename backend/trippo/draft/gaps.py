"""Unaccounted gap detection. ADR-0007 -- the zero-hallucination guarantee.

The reference trip contains a 47-hour hole: the last Spanish fix on 09-21 evening, then
nothing until a GPX track begins at Glendalough on 09-23 10:26. A ferry crossing and a
long drive happened in between and no source recorded either.

Trippo does not stitch a drive across a void. It emits a visible `unknown` event stating
only the facts, and asks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from trippo.config.heuristics import (
    GAP_ISOLATED_FIX_HOURS,
    GAP_MIN_HOURS,
    GAP_MIN_KM,
    GAP_STATIONARY_KM,
)
from trippo.domain.geo import haversine_m
from trippo.domain.models import EventType
from trippo.observe.models import NormalizedObservation, ObservationKind


@dataclass(slots=True)
class Gap:
    start: datetime
    end: datetime
    from_coord: tuple[float, float] | None
    to_coord: tuple[float, float] | None
    hours: float
    displacement_km: float
    candidate_types: list[EventType] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    #: Kept so candidates can be recomputed if this gap is later merged with another.
    tz_changed: bool = False


def find_gaps(observations: list[NormalizedObservation]) -> list[Gap]:
    """Holes in *merged coverage* that represent unexplained travel.

    Two subtleties, both learned the hard way on real data:

    1. Coverage intervals must be MERGED before looking for holes. Observations overlap
       heavily -- a 13-hour overnight visit coexists with 2-hourly breadcrumbs inside it
       (ADR-0009). Comparing consecutive observations pairwise reports the space between
       two breadcrumbs as a gap even though the enclosing visit covers it. That produced
       31 gaps on the reference trip where only 2 were real.

    2. A hole with no displacement is not unaccounted travel -- it is an unlogged stay.
       The phone simply recorded nothing while the user stayed put. Only a hole the user
       visibly moved across needs explaining.
    """
    positioned = [
        o
        for o in observations
        if o.kind is not ObservationKind.MEDIA and (o.has_position or o.end_t)
    ]
    if len(positioned) < 2:
        return []

    spans = sorted(((o.t, o.end_t or o.t, o) for o in positioned), key=lambda s: s[0])

    gaps: list[Gap] = []
    _, cur_end, cur_obs = spans[0]

    for start, end, obs in spans[1:]:
        if start <= cur_end:  # overlapping or contiguous -- extend the covered interval
            if end > cur_end:
                cur_end, cur_obs = end, obs
            continue

        hours = (start - cur_end).total_seconds() / 3600.0
        from_c = _end_coord(cur_obs)
        to_c = obs.coord
        dist_km = (
            haversine_m(from_c, to_c) / 1000.0  # type: ignore[arg-type]
            if from_c and to_c
            else 0.0
        )

        if _is_unexplained(hours, dist_km):
            tz_changed = (
                cur_obs.utc_offset_minutes is not None
                and obs.utc_offset_minutes is not None
                and cur_obs.utc_offset_minutes != obs.utc_offset_minutes
            )
            reasons = [f"{dist_km:.0f} km displacement with no recorded position"]
            if hours >= GAP_MIN_HOURS:
                reasons.append(f"{hours:.1f} h unrecorded")
            gaps.append(
                Gap(
                    start=cur_end,
                    end=start,
                    from_coord=from_c,
                    to_coord=to_c,
                    hours=round(hours, 2),
                    displacement_km=round(dist_km, 1),
                    candidate_types=_candidates(hours, dist_km, tz_changed),
                    reasons=reasons,
                    tz_changed=tz_changed,
                )
            )

        cur_end, cur_obs = end, obs

    return _merge_split_gaps(gaps)


def _merge_split_gaps(gaps: list[Gap]) -> list[Gap]:
    """Join gaps separated only by an isolated position fix.

    A single mid-Atlantic breadcrumb during a 30-hour ferry crossing does not explain the
    crossing -- it is evidence *of* it. Left alone it splits one honest "unaccounted"
    card into two confusing ones. Merge when the covered sliver between two gaps is short
    relative to the gaps it separates.
    """
    if len(gaps) < 2:
        return gaps

    out: list[Gap] = [gaps[0]]
    for g in gaps[1:]:
        prev = out[-1]
        covered_h = (g.start - prev.end).total_seconds() / 3600.0
        if 0 <= covered_h <= GAP_ISOLATED_FIX_HOURS:
            out[-1] = Gap(
                start=prev.start,
                end=g.end,
                from_coord=prev.from_coord,
                to_coord=g.to_coord,
                hours=round(prev.hours + covered_h + g.hours, 2),
                displacement_km=round(
                    haversine_m(prev.from_coord, g.to_coord) / 1000.0  # type: ignore[arg-type]
                    if prev.from_coord and g.to_coord
                    else prev.displacement_km + g.displacement_km,
                    1,
                ),
                # Recompute rather than inherit: a 30-minute 400 km fragment looks like a
                # flight, but merged into 19 hours and 1,000 km it is plainly a crossing.
                candidate_types=[],  # filled in below, once hours and distance are known
                reasons=[
                    *prev.reasons,
                    "merged with the next gap across an isolated "
                    f"{covered_h * 60:.0f} min fix",
                ],
                tz_changed=prev.tz_changed or g.tz_changed,
            )
            out[-1].candidate_types = _candidates(
                out[-1].hours, out[-1].displacement_km, out[-1].tz_changed
            )
        else:
            out.append(g)
    return out


def _end_coord(o: NormalizedObservation) -> tuple[float, float] | None:
    if o.end_lat is not None and o.end_lon is not None:
        return (o.end_lat, o.end_lon)
    return o.coord


def _is_unexplained(hours: float, dist_km: float) -> bool:
    """Did travel happen that no source explains?

    Displacement is the decisive signal. Time alone is not: a phone that logs nothing for
    ten hours while parked outside a campsite has not hidden a journey.
    """
    if dist_km >= GAP_MIN_KM:
        return True
    return hours >= GAP_MIN_HOURS and dist_km >= GAP_STATIONARY_KM


def _candidates(hours: float, dist_km: float, tz_changed: bool = False) -> list[EventType]:
    """Plausible types for the one-click conversion buttons.

    These populate UI affordances ONLY. The event stays `unknown` and asserts no distance
    or route until the user chooses. ADR-0007.
    """
    if dist_km < 1:
        return [EventType.VISIT, EventType.OVERNIGHT]

    speed = dist_km / max(hours, 0.1)
    out: list[EventType] = []
    if speed > 250:
        out.append(EventType.FLIGHT)
    elif dist_km > 300:
        out.extend([EventType.FERRY, EventType.FLIGHT, EventType.DRIVE])
    else:
        out.append(EventType.DRIVE)

    if tz_changed and EventType.FERRY not in out:
        out.insert(0, EventType.FERRY)
    return out
