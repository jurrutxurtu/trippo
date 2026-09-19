"""Model-driven suggestions.

Every one of these shares the same shape, and it is the shape that makes them safe:

    the model proposes a STRUCTURAL change over data it can already see,
    and the user accepts or rejects it.

It never writes a fact, never invents a place, and every suggestion is one undoable
operation. A suggestion that fails validation is dropped silently -- the deterministic
result stands, and the user is never shown something the facts do not support.

Five kinds:

  group           a dozen city-centre stops are one visit to a quarter
  demote          a named traffic light is not a place you went
  day_title       what the day was actually for, not its longest stop
  activity_shape  "out-and-back to Slieve Binnian, steep from the saddle"
  place_name      break a tie the deterministic ranking could not settle
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from trippo.ai.validators import choice_is_offered, invented_names, within_length
from trippo.config.heuristics import (
    GROUP_MAX_GAP_MIN,
    GROUP_MAX_SPAN_M,
    GROUP_MIN_EVENTS,
    PASSING_MAX_MINUTES,
    PASSING_REVIEW_MAX_MINUTES,
)
from trippo.domain.geo import haversine_m
from trippo.domain.models import (
    ACTIVITY_TYPES,
    TRANSIT_TYPES,
    ActivityDetail,
    Day,
    Event,
    EventType,
    PlaceSource,
    Trip,
)
from trippo.ports.llm import Llm

MAX_TITLE = 70
MAX_SUMMARY = 160

SYSTEM = (
    "You help someone make sense of their own trip. You are given facts that are already "
    "verified. Use ONLY the names in those facts -- never introduce a place, landmark or "
    "region that is not listed. Prefer the concrete over the poetic. British English. "
    "No exclamation marks."
)


@dataclass
class Suggestion:
    id: str
    kind: str
    title: str
    rationale: str
    #: Operations to apply, in order, if the user accepts.
    ops: list[dict] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    day_id: str | None = None
    media_count: int = 0

    @property
    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "rationale": self.rationale,
            "ops": self.ops,
            "eventIds": self.event_ids,
            "dayId": self.day_id,
            "mediaCount": self.media_count,
        }


def _sid(kind: str) -> str:
    return f"{kind}_{uuid.uuid4().hex[:8]}"


def _named(e: Event) -> str | None:
    if e.place and e.place.source is not PlaceSource.COORDS and e.place.name:
        return e.place.name
    return e.title


def _day_events(trip: Trip, day: Day) -> list[Event]:
    return [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status.value == "active"
    ]


# ============================================================================ A. group


def _clusters(events: list[Event]) -> list[list[Event]]:
    """Runs of nearby stops that are probably one thing.

    Purely geometric -- the model is asked to name the group, not to find it. Letting a
    model decide *which* events are related invites it to relate unrelated ones.
    """
    candidates = [
        e
        for e in events
        if e.type not in TRANSIT_TYPES
        and e.type not in ACTIVITY_TYPES
        and e.type is not EventType.UNKNOWN
        and not e.track_ids
        and e.place
        and e.place.lat is not None
    ]
    candidates.sort(key=lambda e: e.start)

    # Coordinates are known present by the filter above; pull them out so the clustering
    # reads as geometry rather than as a chain of None checks.
    located: list[tuple[Event, tuple[float, float]]] = [
        (e, (e.place.lat, e.place.lon))  # type: ignore[union-attr,misc]
        for e in candidates
    ]

    runs: list[list[Event]] = []
    current: list[tuple[Event, tuple[float, float]]] = []
    for item in located:
        e, here = item
        if not current:
            current = [item]
            continue
        prev = current[-1][0]
        gap_min = (e.start - prev.end).total_seconds() / 60.0
        spread = haversine_m(current[0][1], here)
        if gap_min <= GROUP_MAX_GAP_MIN and spread <= GROUP_MAX_SPAN_M:
            current.append(item)
        else:
            runs.append([x for x, _ in current])
            current = [item]
    if current:
        runs.append([x for x, _ in current])

    return [r for r in runs if len(r) >= GROUP_MIN_EVENTS]


def suggest_groups(llm: Llm, trip: Trip) -> list[Suggestion]:
    """Fold repetitive nearby stops into the thing they collectively were."""
    if not llm.available:
        return []

    out: list[Suggestion] = []
    for day in trip.days:
        if day.excluded:
            continue
        for run in _clusters(_day_events(trip, day)):
            names = [n for n in (_named(e) for e in run) if n]
            if len(names) < GROUP_MIN_EVENTS:
                continue
            media = sum(len(e.media_ids) for e in run)
            minutes = sum(e.duration_s for e in run) / 60.0

            response = llm.complete(
                system=SYSTEM,
                prompt=(
                    "These stops happened one after another, within a few hundred metres. "
                    "They are probably one visit to a single area.\n\n"
                    f"Stops, in order: {'; '.join(names)}\n"
                    f"Total time: {minutes:.0f} minutes. Photographs: {media}.\n\n"
                    "Give the group a short title naming the AREA or the main thing, and "
                    "say which single stop best represents where it happened. "
                    f"The title must be at most {MAX_TITLE} characters and may only use "
                    "words from the stop names above, or plain geographic words."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "represents": {"type": "string"},
                        "worthGrouping": {"type": "boolean"},
                    },
                    "required": ["title", "represents", "worthGrouping"],
                },
            )
            if not response.ok or not response.data.get("worthGrouping"):
                continue

            title = str(response.data.get("title", "")).strip()
            if not title or not within_length(title, MAX_TITLE):
                continue
            if invented_names(title, names):
                continue

            chosen = str(response.data.get("represents", "")).strip()
            rep = next((e for e in run if _named(e) == chosen), None)
            if rep is None and not choice_is_offered(chosen, names):
                rep = max(run, key=lambda e: len(e.media_ids))

            out.append(
                Suggestion(
                    id=_sid("group"),
                    kind="group",
                    title=title,
                    rationale=(
                        f"{len(run)} stops within {GROUP_MAX_SPAN_M:.0f} m over "
                        f"{minutes:.0f} minutes: {'; '.join(names[:4])}"
                        + ("\u2026" if len(names) > 4 else "")
                    ),
                    event_ids=[e.id for e in run],
                    day_id=day.id,
                    media_count=media,
                    ops=[
                        {
                            "op": "group_events",
                            "payload": {
                                "event_ids": [e.id for e in run],
                                "title": title,
                                "representative_id": (rep or run[0]).id,
                            },
                        }
                    ],
                )
            )
    return out


# ============================================================================ B. demote


def suggest_demotions(llm: Llm, trip: Trip) -> list[Suggestion]:
    """Stops that were almost certainly just passing through.

    Unlike the others, this works **without a model**: short, photograph-less and
    unremarkable is a deterministic rule, and gating a safe cleanup behind an API key
    would be silly. When a model is available it is used only to SPARE things -- to pull
    a real destination back out of the pile.

    The rule is conservative and applied before the model sees anything: never propose
    hiding something with a photograph attached. A photograph is proof the traveller
    cared, and no amount of model confidence outranks that.
    """
    # Without a model only the obvious cases; with one, widen the net and let it discriminate.
    limit = PASSING_REVIEW_MAX_MINUTES if llm.available else PASSING_MAX_MINUTES
    candidates = [
        e
        for e in trip.active_events
        if not e.media_ids
        and not e.track_ids
        # A short drive is a leg of the journey, not a stop that can be hidden. Removing
        # one would punch a hole in the route.
        and e.type not in TRANSIT_TYPES
        and e.type not in ACTIVITY_TYPES
        and e.type is not EventType.UNKNOWN
        and e.type is not EventType.OVERNIGHT
        and not e.user_edited
        and e.duration_s / 60.0 <= limit
    ]
    if not candidates:
        return []

    # Short, photo-less and unremarkable is already a strong enough signal to offer in
    # bulk. The model is only asked to spare anything that looks like a real destination.
    spare: set[str] = set()
    if llm.available:
        listing = "\n".join(
            f"{i}. {_named(e) or 'unnamed'} "
            f"({e.duration_s / 60:.0f} min, {e.place.category if e.place else 'unknown'})"
            for i, e in enumerate(candidates[:60])
        )
        response = llm.complete(
            system=SYSTEM,
            prompt=(
                "These stops are brief and have no photographs. Most are traffic, parking "
                "or passing through. Some might still be real destinations.\n\n"
                f"{listing}\n\n"
                "Return the numbers of any that look like a genuine destination worth "
                "keeping. Return an empty list if none do."
            ),
            schema={
                "type": "object",
                "properties": {
                    "keep": {"type": "array", "items": {"type": "integer"}}
                },
                "required": ["keep"],
            },
        )
        if response.ok:
            for i in response.data.get("keep", []):
                if isinstance(i, int) and 0 <= i < len(candidates):
                    spare.add(candidates[i].id)

    doomed = [e for e in candidates if e.id not in spare]
    if not doomed:
        return []

    return [
        Suggestion(
            id=_sid("demote"),
            kind="demote",
            title=f"Hide {len(doomed)} stops that look like passing through",
            rationale=(
                f"Each is under {limit:.0f} minutes with no photographs: "
                + "; ".join((_named(e) or "unnamed") for e in doomed[:5])
                + ("\u2026" if len(doomed) > 5 else "")
                + ". Hidden, not deleted."
            ),
            event_ids=[e.id for e in doomed],
            ops=[
                {
                    "op": "suppress_event",
                    "payload": {"event_id": e.id},
                }
                for e in doomed
            ],
        )
    ]


# ============================================================================ C. day title


def suggest_day_titles(llm: Llm, trip: Trip) -> list[Suggestion]:
    """What the day was *for*, rather than its longest single stop.

    The deterministic title picks the biggest event, which gives "Northern Ireland War
    Memorial" for a day that was really about the Titanic Quarter and the docks. A model
    looking at the whole day can say what it was.
    """
    if not llm.available:
        return []

    out: list[Suggestion] = []
    for day in trip.days:
        if day.excluded or day.user_title:
            continue
        events = _day_events(trip, day)
        if not events:
            continue

        lines: list[str] = []
        facts: list[str] = []
        for e in events:
            name = _named(e)
            mins = e.duration_s / 60.0
            bits = [e.type.value]
            if name:
                bits.append(name)
                facts.append(name)
            if e.track_ids and isinstance(e.detail, ActivityDetail):
                st = e.detail.stats
                bits.append(f"{st.distance_m / 1000:.1f} km, +{st.ascent_m:.0f} m")
                facts.extend(h.name for h in e.detail.highlights)
            bits.append(f"{mins:.0f} min")
            if e.media_ids:
                bits.append(f"{len(e.media_ids)} photos")
            lines.append(" \u00b7 ".join(bits))

        if not facts:
            continue

        response = llm.complete(
            system=SYSTEM,
            prompt=(
                "Here is everything that happened on one day of a trip, in order.\n\n"
                + "\n".join(lines)
                + "\n\nWrite a title saying what the day was FOR. It may combine two "
                "things, for example a walk and a town. Name real places from the list. "
                f"At most {MAX_TITLE} characters."
            ),
            schema={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        )
        if not response.ok:
            continue
        title = str(response.data.get("title", "")).strip()
        if not title or not within_length(title, MAX_TITLE):
            continue
        if invented_names(title, facts):
            continue
        if title == day.title:
            continue

        out.append(
            Suggestion(
                id=_sid("daytitle"),
                kind="day_title",
                title=title,
                rationale=f"Day {day.index} is currently \u201c{day.title}\u201d",
                day_id=day.id,
                ops=[
                    {
                        "op": "set_day_title",
                        "payload": {"day_id": day.id, "title": title},
                    }
                ],
            )
        )
    return out


# ============================================================================ D. activity


def suggest_activity_shapes(llm: Llm, trip: Trip) -> list[Suggestion]:
    """Describe the shape of a walk from its own telemetry.

    Out-and-back or a loop, where the climbing was, what it went over. All of it is in the
    numbers; none of it is in the numbers in a form anyone wants to read.
    """
    if not llm.available:
        return []

    out: list[Suggestion] = []
    for e in trip.active_events:
        if not e.track_ids or not isinstance(e.detail, ActivityDetail) or e.summary:
            continue
        st = e.detail.stats
        track = trip.track_by_id(e.track_ids[0])
        if track is None or st.distance_m <= 0:
            continue

        peaks = [h for h in e.detail.highlights if h.kind == "natural=peak"]
        water = [h for h in e.detail.highlights if "water" in h.kind]
        facts = [e.title or "", *(h.name for h in e.detail.highlights)]

        # Out-and-back leaves ascent and descent nearly equal AND ends where it began.
        loopish = abs(st.ascent_m - st.descent_m) / max(st.ascent_m, 1.0) < 0.15

        response = llm.complete(
            system=SYSTEM,
            prompt=(
                f"An activity called {e.title!r}.\n"
                f"Distance {st.distance_m / 1000:.1f} km, ascent {st.ascent_m:.0f} m, "
                f"descent {st.descent_m:.0f} m, highest point "
                f"{st.max_ele_m or 0:.0f} m, moving time "
                f"{st.moving_time_s / 3600:.1f} h.\n"
                + (f"Summits passed: {', '.join(h.name for h in peaks)}.\n" if peaks else "")
                + (f"Water passed: {', '.join(h.name for h in water)}.\n" if water else "")
                + f"Ascent and descent are {'close to equal' if loopish else 'uneven'}.\n\n"
                "Describe this walk in one sentence: its shape, its effort, and what it "
                f"went over. At most {MAX_SUMMARY} characters. Use only the names above."
            ),
            schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        )
        if not response.ok:
            continue
        text = str(response.data.get("summary", "")).strip()
        if not text or not within_length(text, MAX_SUMMARY):
            continue
        if invented_names(text, facts):
            continue

        out.append(
            Suggestion(
                id=_sid("shape"),
                kind="activity_shape",
                title=text,
                rationale=(
                    f"{e.title} \u00b7 {st.distance_m / 1000:.1f} km, "
                    f"+{st.ascent_m:.0f} m"
                ),
                event_ids=[e.id],
                day_id=e.day_id,
                ops=[
                    {
                        "op": "set_summary",
                        "payload": {"event_id": e.id, "summary": text},
                    }
                ],
            )
        )
    return out


# ============================================================================ F. names


def suggest_place_names(
    llm: Llm, trip: Trip, candidates_for=None
) -> list[Suggestion]:
    """Break the ties the deterministic ranking could not settle.

    The model may only choose from the candidates it was given (ADR-0008) -- enforced, not
    requested.
    """
    if not llm.available:
        return []

    out: list[Suggestion] = []
    for e in trip.active_events:
        if (
            not e.place
            or e.type is EventType.UNKNOWN
            or e.place.source not in (PlaceSource.OSM, PlaceSource.NOMINATIM)
            or e.place.confidence >= 0.9
        ):
            continue
        options = candidates_for(e) if candidates_for else []
        if len(options) < 2:
            continue

        minutes = e.duration_s / 60.0
        response = llm.complete(
            system=(
                "You pick the most useful name for a place someone stopped at on a trip. "
                "Choose EXACTLY one of the options given. Do not invent or combine."
            ),
            prompt=(
                f"A {e.type.value} lasting {minutes:.0f} minutes with "
                f"{len(e.media_ids)} photographs.\n\nOptions:\n"
                + "\n".join(f"- {c}" for c in options)
            ),
            schema={
                "type": "object",
                "properties": {"choice": {"type": "string"}},
                "required": ["choice"],
            },
        )
        if not response.ok:
            continue
        choice = str(response.data.get("choice", "")).strip()
        if not choice_is_offered(choice, options) or choice == e.place.name:
            continue

        out.append(
            Suggestion(
                id=_sid("name"),
                kind="place_name",
                title=choice,
                rationale=(
                    f"Currently \u201c{e.place.name}\u201d. "
                    f"{minutes:.0f} min, {len(e.media_ids)} photographs. "
                    f"Other candidates: {', '.join(c for c in options if c != choice)[:80]}"
                ),
                event_ids=[e.id],
                day_id=e.day_id,
                media_count=len(e.media_ids),
                ops=[
                    {
                        "op": "rename_event",
                        "payload": {"event_id": e.id, "name": choice},
                    }
                ],
            )
        )
    return out


GENERATORS = {
    "group": suggest_groups,
    "demote": suggest_demotions,
    "day_title": suggest_day_titles,
    "activity_shape": suggest_activity_shapes,
}
