"""Transport classification and overnight detection.

Provider mode labels are hints, never truth (pathology P2). Distance and geometry are
always recomputed from positions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trippo.config.heuristics import (
    FERRY_MIN_KM,
    NIGHT_CORE_END_H,
    NIGHT_CORE_START_H,
    OVERNIGHT_MIN_HOURS,
    SPEED_BIKE_MAX_KMH,
    SPEED_DRIVE_MAX_KMH,
    SPEED_FLIGHT_MIN_KMH,
    SPEED_WALK_MAX_KMH,
    TZ_CHANGE_IS_CROSSING,
)
from trippo.domain.geo import haversine_m
from trippo.domain.models import EventType
from trippo.observe.models import NormalizedObservation

#: Google's own mode strings, mapped to our canonical types. Used only as a prior.
_PROVIDER_MODES: dict[str, EventType] = {
    "IN_PASSENGER_VEHICLE": EventType.DRIVE,
    "IN_VEHICLE": EventType.DRIVE,
    "DRIVING": EventType.DRIVE,
    "MOTORCYCLING": EventType.DRIVE,
    "IN_BUS": EventType.DRIVE,
    "IN_TAXI": EventType.DRIVE,
    "WALKING": EventType.WALK,
    "ON_FOOT": EventType.WALK,
    "RUNNING": EventType.WALK,
    "HIKING": EventType.HIKE,
    "CYCLING": EventType.BIKE,
    "IN_FERRY": EventType.FERRY,
    "BOATING": EventType.FERRY,
    "SAILING": EventType.FERRY,
    "FLYING": EventType.FLIGHT,
    "IN_FLIGHT": EventType.FLIGHT,
}


def classify_move(
    obs: NormalizedObservation,
    *,
    tz_changed: bool = False,
) -> tuple[EventType, float, list[str]]:
    """Return (type, recomputed_distance_m, rules_applied)."""
    rules: list[str] = []
    duration_h = max(obs.duration_s, 1.0) / 3600.0

    dist_m = 0.0
    start_coord, end_coord = obs.coord, obs.end_coord
    if start_coord is not None and end_coord is not None:
        dist_m = haversine_m(start_coord, end_coord)
    speed_kmh = (dist_m / 1000.0) / duration_h

    provider = str(obs.hints.get("mode") or "").upper()
    prior = _PROVIDER_MODES.get(provider)
    if prior is not None:
        rules.append(f"provider hint {provider}")

    # Speed is decisive where it is unambiguous; otherwise trust the provider prior.
    if speed_kmh >= SPEED_FLIGHT_MIN_KMH:
        rules.append(f"speed {speed_kmh:.0f} km/h implies air travel")
        return EventType.FLIGHT, dist_m, rules

    if prior is EventType.FERRY and dist_m / 1000.0 < FERRY_MIN_KM:
        # The reference export labelled a ~900 km crossing IN_FERRY with a 24 km distance.
        # Keep the ferry classification, distrust the distance (P2).
        rules.append("ferry hint retained; provider distance discarded as implausible")
        return EventType.FERRY, dist_m, rules

    if prior is not None:
        if prior is EventType.WALK and speed_kmh > SPEED_BIKE_MAX_KMH:
            rules.append(f"provider said walking but speed is {speed_kmh:.0f} km/h")
        else:
            return prior, dist_m, rules

    if TZ_CHANGE_IS_CROSSING and tz_changed:
        # A UTC-offset change between consecutive segments is a free, reliable signal
        # of an international crossing. Pathology P10.
        rules.append("timezone offset changed across this segment")

    if speed_kmh <= SPEED_WALK_MAX_KMH:
        guess = EventType.WALK
    elif speed_kmh <= SPEED_BIKE_MAX_KMH:
        guess = EventType.BIKE
    elif speed_kmh <= SPEED_DRIVE_MAX_KMH:
        guess = EventType.DRIVE
    else:
        guess = EventType.FLIGHT
    rules.append(f"speed {speed_kmh:.1f} km/h")
    return guess, dist_m, rules


# --------------------------------------------------------------------------- overnight


def local_dt(t: datetime, utc_offset_minutes: int | None) -> datetime:
    """Convert to local wall-clock time at the location. Always local, never home time."""
    if utc_offset_minutes is None:
        return t
    return t.astimezone(timezone(timedelta(minutes=utc_offset_minutes)))


def is_overnight(
    start: datetime, end: datetime, utc_offset_minutes: int | None
) -> tuple[bool, str]:
    """True when a stay covers the core sleeping hours, or is a long dusk-to-dawn stay.

    MUST run after the plausibility gate -- otherwise a phantom mid-ocean "visit" qualifies.
    """
    ls, le = local_dt(start, utc_offset_minutes), local_dt(end, utc_offset_minutes)
    hours = (end - start).total_seconds() / 3600.0

    if _covers_core_night(ls, le):
        return True, f"covers local {NIGHT_CORE_START_H:02d}:00-{NIGHT_CORE_END_H:02d}:00"

    if hours >= OVERNIGHT_MIN_HOURS and (ls.hour >= 19 or le.hour <= 9) and ls.date() != le.date():
        return True, f"{hours:.1f} h spanning dusk to dawn"

    return False, ""


def _covers_core_night(ls: datetime, le: datetime) -> bool:
    """Does [ls, le] contain the local 02:00-05:00 window of any night it spans?"""
    probe = ls.replace(hour=NIGHT_CORE_START_H, minute=0, second=0, microsecond=0)
    for _ in range(3):
        core_end = probe.replace(hour=NIGHT_CORE_END_H)
        if ls <= probe and le >= core_end:
            return True
        probe += timedelta(days=1)
    return False
