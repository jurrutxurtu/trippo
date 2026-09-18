"""Curation session: apply operations, re-derive, validate, and support undo.

Undo keeps snapshots of only the **mutable slice** of a capsule -- events, days, and the
unassigned pools. Media and tracks are immutable once imported, and they are the bulk of
the document, so a 20-deep history costs a few hundred kilobytes rather than 40 MB.

Every operation runs the same cycle:

    apply -> re-derive (titles, stats, bounds, route, selection) -> check invariants

If invariants fail the whole operation is rolled back. A capsule is never left in a state
that violates its own guarantees, which is what lets the UI trust what it renders.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trippo.capsule import io as capsule_io
from trippo.domain import ops
from trippo.domain.invariants import InvariantError, check
from trippo.domain.models import EventType, Trip
from trippo.domain.stats import compute_trip_stats
from trippo.domain.summarize import summarize

HISTORY_DEPTH = 40


def _slice(trip: Trip) -> str:
    """The part of a capsule that curation can change."""
    return json.dumps(
        {
            "events": [e.model_dump(mode="json") for e in trip.events],
            "days": [d.model_dump(mode="json") for d in trip.days],
            "unassigned_media_ids": trip.unassigned_media_ids,
            "unassigned_track_ids": trip.unassigned_track_ids,
            "title": trip.title,
            "subtitle": trip.subtitle,
        },
        ensure_ascii=False,
    )


def _restore(trip: Trip, blob: str) -> None:
    from trippo.domain.models import Day, Event

    data = json.loads(blob)
    trip.events = [Event.model_validate(e) for e in data["events"]]
    trip.days = [Day.model_validate(d) for d in data["days"]]
    trip.unassigned_media_ids = data["unassigned_media_ids"]
    trip.unassigned_track_ids = data["unassigned_track_ids"]
    trip.title = data["title"]
    trip.subtitle = data["subtitle"]


@dataclass
class CurationSession:
    trip: Trip
    root: Path | None = None
    undo_stack: deque[str] = field(default_factory=lambda: deque(maxlen=HISTORY_DEPTH))
    redo_stack: deque[str] = field(default_factory=lambda: deque(maxlen=HISTORY_DEPTH))
    dirty: bool = False

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    # ------------------------------------------------------------------ apply

    def apply(self, op: str, payload: dict[str, Any]) -> None:
        before = _slice(self.trip)
        try:
            _dispatch(self.trip, op, payload)
            self._rederive()
            check(self.trip)
        except (ops.OpError, InvariantError, KeyError, ValueError):
            # Roll back rather than leave the capsule half-changed.
            _restore(self.trip, before)
            self._rederive()
            raise
        self.undo_stack.append(before)
        self.redo_stack.clear()
        self.dirty = True

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(_slice(self.trip))
        _restore(self.trip, self.undo_stack.pop())
        self._rederive()
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(_slice(self.trip))
        _restore(self.trip, self.redo_stack.pop())
        self._rederive()
        self.dirty = True
        return True

    def save(self) -> None:
        if self.root is None:
            raise ops.OpError("This session has nowhere to save to")
        capsule_io.write(self.trip, self.root)
        self.dirty = False

    def _rederive(self) -> None:
        """Titles, stats, bounds, route and photo selection all follow from the events."""
        summarize(self.trip)
        self.trip.stats = compute_trip_stats(self.trip)


# --------------------------------------------------------------------------- dispatch


def _dispatch(trip: Trip, op: str, p: dict[str, Any]) -> None:
    match op:
        case "rename_event":
            ops.rename_event(trip, p["event_id"], p["name"])
        case "set_note":
            ops.set_note(trip, p["event_id"], p.get("note", ""))
        case "set_event_type":
            ops.set_event_type(trip, p["event_id"], EventType(p["type"]))
        case "resolve_gap":
            ops.resolve_gap(trip, p["event_id"], EventType(p["type"]), p.get("name"))
        case "suppress_event":
            ops.suppress_event(trip, p["event_id"])
        case "restore_event":
            ops.restore_event(trip, p["event_id"])
        case "delete_event":
            ops.delete_event(trip, p["event_id"])
        case "add_event":
            ops.add_event(
                trip,
                p["day_id"],
                EventType(p.get("type", "visit")),
                p.get("title", "New event"),
                p.get("start"),
                int(p.get("minutes", 60)),
            )
        case "set_day_excluded":
            ops.set_day_excluded(trip, p["day_id"], bool(p["excluded"]))
        case "set_day_title":
            ops.set_day_title(trip, p["day_id"], p.get("title", ""))
        case "set_day_note":
            ops.set_day_note(trip, p["day_id"], p.get("note", ""))
        case "move_media":
            ops.move_media(trip, list(p["media_ids"]), p.get("target_event_id"))
        case "set_selected_media":
            ops.set_selected_media(trip, p["event_id"], list(p["media_ids"]))
        case "attach_track":
            ops.attach_track(trip, p["event_id"], p["track_id"])
        case "detach_track":
            ops.detach_track(trip, p["event_id"], p["track_id"])
        case "set_trip_meta":
            ops.set_trip_meta(trip, p.get("title"), p.get("subtitle"))
        case _:
            raise ops.OpError(f"Unknown operation {op!r}")
