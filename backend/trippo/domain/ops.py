"""Curation operations -- every way a user can change a trip.

PURE. Each operation takes a `Trip` and mutates it, then the caller re-derives and checks
invariants. Keeping them here rather than in the API layer means they are testable without
HTTP and reusable from the CLI.

Two rules run through all of them:

* **Nothing is ever lost.** Deleting an event returns its media and tracks to the pool;
  excluding a day does the same. The Golden Rule is a structural guarantee, not a UI
  courtesy.
* **A user's edit is final.** Anything the user sets is marked so that re-running the
  draft pipeline or enrichment will not overwrite it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from typing import Any

from trippo.domain.models import (
    DETAIL_FOR_TYPE,
    AbsorbedRef,
    ActivityDetail,
    Event,
    EventStatus,
    EventType,
    FerryDetail,
    FlightDetail,
    Place,
    PlaceDetail,
    PlaceSource,
    Provenance,
    TransitDetail,
    Trip,
    TripStatus,
    UnknownDetail,
)


class OpError(ValueError):
    """The operation cannot be applied. The caller should reject it, not guess."""


def _event(trip: Trip, event_id: str) -> Event:
    e = trip.event_by_id(event_id)
    if e is None:
        raise OpError(f"Unknown event {event_id}")
    return e


def _day(trip: Trip, day_id: str):
    d = trip.day_by_id(day_id)
    if d is None:
        raise OpError(f"Unknown day {day_id}")
    return d


# --------------------------------------------------------------------------- naming


def rename_event(trip: Trip, event_id: str, name: str) -> None:
    """Set the title and place name by hand.

    Marks the place as `user`, which the geocoder treats as final -- re-running enrichment
    will never overwrite it (ADR-0008).
    """
    e = _event(trip, event_id)
    name = name.strip()
    if not name:
        raise OpError("A name cannot be empty")
    e.title = name
    if e.place is None:
        e.place = Place(name=name, source=PlaceSource.USER, confidence=1.0)
    else:
        e.place.name = name
        e.place.source = PlaceSource.USER
        e.place.confidence = 1.0
    e.user_edited = True


def set_note(trip: Trip, event_id: str, note: str) -> None:
    e = _event(trip, event_id)
    e.note = note.strip() or None
    e.user_edited = True


def set_day_note(trip: Trip, day_id: str, note: str) -> None:
    d = _day(trip, day_id)
    d.note = note.strip() or None


def set_day_title(trip: Trip, day_id: str, title: str) -> None:
    """A hand-written day title survives re-derivation, unlike a generated one."""
    d = _day(trip, day_id)
    d.title = title.strip() or None
    d.user_title = bool(d.title)


# --------------------------------------------------------------------------- type


def set_event_type(trip: Trip, event_id: str, new_type: EventType) -> None:
    """Change what kind of event this is, preserving everything that still applies.

    The detail object is replaced because each type carries different fields, but the id,
    time range, media and tracks are kept -- which is what makes this safe to do to an
    unaccounted gap holding 59 photographs.
    """
    e = _event(trip, event_id)
    if e.type is new_type:
        return

    old = e.detail
    wanted = DETAIL_FOR_TYPE[new_type]
    if isinstance(old, wanted):
        e.type = new_type
        e.user_edited = True
        return

    distance = float(getattr(old, "distance_m", 0.0) or 0.0)
    if isinstance(old, ActivityDetail):
        distance = old.stats.distance_m
    if isinstance(old, UnknownDetail):
        distance = old.displacement_km * 1000.0
    duration_s = e.duration_s

    new_detail: Any
    if wanted is TransitDetail:
        new_detail = TransitDetail(distance_m=distance, duration_s=duration_s)
    elif wanted is FerryDetail:
        new_detail = FerryDetail(distance_m=distance, duration_s=duration_s)
    elif wanted is FlightDetail:
        new_detail = FlightDetail(distance_m=distance, duration_s=duration_s)
    elif wanted is ActivityDetail:
        new_detail = ActivityDetail()
        new_detail.stats.distance_m = distance
    elif wanted is UnknownDetail:
        new_detail = UnknownDetail(
            gap_hours=duration_s / 3600.0, displacement_km=distance / 1000.0
        )
    else:
        new_detail = PlaceDetail(duration_s=duration_s)

    e.type = new_type
    e.detail = new_detail
    e.user_edited = True
    e.provenance.rules.append(f"type set to {new_type.value} by hand")


def resolve_gap(trip: Trip, event_id: str, new_type: EventType, name: str | None) -> None:
    """Turn an unaccounted gap into the journey it actually was.

    The distance stays derived from the endpoints and the geometry stays `assumed`: the
    user telling us it was a ferry does not tell us the route it took (ADR-0007).
    """
    e = _event(trip, event_id)
    if e.type is not EventType.UNKNOWN:
        raise OpError("Only an unaccounted gap can be resolved")
    set_event_type(trip, event_id, new_type)
    if name:
        e.title = name.strip()
    e.provenance.rules.append("resolved by hand from an unaccounted gap")


# --------------------------------------------------------------------------- lifecycle


def suppress_event(trip: Trip, event_id: str, reason: str = "hidden by hand") -> None:
    """Hide an event without deleting it. Its media return to the pool while hidden."""
    e = _event(trip, event_id)
    e.status = EventStatus.SUPPRESSED
    e.suppress_reason = reason
    trip.unassigned_media_ids.extend(
        m for m in e.media_ids if m not in trip.unassigned_media_ids
    )
    trip.unassigned_track_ids.extend(
        t for t in e.track_ids if t not in trip.unassigned_track_ids
    )
    e.media_ids = []
    e.track_ids = []
    e.selected_media_ids = []
    e.user_edited = True


def restore_event(trip: Trip, event_id: str) -> None:
    e = _event(trip, event_id)
    e.status = EventStatus.ACTIVE
    e.suppress_reason = None
    e.user_pinned = True  # so the Golden Rule cannot suppress it again
    e.user_edited = True


def delete_event(trip: Trip, event_id: str) -> None:
    """Remove an event entirely. Its media and tracks go back to the pool.

    Deleting an event must never delete a photograph -- media are owned by the trip and
    only referenced by events.
    """
    e = _event(trip, event_id)
    trip.unassigned_media_ids.extend(
        m for m in e.media_ids if m not in trip.unassigned_media_ids
    )
    trip.unassigned_track_ids.extend(
        t for t in e.track_ids if t not in trip.unassigned_track_ids
    )
    for d in trip.days:
        if e.id in d.event_ids:
            d.event_ids.remove(e.id)
        if e.id in d.spanning_event_ids:
            d.spanning_event_ids.remove(e.id)
    trip.events = [x for x in trip.events if x.id != e.id]


def add_event(
    trip: Trip,
    day_id: str,
    event_type: EventType,
    title: str,
    start_iso: str | None = None,
    minutes: int = 60,
) -> str:
    """Add an event the sources missed. Returns its id."""
    from datetime import datetime

    d = _day(trip, day_id)
    existing = [e for e in trip.events if e.day_id == day_id]
    if start_iso:
        start = datetime.fromisoformat(start_iso)
    elif existing:
        start = max(e.end for e in existing)
    else:
        start = datetime.fromisoformat(f"{d.date.isoformat()}T12:00:00+00:00")

    offset = existing[0].utc_offset_minutes if existing else 0
    detail_cls = DETAIL_FOR_TYPE[event_type]
    new = Event(
        id=f"evt_{uuid.uuid4().hex[:10]}",
        day_id=day_id,
        type=event_type,
        start=start,
        end=start + timedelta(minutes=minutes),
        utc_offset_minutes=offset,
        title=title.strip() or None,
        place=Place(name=title.strip() or "Added by hand", source=PlaceSource.USER),
        user_edited=True,
        user_pinned=True,
        detail=detail_cls(),  # type: ignore[call-arg]
    )
    trip.events.append(new)
    d.event_ids.append(new.id)
    starts = {e.id: e.start for e in trip.events}
    d.event_ids.sort(key=lambda i: starts.get(i, new.start))
    return new.id


# --------------------------------------------------------------------------- days


def set_day_excluded(trip: Trip, day_id: str, excluded: bool) -> None:
    """Drop a day from the trip, or bring it back.

    Media and tracks stay exactly where they are: an excluded day is hidden, not deleted,
    and including it again restores the day intact. Remaining days renumber.
    """
    d = _day(trip, day_id)
    d.excluded = excluded
    renumber_days(trip)


def renumber_days(trip: Trip) -> None:
    """Keep `index` contiguous from 1 across non-excluded days (invariant 4)."""
    i = 1
    for d in sorted(trip.days, key=lambda x: x.date):
        if d.excluded:
            d.index = 0
        else:
            d.index = i
            i += 1


# --------------------------------------------------------------------------- media


def move_media(trip: Trip, media_ids: list[str], target_event_id: str | None) -> None:
    """Move photographs between events, or to the unassigned pool.

    `target_event_id = None` means the pool. The exactly-one-owner invariant is maintained
    by detaching from every event first.
    """
    wanted = set(media_ids)
    known = {m.id for m in trip.media}
    if unknown := wanted - known:
        raise OpError(f"Unknown media: {sorted(unknown)[:3]}")

    for e in trip.events:
        if any(m in wanted for m in e.media_ids):
            e.media_ids = [m for m in e.media_ids if m not in wanted]
            e.selected_media_ids = [m for m in e.selected_media_ids if m not in wanted]
    trip.unassigned_media_ids = [
        m for m in trip.unassigned_media_ids if m not in wanted
    ]

    if target_event_id is None:
        trip.unassigned_media_ids.extend(sorted(wanted))
        return

    target = _event(trip, target_event_id)
    target.media_ids.extend(sorted(wanted))
    target.user_edited = True


def set_selected_media(trip: Trip, event_id: str, media_ids: list[str]) -> None:
    """Curate which photographs represent an event.

    Marks the choice as the user's, after which `domain.photos.select()` leaves it alone.
    """
    e = _event(trip, event_id)
    owned = set(e.media_ids)
    if extra := set(media_ids) - owned:
        raise OpError(f"Event does not own media: {sorted(extra)[:3]}")
    e.selected_media_ids = [m for m in e.media_ids if m in set(media_ids)]
    e.user_selected_media = True


def attach_track(trip: Trip, event_id: str, track_id: str) -> None:
    """Attach an unassigned track to an existing event."""
    e = _event(trip, event_id)
    if trip.track_by_id(track_id) is None:
        raise OpError(f"Unknown track {track_id}")
    for other in trip.events:
        if track_id in other.track_ids:
            other.track_ids.remove(track_id)
    if track_id in trip.unassigned_track_ids:
        trip.unassigned_track_ids.remove(track_id)
    e.track_ids.append(track_id)
    e.user_edited = True


def detach_track(trip: Trip, event_id: str, track_id: str) -> None:
    e = _event(trip, event_id)
    if track_id in e.track_ids:
        e.track_ids.remove(track_id)
    if track_id not in trip.unassigned_track_ids:
        trip.unassigned_track_ids.append(track_id)
    e.user_edited = True


def finalise(trip: Trip) -> None:
    """Mark the itinerary as agreed.

    Does not lock anything -- the user can always reopen. It records that a human has been
    through it, which is the difference between a machine's guess and a trip.
    """
    from datetime import datetime

    trip.status = TripStatus.CURATED
    trip.curated_at = datetime.now(UTC)


def reopen(trip: Trip) -> None:
    trip.status = TripStatus.DRAFT
    trip.curated_at = None


def set_summary(trip: Trip, event_id: str, summary: str) -> None:
    """A model-written one-liner. Never touches the user's own note."""
    e = _event(trip, event_id)
    e.summary = summary.strip() or None


