"""Capsule invariants. Pure -- no I/O.

Checked on every read, every write and every curation operation. A violation is a bug in
Trippo, not bad user input, so these raise rather than warn.

The most important one: media are owned by the Trip and merely *referenced* by events.
Deleting an event can never delete a photo. See functional-spec section 6.
"""

from __future__ import annotations

from collections import Counter

from trippo.domain.models import EventStatus, Trip


class InvariantError(AssertionError):
    """A capsule violates its structural guarantees."""


def check(trip: Trip) -> None:
    problems = collect(trip)
    if problems:
        raise InvariantError(
            f"{len(problems)} capsule invariant violation(s):\n  - " + "\n  - ".join(problems)
        )


def collect(trip: Trip) -> list[str]:
    """Return every violation rather than failing on the first -- better for debugging."""
    out: list[str] = []
    active = [e for e in trip.events if e.status is EventStatus.ACTIVE]

    # 1 & 2 -- exactly-one ownership of media and tracks
    for label, all_ids, pool, owned in (
        (
            "media",
            {m.id for m in trip.media},
            trip.unassigned_media_ids,
            [mid for e in active for mid in e.media_ids],
        ),
        (
            "track",
            {t.id for t in trip.tracks},
            trip.unassigned_track_ids,
            [tid for e in active for tid in e.track_ids],
        ),
    ):
        dupes = [i for i, n in Counter(owned).items() if n > 1]
        if dupes:
            out.append(f"{label} referenced by more than one active event: {sorted(dupes)[:5]}")
        both = set(owned) & set(pool)
        if both:
            out.append(f"{label} both owned and unassigned: {sorted(both)[:5]}")
        orphans = all_ids - set(owned) - set(pool)
        if orphans:
            out.append(f"{label} neither owned nor in the unassigned pool: {sorted(orphans)[:5]}")
        unknown = (set(owned) | set(pool)) - all_ids
        if unknown:
            out.append(f"{label} id referenced but not defined: {sorted(unknown)[:5]}")

    # 3 -- day/event referential consistency, both directions
    day_ids = {d.id for d in trip.days}
    for e in trip.events:
        if e.day_id is not None and e.day_id not in day_ids:
            out.append(f"event {e.id} references unknown day {e.day_id}")
    event_ids = {e.id for e in trip.events}
    for d in trip.days:
        for eid in d.event_ids:
            if eid not in event_ids:
                out.append(f"day {d.id} references unknown event {eid}")
                continue
            ev = trip.event_by_id(eid)
            if ev is not None and ev.day_id != d.id:
                out.append(f"day {d.id} lists event {eid}, but the event points at {ev.day_id}")
        for eid in d.spanning_event_ids:
            if eid not in event_ids:
                out.append(f"day {d.id} spans unknown event {eid}")
            elif eid in d.event_ids:
                out.append(f"day {d.id} both owns and spans event {eid}")

    # 4 -- contiguous 1-based indices across non-excluded days
    idx = [d.index for d in trip.days if not d.excluded]
    if sorted(idx) != list(range(1, len(idx) + 1)):
        out.append(f"non-excluded day indices are not contiguous from 1: {sorted(idx)}")

    # 5 -- sane, timezone-aware time ranges
    for e in trip.events:
        if e.start.tzinfo is None or e.end.tzinfo is None:
            out.append(f"event {e.id} has a naive datetime")
        elif e.start > e.end:
            out.append(f"event {e.id} starts after it ends")

    # 6 -- suppression must be explained
    for e in trip.events:
        if e.status is EventStatus.SUPPRESSED and not e.suppress_reason:
            out.append(f"event {e.id} is suppressed without a reason")

    # 7 -- no absolute paths may leak into the capsule (ADR-0001)
    for m in trip.media:
        for field in (m.thumb_ref, m.web_ref, m.poster_ref):
            if field and _looks_absolute(field):
                out.append(f"media {m.id} holds an absolute path: {field}")
    for t in trip.tracks:
        for field in (t.simplified_ref, t.original_ref):
            if field and _looks_absolute(field):
                out.append(f"track {t.id} holds an absolute path: {field}")

    return out


def _looks_absolute(ref: str) -> bool:
    return ref.startswith(("/", "\\")) or (len(ref) > 1 and ref[1] == ":")
