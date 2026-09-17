"""The draft builder -- orchestrates the deterministic pipeline.

Order matters. In particular the plausibility gate MUST precede overnight detection, or a
phantom mid-ocean "visit" becomes an overnight stay (pathology P1).

    observations -> dedup -> gpx precedence -> plausibility -> position index
                 -> events (tracks, visits, moves) -> media attachment
                 -> overnight -> gaps -> days -> prune -> stats

Source-agnostic by construction: this module never asks which source produced an
observation. ADR-0005.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone

from trippo.config.heuristics import (
    CONFIDENCE_MEDIA_CLUSTER,
    CONFIDENCE_TIMELINE_MOVE,
    PLACE_CONFIDENCE_FROM_EXIF,
    PLACE_CONFIDENCE_FROM_INFERRED,
)
from trippo.domain.geo import centroid, haversine_m
from trippo.domain.models import (
    AbsorbedRef,
    ActivityDetail,
    ActivityStats,
    DateRange,
    Day,
    Event,
    EventType,
    FerryDetail,
    FlightDetail,
    Geometry,
    GeometryReliability,
    LocationSource,
    MediaAsset,
    Place,
    PlaceDetail,
    PlaceSource,
    Provenance,
    SourceRef,
    TrackMeta,
    TransitDetail,
    Trip,
    UnknownDetail,
)
from trippo.domain.stats import compute_trip_stats
from trippo.domain.summarize import summarize
from trippo.draft.cluster import cluster_media
from trippo.draft.dedup import dedup_visits
from trippo.draft.gaps import find_gaps
from trippo.draft.gpx_precedence import find_mergeable, mask_covered
from trippo.draft.plausibility import find_phantoms
from trippo.draft.prune import apply_golden_rule
from trippo.draft.transport import classify_move, is_overnight, local_dt
from trippo.ingest.gpx.parse import ParsedTrack, track_bbox
from trippo.observe.index import PositionIndex
from trippo.observe.models import NormalizedObservation, ObservationKind

#: The concrete detail classes a move can produce. Mirrors DETAIL_FOR_TYPE.
EventDetailUnion = TransitDetail | FerryDetail | FlightDetail | ActivityDetail
_ACTIVITY_BY_GPX_TYPE = {
    "hiking": EventType.HIKE,
    "hike": EventType.HIKE,
    "walking": EventType.WALK,
    "walk": EventType.WALK,
    "running": EventType.WALK,
    "cycling": EventType.BIKE,
    "biking": EventType.BIKE,
    "road_biking": EventType.BIKE,
    "mountain_biking": EventType.BIKE,
}


@dataclass
class BuildInputs:
    title: str
    observations: list[NormalizedObservation] = field(default_factory=list)
    tracks: list[ParsedTrack] = field(default_factory=list)
    media: list[MediaAsset] = field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    default_offset_minutes: int = 0


@dataclass
class BuildTrace:
    """What the pipeline decided and why. Surfaced in the UI as "why is this here?"."""

    dropped_duplicates: list[str] = field(default_factory=list)
    phantoms: list[str] = field(default_factory=list)
    masked_by_gpx: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    #: Media positions by provenance. The mix is worth showing: a trip where most photos
    #: carry their own GPS is qualitatively better than one relying on interpolation.
    media_gps_exif: int = 0
    inferred_positions: int = 0
    unlocatable_media: int = 0
    events_placed_by_media: int = 0


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build(inputs: BuildInputs) -> tuple[Trip, BuildTrace]:
    trace = BuildTrace()
    obs = sorted(inputs.observations, key=lambda o: o.t)

    # 1 -- deduplicate nested/duplicate visits (P4)
    obs, dropped = dedup_visits(obs)
    trace.dropped_duplicates = [f"{o.ref}: {why}" for o, why in dropped]

    # 2 -- GPX takes absolute precedence over anything it covers (ADR-0004)
    mask = mask_covered(obs, inputs.tracks)
    obs = mask.kept
    trace.masked_by_gpx = [f"{o.ref}: {why}" for o, why in mask.masked]

    # 3 -- plausibility gate BEFORE overnight detection (P1)
    phantoms = find_phantoms(obs)
    phantom_refs = {p.observation.ref for p in phantoms}
    trace.phantoms = [f"{p.observation.ref}: {p.reason}" for p in phantoms]

    # 4 -- position index from every *measured* position (ADR-0009 layer 2).
    # EXIF-geotagged media are measurements and contribute; inferred ones never do.
    track_obs = [
        NormalizedObservation(
            t=p.t,
            kind=ObservationKind.TRACKPOINT,
            source_id=f"gpx:{t.id}",
            lat=p.lat,
            lon=p.lon,
        )
        for t in inputs.tracks
        for p in t.points
        if p.t
    ]
    index = PositionIndex(obs + track_obs)

    # 5 -- resolve a position for every media item, best source first (P6).
    #   EXIF GPS  >  interpolation from timeline/GPX/geotagged photos  >  admit defeat
    for m in inputs.media:
        if m.location_source is LocationSource.EXIF:
            trace.media_gps_exif += 1
            continue
        if m.lat is not None:
            continue
        if m.captured_at is None:
            trace.unlocatable_media += 1
            m.location_source = LocationSource.NONE
            continue
        pos = index.at(m.captured_at)
        if pos:
            m.lat, m.lon = pos
            m.location_source = LocationSource.INFERRED
            trace.inferred_positions += 1
        else:
            m.location_source = LocationSource.NONE
            trace.unlocatable_media += 1


    events: list[Event] = []
    tracks_meta: list[TrackMeta] = []

    # 6 -- one event per GPX track
    mergeable = find_mergeable(inputs.tracks)
    for t in inputs.tracks:
        if not (t.start and t.end):
            continue
        etype = _ACTIVITY_BY_GPX_TYPE.get((t.activity_type or "").lower(), EventType.HIKE)
        offset = _offset_for(obs, t.start, inputs.default_offset_minutes)
        tracks_meta.append(
            TrackMeta(
                id=t.id,
                source_id=f"gpx:{t.id}",
                name=t.name,
                activity_type=t.activity_type,
                start=t.start,
                end=t.end,
                bbox=track_bbox(t.points),
                stats=t.stats,
                point_count=len(t.points),
                simplified_ref=f"tracks/{t.id}.json",
                original_ref=f"tracks/{t.id}.gpx",
                mergeable_with=mergeable.get(t.id, []),
            )
        )
        events.append(
            Event(
                id=_nid("evt"),
                type=etype,
                start=t.start,
                end=t.end,
                utc_offset_minutes=offset,
                # Name and type come free from <trk>; no geocoding needed (P8).
                title=t.name,
                place=Place(
                    name=t.name,
                    lat=t.points[0].lat,
                    lon=t.points[0].lon,
                    source=PlaceSource.GPX,
                    confidence=1.0,
                ),
                geometry=Geometry(
                    kind="line", track_id=t.id, reliability=GeometryReliability.MEASURED
                ),
                track_ids=[t.id],
                provenance=Provenance(
                    derived_from=[SourceRef(source_id=f"gpx:{t.id}")],
                    rules=["GPX track (absolute precedence, ADR-0004)"],
                    confidence=1.0,
                    absorbed=[
                        AbsorbedRef(ref=r, reason="covered by this track")
                        for r in mask.absorbed_by_track.get(t.id, [])
                    ],
                ),
                detail=ActivityDetail(
                    stats=ActivityStats(**t.stats.model_dump()),
                    activity_type_hint=t.activity_type,
                ),
            )
        )

    # 7 -- events from timeline visits and moves
    prev_offset: int | None = None
    for o in obs:
        if o.kind is ObservationKind.BREADCRUMB:
            continue  # layer 2 never creates events (ADR-0009)

        if o.kind is ObservationKind.VISIT:
            if o.ref in phantom_refs:
                continue  # absorbed into the adjacent crossing (P1)
            events.append(_visit_event(o, inputs.default_offset_minutes))

        elif o.kind is ObservationKind.MOVE:
            tz_changed = (
                prev_offset is not None
                and o.utc_offset_minutes is not None
                and prev_offset != o.utc_offset_minutes
            )
            events.append(_move_event(o, index, tz_changed, inputs.default_offset_minutes))

        if o.utc_offset_minutes is not None:
            prev_offset = o.utc_offset_minutes

    # 8 -- absorb phantom visits into the crossing that swallowed them
    _absorb_phantoms(events, phantoms)

    # 9 -- overnight detection, strictly after the plausibility gate
    for e in events:
        if e.type is not EventType.VISIT:
            continue
        ok, why = is_overnight(e.start, e.end, e.utc_offset_minutes)
        if ok:
            e.type = EventType.OVERNIGHT
            e.provenance.rules.append(f"overnight: {why}")

    # 10 -- unaccounted gaps (ADR-0007)
    for g in find_gaps(obs + track_obs):
        events.append(
            Event(
                id=_nid("evt"),
                type=EventType.UNKNOWN,
                start=g.start,
                end=g.end,
                utc_offset_minutes=_offset_for(obs, g.start, inputs.default_offset_minutes),
                title="Unaccounted",
                provenance=Provenance(rules=g.reasons, confidence=0.0),
                detail=UnknownDetail(
                    gap_hours=g.hours,
                    displacement_km=g.displacement_km,
                    from_place=_coord_place(g.from_coord),
                    to_place=_coord_place(g.to_coord),
                    candidate_types=g.candidate_types,
                ),
            )
        )
        trace.gaps.append(
            f"{g.start.isoformat()} -> {g.end.isoformat()}: "
            f"{g.hours:.1f} h, {g.displacement_km:.0f} km ({'; '.join(g.reasons)})"
        )

    events.sort(key=lambda e: (e.start, e.end))

    # 11 -- attach media, then create photo-only events for whatever is left over
    unassigned_media = _attach_media(events, inputs.media)
    events.extend(_photo_only_events(unassigned_media, inputs.default_offset_minutes))
    events.sort(key=lambda e: (e.start, e.end))
    unassigned_media = _attach_media(events, inputs.media)

    # 11b -- an event with no coordinates can borrow one from its own photos.
    # Timeline visits always carry coordinates, but photo-derived and manual events may
    # not, and a geotagged photo is the best evidence available for where they happened.
    trace.events_placed_by_media += _place_events_from_media(events, inputs.media)


    # 12 -- days, then the Golden Rule
    days = _build_days(events, inputs)
    apply_golden_rule(events)

    # Recompute ownership last: window clamping may have dropped events, and their media
    # must land in the pool rather than vanish. The Golden Rule guarantees suppressed
    # events never hold media, so active-event ownership is complete.
    owned = {mid for e in events for mid in e.media_ids}
    unassigned_media = [m for m in inputs.media if m.id not in owned]

    trip = Trip(
        id=_nid("trip"),
        title=inputs.title,
        date_range=_date_range(days, inputs),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        days=days,
        events=events,
        tracks=tracks_meta,
        media=inputs.media,
        unassigned_media_ids=[m.id for m in unassigned_media],
        unassigned_track_ids=[
            t.id for t in tracks_meta if not any(t.id in e.track_ids for e in events)
        ],
    )
    # Derived presentation data: day titles, per-day stats, bounds, the overview route.
    summarize(trip)
    trip.stats = compute_trip_stats(trip)
    return trip, trace


# --------------------------------------------------------------------------- helpers


def _coord_place(c: tuple[float, float] | None) -> Place | None:
    if not c:
        return None
    return Place(name=f"{c[0]:.4f}, {c[1]:.4f}", lat=c[0], lon=c[1], source=PlaceSource.COORDS)


def _offset_for(obs: list[NormalizedObservation], t: datetime, default: int) -> int:
    """Nearest known UTC offset. Local time is always local at the location."""
    best, best_delta = default, None
    for o in obs:
        if o.utc_offset_minutes is None:
            continue
        delta = abs((o.t - t).total_seconds())
        if best_delta is None or delta < best_delta:
            best, best_delta = o.utc_offset_minutes, delta
    return best


def _visit_event(o: NormalizedObservation, default_offset: int) -> Event:
    # The on-device export carries NO place name -- only an id (ADR-0008). Until the
    # geocoder runs, the label is the coordinate pair. Honest, and obviously provisional.
    name = str(o.hints.get("name") or "")
    place = Place(
        name=name or (f"{o.lat:.4f}, {o.lon:.4f}" if o.has_position else "Unknown location"),
        lat=o.lat,
        lon=o.lon,
        address=str(o.hints["address"]) if o.hints.get("address") else None,
        google_place_id=str(o.hints["place_id"]) if o.hints.get("place_id") else None,
        source=PlaceSource.GOOGLE if name else PlaceSource.COORDS,
        confidence=1.0 if name else 0.0,
    )
    return Event(
        id=_nid("evt"),
        type=EventType.VISIT,
        start=o.t,
        end=o.end_t or o.t,
        utc_offset_minutes=o.utc_offset_minutes
        if o.utc_offset_minutes is not None
        else default_offset,
        place=place,
        geometry=Geometry(kind="point") if o.has_position else None,
        provenance=Provenance(
            derived_from=[SourceRef(source_id=o.source_id, ref=o.ref)],
            rules=["timeline visit"],
            confidence=float(o.hints.get("probability") or 0.5),  # type: ignore[arg-type]
        ),
        detail=PlaceDetail(duration_s=o.duration_s),
    )


def _move_event(
    o: NormalizedObservation, index: PositionIndex, tz_changed: bool, default_offset: int
) -> Event:
    etype, dist_m, rules = classify_move(o, tz_changed=tz_changed)

    # Geometry from breadcrumbs. Reliability is explicit so a crossing drawn from two
    # points never renders as a confident line (ADR-0007).
    crumbs = index.between(o.t, o.end_t or o.t)
    if len(crumbs) >= 8:
        reliability = GeometryReliability.MEASURED
    elif len(crumbs) >= 2:
        reliability = GeometryReliability.SPARSE
    else:
        reliability = GeometryReliability.ASSUMED
    if len(crumbs) >= 2:
        dist_m = max(
            dist_m, sum(haversine_m(crumbs[i], crumbs[i + 1]) for i in range(len(crumbs) - 1))
        )

    detail: EventDetailUnion
    if etype is EventType.FERRY:
        detail = FerryDetail(
            distance_m=round(dist_m, 1), duration_s=o.duration_s, geometry_reliability=reliability
        )
    elif etype is EventType.FLIGHT:
        detail = FlightDetail(
            distance_m=round(dist_m, 1), duration_s=o.duration_s, geometry_reliability=reliability
        )
    elif etype in (EventType.HIKE, EventType.WALK, EventType.BIKE):
        detail = ActivityDetail(stats=ActivityStats(distance_m=round(dist_m, 1)))
    else:
        detail = TransitDetail(
            distance_m=round(dist_m, 1),
            duration_s=o.duration_s,
            geometry_reliability=reliability,
            mode_hint=str(o.hints.get("mode") or "") or None,
        )

    return Event(
        id=_nid("evt"),
        type=etype,
        start=o.t,
        end=o.end_t or o.t,
        utc_offset_minutes=o.utc_offset_minutes
        if o.utc_offset_minutes is not None
        else default_offset,
        geometry=Geometry(
            kind="line",
            polyline=crumbs if len(crumbs) >= 2 else None,
            reliability=reliability,
        ),
        provenance=Provenance(
            derived_from=[SourceRef(source_id=o.source_id, ref=o.ref)],
            rules=rules,
            confidence=CONFIDENCE_TIMELINE_MOVE,
        ),
        detail=detail,
    )


def _absorb_phantoms(events: list[Event], phantoms: list) -> None:
    """Attach each phantom visit to the transit event that actually contains it (P1)."""
    for p in phantoms:
        o = p.observation
        host = next(
            (
                e
                for e in events
                if e.type in (EventType.FERRY, EventType.FLIGHT, EventType.DRIVE)
                and e.start <= o.t <= e.end + timedelta(hours=24)
            ),
            None,
        )
        if host is None:
            continue
        host.provenance.absorbed.append(
            AbsorbedRef(
                ref=o.ref or "?",
                reason=f"phantom stationary period: {p.reason}",
                start=o.t,
                end=o.end_t,
            )
        )
        # The crossing really lasted until the phantom "visit" ended.
        if o.end_t and o.end_t > host.end:
            host.end = o.end_t
            host.provenance.rules.append("extended to cover an absorbed phantom stop")


def _attach_media(events: list[Event], media: list[MediaAsset]) -> list[MediaAsset]:
    """Assign each media item to the event containing its timestamp. Returns leftovers.

    Preference order: an event whose range contains the photo, innermost (shortest) first
    so a hike inside a day beats a day-long visit. Unaccounted gaps do accept media --
    that is how the ferry-day photos find a home (ADR-0007).
    """
    for e in events:
        e.media_ids = []
    leftovers: list[MediaAsset] = []

    containers = sorted(events, key=lambda e: e.duration_s)
    for m in media:
        if m.captured_at is None:
            leftovers.append(m)
            continue
        host = next((e for e in containers if e.start <= m.captured_at <= e.end), None)
        if host is None:
            leftovers.append(m)
        else:
            host.media_ids.append(m.id)
    return leftovers


def _photo_only_events(media: list[MediaAsset], default_offset: int) -> list[Event]:
    """Candidate stops built from photos alone -- the photo-only path (ADR-0005).

    With no GPS these have no coordinates, only a time range. That is an honest, useful
    result: the day gains structure even though it cannot gain place names.
    """
    obs = [
        NormalizedObservation(
            t=m.captured_at,
            kind=ObservationKind.MEDIA,
            source_id="media",
            lat=m.lat,
            lon=m.lon,
            ref=m.id,
        )
        for m in media
        if m.captured_at is not None
    ]
    out: list[Event] = []
    for c in cluster_media(obs):
        coord = c.coord
        out.append(
            Event(
                id=_nid("evt"),
                type=EventType.VISIT,
                start=c.start,
                end=c.end,
                utc_offset_minutes=default_offset,
                place=_coord_place(coord)
                or Place(name="Unlocated photos", source=PlaceSource.COORDS),
                geometry=Geometry(kind="point") if coord else None,
                provenance=Provenance(
                    derived_from=[SourceRef(source_id="media")],
                    rules=[
                        f"clustered from {len(c.media_refs)} media items"
                        + ("" if coord else " (no position available)")
                    ],
                    confidence=CONFIDENCE_MEDIA_CLUSTER,
                ),
                detail=PlaceDetail(duration_s=c.duration_s),
            )
        )
    return out


def _place_events_from_media(events: list[Event], media: list[MediaAsset]) -> int:
    """Locate events from their attached photos, and record how well.

    Applies to events with no coordinate at all, and to ones carrying only a bare
    coordinate label with no confidence -- the photo-only clusters, which know where they
    are but not how much to trust it.

    Prefers EXIF-geotagged media (a measured fix) and falls back to inferred positions.
    `place.confidence` records which, so the UI, the geocoder and the ranking logic can
    weight it accordingly.
    """
    by_id = {m.id: m for m in media}
    placed = 0

    for e in events:
        if e.type is EventType.UNKNOWN:
            continue  # an unaccounted gap must not acquire a location (ADR-0007)
        already_trusted = (
            e.place is not None and e.place.lat is not None and e.place.confidence > 0
        )
        if already_trusted:
            continue

        attached = [m for m in (by_id.get(i) for i in e.media_ids) if m and m.lat is not None]
        if not attached:
            continue

        exact = [m for m in attached if m.location_source is LocationSource.EXIF]
        chosen = exact or attached
        coord = centroid([(m.lat, m.lon) for m in chosen])  # type: ignore[misc]

        e.place = Place(
            name=f"{coord[0]:.4f}, {coord[1]:.4f}",
            lat=coord[0],
            lon=coord[1],
            source=PlaceSource.COORDS,
            confidence=PLACE_CONFIDENCE_FROM_EXIF if exact else PLACE_CONFIDENCE_FROM_INFERRED,
        )
        e.geometry = e.geometry or Geometry(kind="point")
        e.provenance.rules.append(
            f"located from {len(chosen)} "
            + ("geotagged photo(s)" if exact else "photo(s) with inferred positions")
        )
        placed += 1

    return placed


def _build_days(events: list[Event], inputs: BuildInputs) -> list[Day]:
    """One day per local calendar date. Events are filed by their LOCAL start date."""
    buckets: dict[date, list[Event]] = {}
    for e in events:
        d = local_dt(e.start, e.utc_offset_minutes).date()
        buckets.setdefault(d, []).append(e)

    # The ingestion window is padded by a day so that visits starting late in local time
    # are not lost. Clamp back to what the user actually asked for, so the trip does not
    # silently acquire bookend days.
    if inputs.window_start:
        buckets = {d: v for d, v in buckets.items() if d >= inputs.window_start}
    if inputs.window_end:
        buckets = {d: v for d, v in buckets.items() if d <= inputs.window_end}

    # Fill interior dates so a blind day still exists instead of silently vanishing.
    if buckets:
        cur, last = min(buckets), max(buckets)
        while cur <= last:
            buckets.setdefault(cur, [])
            cur += timedelta(days=1)

    days: list[Day] = []
    kept_event_ids: set[str] = set()
    by_date: dict[date, Day] = {}
    for i, d in enumerate(sorted(buckets), start=1):
        day = Day(
            id=_nid("day"),
            index=i,
            date=d,
            timezone=str(timezone(timedelta(minutes=inputs.default_offset_minutes))),
        )
        for e in sorted(buckets[d], key=lambda x: x.start):
            e.day_id = day.id
            day.event_ids.append(e.id)
            kept_event_ids.add(e.id)
        days.append(day)
        by_date[d] = day

    # Multi-day events (crossings, overnights, long gaps) are listed on every day they
    # cover, so a day is never reported as empty when something is happening in it.
    # Ownership -- and therefore media accounting -- stays with the start day (P5).
    for day in days:
        for eid in day.event_ids:
            e = next(ev for ev in events if ev.id == eid)
            start_local = local_dt(e.start, e.utc_offset_minutes).date()
            end_local = local_dt(e.end, e.utc_offset_minutes).date()
            if end_local <= start_local:
                continue
            e.continues_to_next_day = True
            cur = start_local + timedelta(days=1)
            while cur <= end_local:
                if (target := by_date.get(cur)) is not None:
                    target.spanning_event_ids.append(e.id)
                cur += timedelta(days=1)

    # Drop events that fell outside the clamped window entirely, so the capsule keeps its
    # exactly-one-owner invariant for their media.
    events[:] = [e for e in events if e.id in kept_event_ids]
    return days


def _date_range(days: list[Day], inputs: BuildInputs) -> DateRange:
    if days:
        return DateRange(start=days[0].date, end=days[-1].date)
    today = datetime.now(UTC).date()
    return DateRange(start=inputs.window_start or today, end=inputs.window_end or today)
