"""Derived presentation data: day titles, per-day statistics, bounds and the route.

PURE. No I/O. Everything here is recomputed from the capsule rather than stored as mutable
state, so a curation edit cannot leave a stale title behind.

This exists because the capsule explorer needs things the draft pipeline never produced:
a heading for each day in the timeline, bounds to fit the map to, and a route split into
legs the map can style differently.
"""

from __future__ import annotations

from collections import defaultdict

from trippo.config.heuristics import (
    ROUTE_MAX_POINTS_PER_SEGMENT,
    ROUTE_SIMPLIFY_TOLERANCE_M,
    TRIP_BBOX_PAD_M,
)
from trippo.domain.geo import Coord, bbox, downsample, pad_bbox, simplify, union_bbox
from trippo.domain.models import (
    ACTIVITY_TYPES,
    TRANSIT_TYPES,
    ActivityDetail,
    BBox,
    Day,
    DayStats,
    Event,
    EventStatus,
    EventType,
    FerryDetail,
    FlightDetail,
    GeometryReliability,
    MediaKind,
    PlaceSource,
    RouteSegment,
    TransitDetail,
    Trip,
)

#: Event types that can headline a day, best first. A drive is never the story of a day.
_TITLE_PRIORITY = (
    EventType.HIKE,
    EventType.BIKE,
    EventType.VISIT,
    EventType.WALK,
    EventType.STOP,
    EventType.FERRY,
    EventType.FLIGHT,
    EventType.OVERNIGHT,
)


def summarize(trip: Trip) -> None:
    """Populate day titles, day stats, bboxes and the trip route. Mutates in place."""
    for day in trip.days:
        events = _active(trip, day)
        day.stats = _day_stats(trip, day, events)
        day.bbox = _day_bbox(trip, events)
        if not day.title:
            day.title = _day_title(trip, day, events)
        if not day.subtitle:
            day.subtitle = _day_subtitle(events, day.title)

    trip.route = _route(trip)
    trip.bbox = _trip_bbox(trip)


# --------------------------------------------------------------------------- helpers


def _active(trip: Trip, day: Day) -> list[Event]:
    return [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]


def _named(e: Event) -> str | None:
    """A place name worth showing. Coordinate labels do not count."""
    if e.title and not _looks_like_coords(e.title):
        return e.title
    if e.place and e.place.source is not PlaceSource.COORDS and e.place.name:
        return e.place.name
    return None


def _looks_like_coords(s: str) -> bool:
    return (bool(s) and s[0].isdigit()) or s.startswith("-")


# --------------------------------------------------------------------------- titles


def _day_title(trip: Trip, day: Day, events: list[Event]) -> str:
    """The most significant named thing that happened.

    An activity wins outright -- "Slieve Donard" is the day. Otherwise the longest named
    visit, which is a decent proxy for what the day was about.
    """
    if not events:
        spanning = [
            e
            for e in (trip.event_by_id(i) for i in day.spanning_event_ids)
            if e and e.status is EventStatus.ACTIVE
        ]
        if any(e.type is EventType.FERRY for e in spanning):
            return "At sea"
        if any(e.type is EventType.UNKNOWN for e in spanning):
            return "Unaccounted"
        return "Nothing recorded"

    for etype in _TITLE_PRIORITY:
        matching = [e for e in events if e.type is etype and _named(e)]
        if not matching:
            continue
        if etype in ACTIVITY_TYPES:
            best = max(matching, key=lambda e: _activity_distance(e))
        else:
            best = max(matching, key=lambda e: e.duration_s)
        name = _named(best)
        if name:
            return name

    if any(e.type is EventType.UNKNOWN for e in events):
        return "Unaccounted"
    if all(e.type in TRANSIT_TYPES for e in events):
        return "On the road"
    return "A quiet day"


def _day_subtitle(events: list[Event], title: str | None) -> str | None:
    """Two or three *other* named places, so the heading has context.

    Three things have to be filtered out or the line reads as noise:

    * transit events, whose "A -> B" labels are derived from neighbours rather than being
      places in their own right;
    * exact repeats, since the same statue can be visited twice in a day;
    * names that merely restate the title -- "Lime Kiln" beside "Lime Kiln, Carrick-a-rede"
      tells the reader nothing.
    """
    names: list[str] = []
    seen: set[str] = set()
    title_key = _subtitle_key(title) if title else ""

    for e in events:
        if e.type in TRANSIT_TYPES or e.type is EventType.UNKNOWN:
            continue
        n = _named(e)
        if not n:
            continue
        key = _subtitle_key(n)
        if not key or key in seen:
            continue
        if title_key and (key in title_key or title_key in key):
            continue
        seen.add(key)
        names.append(n)

    return " \u00b7 ".join(names[:3]) or None


def _subtitle_key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _activity_distance(e: Event) -> float:
    return e.detail.stats.distance_m if isinstance(e.detail, ActivityDetail) else 0.0


# --------------------------------------------------------------------------- stats