def group_events(
    trip: Trip,
    event_ids: list[str],
    title: str,
    representative_id: str | None = None,
    summary: str | None = None,
) -> str:
    """Fold several events into one, and return the new event's id.

    A city centre produces a dozen stops eighty metres apart, each technically a place and
    collectively meaningless. Grouping replaces them with the thing they actually were.

    Nothing is lost. The new event spans the full range and takes every photograph; the
    originals are suppressed with a reason and recorded in provenance.absorbed, so the
    grouping is visible, reversible and undoable.

    The map point comes from one of the originals -- epresentative_id, or the one with
    the most photographs. A centroid would drop a pin in the middle of a road.
    """
    members = [_event(trip, i) for i in event_ids]
    if len(members) < 2:
        raise OpError("Grouping needs at least two events")

    days = {e.day_id for e in members}
    if len(days) > 1:
        raise OpError("Only events on the same day can be grouped")
    day_id = members[0].day_id
    if day_id is None:
        raise OpError("Cannot group events that belong to no day")

    if any(e.track_ids for e in members):
        raise OpError("Activities with tracks cannot be grouped")

    rep = _event(trip, representative_id) if representative_id else None
    if rep is None or rep.id not in {m.id for m in members}:
        rep = max(members, key=lambda e: (len(e.media_ids), e.duration_s))

    media: list[str] = []
    for m in members:
        media.extend(x for x in m.media_ids if x not in media)

    grouped = Event(
        id=f"evt_{uuid.uuid4().hex[:10]}",
        day_id=day_id,
        type=rep.type,
        start=min(m.start for m in members),
        end=max(m.end for m in members),
        utc_offset_minutes=rep.utc_offset_minutes,
        timezone=rep.timezone,
        title=title.strip() or rep.title,
        summary=summary.strip() if summary else None,
        place=rep.place.model_copy() if rep.place else None,
        geometry=rep.geometry.model_copy() if rep.geometry else None,
        media_ids=media,
        user_edited=True,
        user_pinned=True,  # a deliberate grouping must survive the Golden Rule
        provenance=Provenance(
            rules=[f"grouped from {len(members)} events"],
            confidence=1.0,
            absorbed=[
                AbsorbedRef(
                    ref=m.id,
                    reason=f"grouped into '{title.strip()}'",
                    start=m.start,
                    end=m.end,
                )
                for m in members
            ],
        ),
        detail=PlaceDetail(
            duration_s=(
                max(m.end for m in members) - min(m.start for m in members)
            ).total_seconds()
        ),
    )

    for m in members:
        m.media_ids = []
        m.selected_media_ids = []
        m.status = EventStatus.SUPPRESSED
        m.suppress_reason = f"grouped into '{title.strip()}'"

    trip.events.append(grouped)
    day = _day(trip, day_id)
    day.event_ids.append(grouped.id)
    starts = {e.id: e.start for e in trip.events}
    day.event_ids.sort(key=lambda i: starts.get(i, grouped.start))
    return grouped.id


def ungroup_event(trip: Trip, event_id: str) -> None:
    """Undo a grouping: restore the members and remove the wrapper."""
    grouped = _event(trip, event_id)
    refs = [a.ref for a in grouped.provenance.absorbed]
    if not refs:
        raise OpError("That event was not created by grouping")

    for ref in refs:
        member = trip.event_by_id(ref)
        if member is None:
            continue
        member.status = EventStatus.ACTIVE
        member.suppress_reason = None

    # Photographs go back to the pool rather than being guessed back into members: the
    # grouping merged them, and only the user knows which belonged where.
    trip.unassigned_media_ids.extend(
        m for m in grouped.media_ids if m not in trip.unassigned_media_ids
    )
    grouped.media_ids = []
    grouped.selected_media_ids = []
    delete_event(trip, grouped.id)


def set_trip_meta(trip: Trip, title: str | None, subtitle: str | None) -> None:
    if title is not None and title.strip():
        trip.title = title.strip()
    if subtitle is not None:
        trip.subtitle = subtitle.strip() or None
