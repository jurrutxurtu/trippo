"""The Golden Rule -- pruning that never deletes.

    keep = has_media or has_track or is_overnight or user_pinned
           or duration >= PRUNE_MIN_DURATION_MIN
           or distance >= PRUNE_MIN_DISTANCE_KM
           or is_named_poi

Events that fail are marked `suppressed` with a reason and stay in the capsule, visible
behind a "N hidden" toggle. The user's brief was explicit: anything with a photo or a
recorded track must never be discarded.
"""

from __future__ import annotations

from trippo.config.heuristics import PRUNE_MIN_DISTANCE_KM, PRUNE_MIN_DURATION_MIN
from trippo.domain.models import (
    ActivityDetail,
    Event,
    EventStatus,
    EventType,
    FerryDetail,
    FlightDetail,
    PlaceSource,
    TransitDetail,
)


def apply_golden_rule(events: list[Event]) -> list[Event]:
    """Mutates `status` and `suppress_reason` in place; returns the same list."""
    for e in events:
        keep, reason = _verdict(e)
        if keep:
            e.status = EventStatus.ACTIVE
            e.suppress_reason = None
        else:
            e.status = EventStatus.SUPPRESSED
            e.suppress_reason = reason
    return events


def _verdict(e: Event) -> tuple[bool, str]:
    # Protected by the Golden Rule -- these are never suppressed, whatever their size.
    if e.media_ids:
        return True, ""
    if e.track_ids:
        return True, ""
    if e.type is EventType.OVERNIGHT:
        return True, ""
    if e.user_pinned or e.user_edited:
        return True, ""
    if e.type is EventType.UNKNOWN:
        return True, ""  # an unaccounted gap must always be visible (ADR-0007)

    duration_min = e.duration_s / 60.0
    if duration_min >= PRUNE_MIN_DURATION_MIN:
        return True, ""

    if _distance_km(e) >= PRUNE_MIN_DISTANCE_KM:
        return True, ""

    if e.place and e.place.source not in (PlaceSource.COORDS,) and e.place.name:
        return True, ""

    return False, (
        f"{duration_min:.0f} min, {_distance_km(e):.1f} km, no photos or track "
        "(below the minor-stop threshold)"
    )


def _distance_km(e: Event) -> float:
    d = e.detail
    if isinstance(d, (TransitDetail, FerryDetail, FlightDetail)):
        return d.distance_m / 1000.0
    if isinstance(d, ActivityDetail):
        return d.stats.distance_m / 1000.0
    return 0.0
