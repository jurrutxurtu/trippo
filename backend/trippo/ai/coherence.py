"""Coherence checks -- most of them deterministic.

Do not ask a language model what Python can compute. Everything here is arithmetic over
the curated itinerary; only genuinely fuzzy judgements are left to `ai/suggest.py`.

These are the flags a user should see before calling a trip finished: unresolved gaps,
photographs sitting in the pool, a day with pictures but no events, an event whose
photographs were taken somewhere else entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trippo.domain.models import EventStatus, EventType, PlaceSource, Trip


class Severity(StrEnum):
    BLOCKING = "blocking"  # the trip is not finished until this is answered
    WARNING = "warning"  # probably wrong, worth a look
    INFO = "info"  # worth knowing, not a problem


@dataclass(slots=True)
class Finding:
    severity: Severity
    code: str
    message: str
    day_id: str | None = None
    event_id: str | None = None
    action: str | None = None


def check_trip(trip: Trip) -> list[Finding]:
    out: list[Finding] = []
    out += _unaccounted(trip)
    out += _unassigned_media(trip)
    out += _empty_days(trip)
    out += _unresolved_places(trip)
    out += _contested_places(trip)
    out += _double_overnights(trip)
    out += _media_outside_range(trip)
    out += _orphan_tracks(trip)
    order = {Severity.BLOCKING: 0, Severity.WARNING: 1, Severity.INFO: 2}
    out.sort(key=lambda f: order[f.severity])
    return out


def _active(trip: Trip, day):
    return [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]


def _unaccounted(trip: Trip) -> list[Finding]:
    """The one thing that genuinely blocks a finished trip: holes nobody has explained."""
    out = []
    for e in trip.events:
        if e.type is not EventType.UNKNOWN or e.status is not EventStatus.ACTIVE:
            continue
        d = e.detail
        hours = getattr(d, "gap_hours", 0.0)
        km = getattr(d, "displacement_km", 0.0)
        out.append(
            Finding(
                severity=Severity.BLOCKING,
                code="unaccounted_gap",
                message=(
                    f"{hours:.0f} hours and {km:,.0f} km that no source explains"
                    + (
                        f", holding {len(e.media_ids)} photographs"
                        if e.media_ids
                        else ""
                    )
                ),
                day_id=e.day_id,
                event_id=e.id,
                action="Say what happened: a ferry, a flight, or a drive.",
            )
        )
    return out


def _unassigned_media(trip: Trip) -> list[Finding]:
    n = len(trip.unassigned_media_ids)
    if not n:
        return []
    return [
        Finding(
            severity=Severity.WARNING,
            code="unassigned_media",
            message=f"{n} photographs belong to no event",
            action="Attach them, or leave them in the pool.",
        )
    ]


def _empty_days(trip: Trip) -> list[Finding]:
    out = []
    for d in trip.days:
        if d.excluded or _active(trip, d) or d.spanning_event_ids:
            continue
        out.append(
            Finding(
                severity=Severity.WARNING,
                code="empty_day",
                message=f"Day {d.index} has nothing at all",
                day_id=d.id,
                action="Add an event, or exclude the day.",
            )
        )
    return out


def _unresolved_places(trip: Trip) -> list[Finding]:
    n = sum(
        1
        for e in trip.active_events
        if e.place
        and e.place.lat is not None
        and e.place.source is PlaceSource.COORDS
        and e.type is not EventType.UNKNOWN
    )
    if not n:
        return []
    return [
        Finding(
            severity=Severity.WARNING,
            code="unresolved_places",
            message=f"{n} places are still labelled by coordinates",
            action="Name them by hand, or re-run place lookup.",
        )
    ]


def _contested_places(trip: Trip) -> list[Finding]:
    n = sum(
        1
        for e in trip.active_events
        if e.place
        and e.place.source in (PlaceSource.OSM, PlaceSource.NOMINATIM)
        and e.place.confidence < 0.9
    )
    if not n:
        return []
    return [
        Finding(
            severity=Severity.INFO,
            code="contested_places",
            message=f"{n} place names were a close call between two candidates",
            action="Worth a glance; rename any that look wrong.",
        )
    ]


def _double_overnights(trip: Trip) -> list[Finding]:
    out = []
    for d in trip.days:
        if d.excluded:
            continue
        nights = [e for e in _active(trip, d) if e.type is EventType.OVERNIGHT]
        if len(nights) > 1:
            out.append(
                Finding(
                    severity=Severity.WARNING,
                    code="double_overnight",
                    message=f"Day {d.index} has {len(nights)} overnight stays",
                    day_id=d.id,
                    action="One is probably a long daytime stop.",
                )
            )
    return out


def _media_outside_range(trip: Trip) -> list[Finding]:
    """A photograph taken outside its event's time range usually means a clock offset."""
    by_id = {m.id: m for m in trip.media}
    worst = 0
    for e in trip.active_events:
        for mid in e.media_ids:
            m = by_id.get(mid)
            if m is None or m.captured_at is None:
                continue
            if m.captured_at < e.start or m.captured_at > e.end:
                worst += 1
    if not worst:
        return []
    return [
        Finding(
            severity=Severity.INFO,
            code="media_outside_range",
            message=f"{worst} photographs fall outside the event they are attached to",
            action="Usually a camera clock offset, or a hand-moved photograph.",
        )
    ]


def _orphan_tracks(trip: Trip) -> list[Finding]:
    n = len(trip.unassigned_track_ids)
    if not n:
        return []
    return [
        Finding(
            severity=Severity.WARNING,
            code="orphan_tracks",
            message=f"{n} GPS tracks are attached to no event",
            action="Attach each to an activity, or create one from it.",
        )
    ]
