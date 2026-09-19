"""The curation agenda: what the user still has to decide.

A capsule exists the moment ingestion finishes, but it is a machine's guess until someone
has been through it. This builds the queue for that pass -- ordered so the things only a
human can answer come first, and the cosmetic ones last.

Three kinds of item, and the distinction is the point:

  decide    only you know this. An unaccounted gap is not a defect to be cleaned up; it is
            a question. Nothing is finished while one is open.
  check     probably wrong, cheap to confirm. Two overnights in a day, photographs in the
            pool, a track attached to nothing.
  polish    entirely optional. Day titles, contested place names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from trippo.ai.coherence import Severity, check_trip
from trippo.domain.models import EventStatus, EventType, PlaceSource, Trip


class Kind(StrEnum):
    DECIDE = "decide"
    CHECK = "check"
    POLISH = "polish"


@dataclass
class AgendaItem:
    id: str
    kind: Kind
    code: str
    title: str
    detail: str
    day_id: str | None = None
    event_id: str | None = None
    #: What the user can do about it, as operations the UI can offer directly.
    actions: list[dict] = field(default_factory=list)
    media_count: int = 0

    @property
    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "code": self.code,
            "title": self.title,
            "detail": self.detail,
            "dayId": self.day_id,
            "eventId": self.event_id,
            "actions": self.actions,
            "mediaCount": self.media_count,
        }


def build_agenda(trip: Trip) -> list[AgendaItem]:
    """Everything still worth a human's attention, most consequential first."""
    items: list[AgendaItem] = []
    items += _gaps(trip)
    items += _from_findings(trip)
    items += _untitled_days(trip)
    items += _contested(trip)
    return items


def blocking_count(items: list[AgendaItem]) -> int:
    return sum(1 for i in items if i.kind is Kind.DECIDE)


# --------------------------------------------------------------------------- decide


def _gaps(trip: Trip) -> list[AgendaItem]:
    """Unaccounted travel. The one thing Trippo refuses to guess at (ADR-0007)."""
    out: list[AgendaItem] = []
    for e in trip.events:
        if e.type is not EventType.UNKNOWN or e.status is not EventStatus.ACTIVE:
            continue
        d = e.detail
        hours = getattr(d, "gap_hours", 0.0)
        km = getattr(d, "displacement_km", 0.0)
        # Suggested first, then everything else that could plausibly cross a gap. A
        # suggestion that turns out to be wrong must never be a dead end.
        suggested = [t.value for t in getattr(d, "candidate_types", [])]
        others = [t for t in ("drive", "ferry", "flight", "walk") if t not in suggested]
        candidates = (suggested or ["drive", "ferry", "flight"]) + others
        out.append(
            AgendaItem(
                id=f"gap:{e.id}",
                kind=Kind.DECIDE,
                code="unaccounted_gap",
                title=f"{hours:.0f} hours nobody recorded",
                detail=(
                    f"{km:,.0f} km of travel that no source explains"
                    + (
                        f", with {len(e.media_ids)} photographs taken inside it. "
                        if e.media_ids
                        else ". "
                    )
                    + "Trippo will not guess. What happened?"
                ),
                day_id=e.day_id,
                event_id=e.id,
                media_count=len(e.media_ids),
                actions=[
                    {
                        "label": f"It was a {t}",
                        "op": "resolve_gap",
                        "payload": {"event_id": e.id, "type": t},
                    }
                    for t in candidates
                ]
                + [
                    {
                        "label": "Leave it unexplained",
                        "op": None,
                        "payload": {},
                        "dismiss": True,
                    }
                ],
            )
        )
    return out


# --------------------------------------------------------------------------- check


_CHECKABLE = {
    "unassigned_media",
    "empty_day",
    "double_overnight",
    "orphan_tracks",
    "media_outside_range",
}


def _from_findings(trip: Trip) -> list[AgendaItem]:
    """Reuse the coherence checks rather than reimplementing them here."""
    out: list[AgendaItem] = []
    for f in check_trip(trip):
        if f.code not in _CHECKABLE or f.severity is Severity.BLOCKING:
            continue
        actions: list[dict] = []
        if f.code == "empty_day" and f.day_id:
            actions.append(
                {
                    "label": "Exclude this day",
                    "op": "set_day_excluded",
                    "payload": {"day_id": f.day_id, "excluded": True},
                }
            )
        out.append(
            AgendaItem(
                id=f"check:{f.code}:{f.day_id or ''}",
                kind=Kind.CHECK,
                code=f.code,
                title=f.message,
                detail=f.action or "",
                day_id=f.day_id,
                event_id=f.event_id,
                actions=actions,
            )
        )
    return out


# --------------------------------------------------------------------------- polish


def _untitled_days(trip: Trip) -> list[AgendaItem]:
    """Days whose title is still a machine's summary rather than the user's own."""
    out: list[AgendaItem] = []
    for d in trip.days:
        if d.excluded or d.user_title:
            continue
        out.append(
            AgendaItem(
                id=f"title:{d.id}",
                kind=Kind.POLISH,
                code="day_title",
                title=f"Day {d.index}: {d.title or 'untitled'}",
                detail=d.subtitle or "Give the day a name in your own words, or keep this.",
                day_id=d.id,
            )
        )
    return out


def _contested(trip: Trip) -> list[AgendaItem]:
    """Places where the geocoder had two close candidates and picked one."""
    out: list[AgendaItem] = []
    for e in trip.active_events:
        if (
            not e.place
            or e.type is EventType.UNKNOWN
            or e.place.source not in (PlaceSource.OSM, PlaceSource.NOMINATIM)
            or e.place.confidence >= 0.9
        ):
            continue
        out.append(
            AgendaItem(
                id=f"name:{e.id}",
                kind=Kind.POLISH,
                code="contested_place",
                title=e.place.name,
                detail=(
                    "Two nearby places scored almost the same. "
                    f"{e.place.category or 'unknown kind'} \u00b7 "
                    f"{len(e.media_ids)} photographs."
                ),
                day_id=e.day_id,
                event_id=e.id,
                media_count=len(e.media_ids),
            )
        )
    return out