def _day_stats(trip: Trip, day: Day, events: list[Event]) -> DayStats:
    by_mode: dict[str, float] = defaultdict(float)
    ascent = 0.0
    has_activity = False
    unaccounted = 0.0

    for e in events:
        d = e.detail
        if isinstance(d, TransitDetail):
            by_mode[e.type.value] += d.distance_m
        elif isinstance(d, FerryDetail):
            by_mode["ferry"] += d.distance_m
        elif isinstance(d, FlightDetail):
            by_mode["flight"] += d.distance_m
        elif isinstance(d, ActivityDetail):
            by_mode[e.type.value] += d.stats.distance_m
            if e.track_ids:
                has_activity = True
                ascent += d.stats.ascent_m
        elif e.type is EventType.UNKNOWN:
            unaccounted += getattr(d, "gap_hours", 0.0)

    photos = videos = 0
    for e in events:
        for mid in e.media_ids:
            m = trip.media_by_id(mid)
            if m is None:
                continue
            if m.kind is MediaKind.VIDEO:
                videos += 1
            else:
                photos += 1

    return DayStats(
        event_count=len(events),
        photo_count=photos,
        video_count=videos,
        distance_by_mode_m={k: round(v, 1) for k, v in by_mode.items() if v > 0},
        # Elevation only when the day actually had an activity -- the scoping rule.
        ascent_m=round(ascent, 1) if has_activity else None,
        has_activity=has_activity,
        unaccounted_hours=round(unaccounted, 2),
    )


# --------------------------------------------------------------------------- bounds


def _event_points(trip: Trip, e: Event) -> list[Coord]:
    pts: list[Coord] = []
    if e.place and e.place.lat is not None and e.place.lon is not None:
        pts.append((e.place.lat, e.place.lon))
    if e.geometry and e.geometry.polyline:
        pts.extend(e.geometry.polyline)
    for tid in e.track_ids:
        t = trip.track_by_id(tid)
        if t and t.bbox:
            pts.append((t.bbox[0], t.bbox[1]))
            pts.append((t.bbox[2], t.bbox[3]))
    for mid in e.media_ids:
        m = trip.media_by_id(mid)
        if m and m.lat is not None and m.lon is not None:
            pts.append((m.lat, m.lon))
    return pts


def _day_bbox(trip: Trip, events: list[Event]) -> BBox | None:
    pts = [p for e in events for p in _event_points(trip, e)]
    if not pts:
        return None
    return BBox.of(pad_bbox(bbox(pts), TRIP_BBOX_PAD_M))


def _trip_bbox(trip: Trip) -> BBox | None:
    boxes = [d.bbox.as_tuple() for d in trip.days if not d.excluded and d.bbox]
    merged = union_bbox(boxes)
    return BBox.of(merged) if merged else None


# --------------------------------------------------------------------------- route


def _route(trip: Trip) -> list[RouteSegment]:
    """Assemble the overall route, one segment per drawable event.

    Kept as segments rather than a single line so the map can style each by what it is --
    a measured trail, a sparse ferry crossing, an unaccounted gap.
    """
    segments: list[RouteSegment] = []

    for day in trip.days:
        if day.excluded:
            continue
        for e in _active(trip, day):
            pts = _segment_points(trip, e)
            if len(pts) < 2:
                continue
            pts = simplify(pts, ROUTE_SIMPLIFY_TOLERANCE_M)
            if len(pts) > ROUTE_MAX_POINTS_PER_SEGMENT:
                pts = downsample(pts, ROUTE_MAX_POINTS_PER_SEGMENT)
            segments.append(
                RouteSegment(
                    event_id=e.id,
                    day_index=day.index,
                    kind=e.type.value,
                    reliability=_reliability(e),
                    points=pts,
                )
            )
    return segments


def _segment_points(trip: Trip, e: Event) -> list[Coord]:
    """Geometry for one leg, best source first.

    An unaccounted gap gets its endpoints only, and its reliability marks it `assumed` so
    the map draws a dashed hint rather than a route. It must never look measured.
    """
    if e.track_ids:
        # Full points live in tracks/<id>.json and the map loads them on demand; the
        # overview only needs enough to place the leg.
        t = trip.track_by_id(e.track_ids[0])
        if t and t.bbox:
            return [(t.bbox[0], t.bbox[1]), (t.bbox[2], t.bbox[3])]
    if e.geometry and e.geometry.polyline:
        return list(e.geometry.polyline)
    if e.type is EventType.UNKNOWN:
        d = e.detail
        ends = [
            (p.lat, p.lon)
            for p in (getattr(d, "from_place", None), getattr(d, "to_place", None))
            if p is not None and p.lat is not None and p.lon is not None
        ]
        return ends
    return []


def _reliability(e: Event) -> GeometryReliability:
    if e.type is EventType.UNKNOWN:
        return GeometryReliability.ASSUMED
    if e.track_ids:
        return GeometryReliability.MEASURED
    if e.geometry:
        return e.geometry.reliability
    return GeometryReliability.ASSUMED
