"""AI suggestions -- deliberately small.

Roughly one line per day. Long generated prose is an explicit non-goal (`AGENTS.md` §1):
the user writes the notes, the model helps with phrasing and with choices the ranking
could not settle.

Every function degrades to `None` when no model is configured, and every output is checked
against the facts it was given before it is returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from trippo.ai.validators import invented_names, within_length
from trippo.domain.models import EventStatus, EventType, Trip
from trippo.ports.llm import Llm

MAX_TITLE_CHARS = 60
MAX_SUMMARY_CHARS = 400

SYSTEM = (
    "You help someone title their own travel photographs. "
    "You are given facts that are already verified. "
    "Use ONLY the place names in those facts -- never introduce a place, landmark or "
    "region that is not listed. Prefer the concrete over the poetic. "
    "British English. No exclamation marks."
)


@dataclass(slots=True)
class Suggestion:
    value: str
    alternatives: list[str]
    grounded: bool = True


def _day_facts(trip: Trip, day) -> list[str]:
    facts: list[str] = []
    for eid in day.event_ids:
        e = trip.event_by_id(eid)
        if not e or e.status is not EventStatus.ACTIVE:
            continue
        name = e.title or (e.place.name if e.place else None)
        if name:
            facts.append(name)
        if e.detail.kind == "activity" and e.detail.highlights:
            facts.extend(h.name for h in e.detail.highlights)
    return facts


def suggest_day_title(llm: Llm, trip: Trip, day_id: str) -> Suggestion | None:
    """Three one-line options for a day. The deterministic title stays the default."""
    if not llm.available:
        return None
    day = trip.day_by_id(day_id)
    if day is None:
        return None

    facts = _day_facts(trip, day)
    if not facts:
        return None

    stats = day.stats
    bits = [f"Places visited, in order: {'; '.join(facts[:12])}"]
    if stats.distance_by_mode_m:
        bits.append(
            "Distance: "
            + ", ".join(
                f"{k} {v / 1000:.0f} km" for k, v in stats.distance_by_mode_m.items()
            )
        )
    if stats.ascent_m:
        bits.append(f"Ascent: {stats.ascent_m:.0f} m")
    if stats.photo_count:
        bits.append(f"{stats.photo_count} photographs taken")

    response = llm.complete(
        system=SYSTEM,
        prompt=(
            "Suggest three short titles for this day of a trip. "
            f"Each must be at most {MAX_TITLE_CHARS} characters.\n\n" + "\n".join(bits)
        ),
        schema={
            "type": "object",
            "properties": {
                "titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 3,
                }
            },
            "required": ["titles"],
        },
    )
    if not response.ok:
        return None

    titles = [
        t.strip()
        for t in response.data.get("titles", [])
        if isinstance(t, str) and t.strip() and within_length(t, MAX_TITLE_CHARS)
    ]
    titles = [t for t in titles if not invented_names(t, facts)]
    if not titles:
        return None
    return Suggestion(value=titles[0], alternatives=titles[1:])


def suggest_trip_summary(llm: Llm, trip: Trip) -> Suggestion | None:
    """Two or three sentences for the whole trip, grounded in the day titles."""
    if not llm.available:
        return None

    titles = [d.title for d in trip.days if not d.excluded and d.title]
    if not titles:
        return None

    s = trip.stats
    facts = [
        *titles,
        trip.title,
        f"{s.day_count} days",
        f"{s.photo_count} photographs",
    ]
    prompt = (
        f"Trip: {trip.title}, {s.day_count} days.\n"
        f"Day by day: {'; '.join(titles)}.\n"
        f"Travelled {sum(s.distance_by_mode_m.values()) / 1000:.0f} km; "
        f"{s.overnight_count} nights away; {s.photo_count} photographs.\n\n"
        f"Write two or three sentences summarising the trip, at most "
        f"{MAX_SUMMARY_CHARS} characters. Mention only places listed above."
    )
    response = llm.complete(
        system=SYSTEM,
        prompt=prompt,
        schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    )
    if not response.ok:
        return None

    text = str(response.data.get("summary", "")).strip()
    if not text or not within_length(text, MAX_SUMMARY_CHARS):
        return None
    if invented_names(text, facts):
        return None
    return Suggestion(value=text, alternatives=[])


def polish_note(llm: Llm, note: str) -> Suggestion | None:
    """Tidy the user's own words. Same content, fewer typos."""
    if not llm.available or not note.strip():
        return None
    response = llm.complete(
        system=(
            "You tidy someone's rough travel notes. Fix spelling and grammar. "
            "Keep their voice, their facts and their length. Add nothing."
        ),
        prompt=note.strip(),
        schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    if not response.ok:
        return None
    text = str(response.data.get("text", "")).strip()
    # Tidying must not become rewriting.
    if not text or len(text) > len(note) * 2.2:
        return None
    if invented_names(text, [note]):
        return None
    return Suggestion(value=text, alternatives=[])


def pick_place_label(
    llm: Llm, candidates: list[str], *, context: str
) -> Suggestion | None:
    """Break a tie the deterministic ranking could not settle (ADR-0008).

    The model may only choose from the candidates it was given -- enforced, not requested.
    """
    if not llm.available or len(candidates) < 2:
        return None
    response = llm.complete(
        system=(
            "You pick the most useful name for a place someone stopped at on a trip. "
            "Choose EXACTLY one of the options given. Do not invent or combine."
        ),
        prompt=f"{context}\n\nOptions:\n" + "\n".join(f"- {c}" for c in candidates),
        schema={
            "type": "object",
            "properties": {"choice": {"type": "string"}},
            "required": ["choice"],
        },
    )
    if not response.ok:
        return None
    from trippo.ai.validators import choice_is_offered

    choice = str(response.data.get("choice", "")).strip()
    if not choice_is_offered(choice, candidates):
        return None
    return Suggestion(value=choice, alternatives=[c for c in candidates if c != choice])


def contested_events(trip: Trip) -> list[str]:
    """Events whose name was a close call -- the queue a tiebreak should work through."""
    return [
        e.id
        for e in trip.active_events
        if e.place
        and e.type is not EventType.UNKNOWN
        and e.place.source.value in ("osm", "nominatim")
        and e.place.confidence < 0.9
    ]
