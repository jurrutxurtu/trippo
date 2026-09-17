"""Derived statistics. Pure functions -- stats are never stored as mutable state.

Scoping rule (functional-spec section 10):
  * TripStats carries NO elevation. A city break must produce meaningful trip stats.
  * Elevation and telemetry live on ActivityDetail, on track-bearing events only.
"""

from __future__ import annotations

from collections import defaultdict

from trippo.domain.models import (
    ActivityDetail,
    DayCoverage,
    Event,
    EventStatus,
    EventType,
    FerryDetail,
    FlightDetail,
    MediaKind,
    TransitDetail,
    Trip,
    TripStats,
    UnknownDetail,
)


def compute_trip_stats(trip: Trip) -> TripStats:
    active = [e for e in trip.active_events if not _day_excluded(trip, e)]

    by_mode: dict[str, float] = defaultdict(float)
    for e in active:
        mode, dist = _distance_of(e)
        if dist > 0:
            by_mode[mode] += dist

    unaccounted = [e for e in active if e.type is EventType.UNKNOWN]
    places = {
        (round(e.place.lat, 4), round(e.place.lon, 4))
        for e in active
        if e.place and e.place.lat is not None and e.place.lon is not None
    }

    coverage = _coverage(trip)

    return TripStats(
        day_count=sum(1 for d in trip.days if not d.excluded),
        excluded_day_count=sum(1 for d in trip.days if d.excluded),
        event_count=len(active),
        suppressed_event_count=sum(1 for e in trip.events if e.status is EventStatus.SUPPRESSED),
        place_count=len(places),
        overnight_count=sum(1 for e in active if e.type is EventType.OVERNIGHT),
        photo_count=sum(1 for m in trip.media if m.kind is MediaKind.PHOTO),
        video_count=sum(1 for m in trip.media if m.kind is MediaKind.VIDEO),
        track_count=len(trip.tracks),
        distance_by_mode_m=dict(by_mode),
        unaccounted_hours=round(
            sum(e.detail.gap_hours for e in unaccounted if isinstance(e.detail, UnknownDetail)),
            2,
        ),
        unaccounted_count=len(unaccounted),
        days_blind=sum(1 for c in coverage if c.blind),
        coverage=coverage,
    )


def _day_excluded(trip: Trip, e: Event) -> bool:
    if e.day_id is None:
        return False
    d = trip.day_by_id(e.day_id)
    return bool(d and d.excluded)


def _distance_of(e: Event) -> tuple[str, float]:
    d = e.detail
    if isinstance(d, TransitDetail):
        return (e.type.value, d.distance_m)
    if isinstance(d, FerryDetail):
        return ("ferry", d.distance_m)
    if isinstance(d, FlightDetail):
        return ("flight", d.distance_m)
    if isinstance(d, ActivityDetail):
        return (e.type.value, d.stats.distance_m)
    return (e.type.value, 0.0)


def _coverage(trip: Trip) -> list[DayCoverage]:
    """Per-day source coverage -- drives the day-rail coverage strip and the report.

    This is what turns "why is day 2 empty?" into "day 2 has no timeline data".

    Events spanning into a day count towards its coverage: a day spent entirely at sea on
    a ferry is not blind, it is accounted for by the crossing.
    """
    cov: dict[object, DayCoverage] = {d.date: DayCoverage(date=d.date) for d in trip.days}

    for day in trip.days:
        if day.date not in cov:
            continue
        c = cov[day.date]
        for eid in (*day.event_ids, *day.spanning_event_ids):
            e = trip.event_by_id(eid)
            if e is None:
                continue
            if any(r.source_id.startswith("timeline") for r in e.provenance.derived_from):
                c.timeline_records += 1
            c.media_count += len(e.media_ids)
            c.track_count += len(e.track_ids)

    return [cov[d.date] for d in sorted(trip.days, key=lambda x: x.date)]
