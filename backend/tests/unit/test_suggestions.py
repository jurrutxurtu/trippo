"""Model-driven suggestions, and the operations that apply them.

The safety property under test throughout: a suggestion proposes a structural change over
data the model can already see. It never writes a fact, never invents a place, and every
accepted suggestion is one undoable operation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from trippo.ai import suggestions as sg
from trippo.capsule.session import CurationSession
from trippo.domain import ops
from trippo.domain.invariants import collect
from trippo.domain.models import (
    ActivityDetail,
    ActivityStats,
    DateRange,
    Day,
    Event,
    EventStatus,
    EventType,
    MediaAsset,
    MediaKind,
    Place,
    PlaceDetail,
    PlaceSource,
    TrackHighlight,
    TrackMeta,
    Trip,
)
from trippo.domain.stats import compute_trip_stats
from trippo.domain.summarize import summarize
from trippo.ports.llm import LlmResponse, NullProvider

T0 = datetime(2023, 9, 26, 9, 0, tzinfo=UTC)


class FakeLlm:
    name = "fake"
    available = True

    def __init__(self, data: dict[str, Any] | None = None, ok: bool = True) -> None:
        self._data = data or {}
        self._ok = ok
        self.prompts: list[str] = []

    def complete(self, *, system: str, prompt: str, schema: dict) -> LlmResponse:
        self.prompts.append(prompt)
        return LlmResponse(data=self._data, ok=self._ok)


def _ev(
    eid: str,
    name: str,
    *,
    at: int,
    minutes: int = 10,
    lat: float = 54.600,
    lon: float = -5.930,
    media: list[str] | None = None,
    etype: EventType = EventType.VISIT,
    source: PlaceSource = PlaceSource.OSM,
    confidence: float = 0.95,
) -> Event:
    start = T0 + timedelta(minutes=at)
    return Event(
        id=eid,
        day_id="d1",
        type=etype,
        start=start,
        end=start + timedelta(minutes=minutes),
        title=name,
        place=Place(
            name=name, lat=lat, lon=lon, source=source, confidence=confidence,
            category="historic=memorial",
        ),
        media_ids=media or [],
        detail=PlaceDetail(),
    )


def _trip(events: list[Event], media_ids: list[str] | None = None) -> Trip:
    ids = media_ids or []
    owned = {m for e in events for m in e.media_ids}
    media = [
        MediaAsset(
            id=m,
            hash=m,
            kind=MediaKind.PHOTO,
            filename=f"{m}.jpg",
            normalized_filename=f"{m}.jpg",
            captured_at=T0,
            thumb_ref=f"media/thumb/{m}.webp",
        )
        for m in sorted(owned | set(ids))
    ]
    day = Day(id="d1", index=1, date=date(2023, 9, 26), event_ids=[e.id for e in events])
    trip = Trip(
        id="t",
        title="Ireland",
        date_range=DateRange(start=day.date, end=day.date),
        created_at=T0,
        updated_at=T0,
        days=[day],
        events=events,
        media=media,
        unassigned_media_ids=[m for m in ids if m not in owned],
    )
    summarize(trip)
    trip.stats = compute_trip_stats(trip)
    return trip


# ============================================================================ grouping op


def test_grouping_keeps_every_photograph():
    trip = _trip(
        [
            _ev("a", "Titanic Memorial", at=0, media=["m1", "m2"]),
            _ev("b", "SS Nomadic", at=20, media=["m3"]),
            _ev("c", "Titanic Names Wall", at=40, media=["m4"]),
        ]
    )
    new_id = ops.group_events(trip, ["a", "b", "c"], "Titanic Quarter")
    grouped = trip.event_by_id(new_id)
    assert grouped is not None
    assert set(grouped.media_ids) == {"m1", "m2", "m3", "m4"}
    assert collect(trip) == []


def test_the_originals_are_hidden_not_deleted():
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=20), _ev("c", "C", at=40)])
    ops.group_events(trip, ["a", "b", "c"], "The quarter")
    for i in ("a", "b", "c"):
        e = trip.event_by_id(i)
        assert e is not None
        assert e.status is EventStatus.SUPPRESSED
        assert "grouped into" in (e.suppress_reason or "")


def test_the_group_spans_the_whole_run():
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=30), _ev("c", "C", at=60, minutes=20)])
    new_id = ops.group_events(trip, ["a", "b", "c"], "Everything")
    g = trip.event_by_id(new_id)
    assert g.start == T0
    assert g.end == T0 + timedelta(minutes=80)


def test_the_map_point_is_a_real_place_not_a_centroid():
    """A centroid drops a pin in the middle of a road. Use one of the actual stops."""
    trip = _trip(
        [
            _ev("a", "Plaque", at=0, lat=54.600),
            _ev("b", "Titanic Belfast", at=20, lat=54.608, media=["m1", "m2", "m3"]),
            _ev("c", "Bench", at=40, lat=54.601),
        ]
    )
    new_id = ops.group_events(trip, ["a", "b", "c"], "Titanic Quarter")
    g = trip.event_by_id(new_id)
    # Defaults to the stop with the most photographs.
    assert g.place.lat == 54.608
    assert g.place.name == "Titanic Belfast"


def test_an_explicit_representative_is_honoured():
    trip = _trip([_ev("a", "A", at=0, lat=1.0), _ev("b", "B", at=20, lat=2.0),
                  _ev("c", "C", at=40, lat=3.0)])
    new_id = ops.group_events(trip, ["a", "b", "c"], "Group", representative_id="c")
    assert trip.event_by_id(new_id).place.lat == 3.0


def test_a_group_survives_the_golden_rule():
    """A deliberate grouping must not be pruned away as a minor stop."""
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=20), _ev("c", "C", at=40)])
    new_id = ops.group_events(trip, ["a", "b", "c"], "Group")
    assert trip.event_by_id(new_id).user_pinned is True


def test_grouping_records_what_it_absorbed():
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=20), _ev("c", "C", at=40)])
    new_id = ops.group_events(trip, ["a", "b", "c"], "Group")
    refs = {r.ref for r in trip.event_by_id(new_id).provenance.absorbed}
    assert refs == {"a", "b", "c"}


def test_activities_with_tracks_are_never_grouped():
    hike = _ev("h", "Hike", at=0, etype=EventType.HIKE)
    hike.track_ids = ["trk"]
    hike.detail = ActivityDetail()
    trip = _trip([hike, _ev("a", "A", at=60), _ev("b", "B", at=80)])
    with pytest.raises(ops.OpError):
        ops.group_events(trip, ["h", "a", "b"], "Nope")


def test_grouping_needs_at_least_two_events():
    trip = _trip([_ev("a", "A", at=0)])
    with pytest.raises(ops.OpError):
        ops.group_events(trip, ["a"], "Nope")


def test_ungrouping_restores_the_originals():
    trip = _trip([_ev("a", "A", at=0, media=["m1"]), _ev("b", "B", at=20),
                  _ev("c", "C", at=40)])
    new_id = ops.group_events(trip, ["a", "b", "c"], "Group")
    ops.ungroup_event(trip, new_id)
    assert trip.event_by_id(new_id) is None
    for i in ("a", "b", "c"):
        assert trip.event_by_id(i).status is EventStatus.ACTIVE
    # The photographs go to the pool: only the user knows which stop they belonged to.
    assert "m1" in trip.unassigned_media_ids
    assert collect(trip) == []


def test_grouping_is_undoable():
    session = CurationSession(
        trip=_trip([_ev("a", "A", at=0, media=["m1"]), _ev("b", "B", at=20),
                    _ev("c", "C", at=40)])
    )
    session.apply(
        "group_events", {"event_ids": ["a", "b", "c"], "title": "Quarter"}
    )
    session.undo()
    assert trip_active(session.trip) == {"a", "b", "c"}
    assert session.trip.event_by_id("a").media_ids == ["m1"]
    assert collect(session.trip) == []


def trip_active(trip: Trip) -> set[str]:
    return {e.id for e in trip.events if e.status is EventStatus.ACTIVE}


# ============================================================================ A. group


def test_grouping_is_only_suggested_for_stops_that_are_actually_close():
    """The model names a group; geometry decides what a group is."""
    llm = FakeLlm({"title": "Titanic Quarter", "represents": "SS Nomadic",
                   "worthGrouping": True})
    near = _trip(
        [
            _ev("a", "Titanic Memorial", at=0, lat=54.6000),
            _ev("b", "SS Nomadic", at=20, lat=54.6010),
            _ev("c", "Titanic Names Wall", at=40, lat=54.6015),
        ]
    )
    assert sg.suggest_groups(llm, near)

    far = _trip(
        [
            _ev("a", "One", at=0, lat=54.60),
            _ev("b", "Two", at=20, lat=54.70),
            _ev("c", "Three", at=40, lat=54.80),
        ]
    )
    assert sg.suggest_groups(llm, far) == []


def test_a_group_title_may_not_invent_a_place():
    llm = FakeLlm({"title": "A morning in Atlantis", "represents": "A",
                   "worthGrouping": True})
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=20), _ev("c", "C", at=40)])
    assert sg.suggest_groups(llm, trip) == []


def test_the_model_can_decline_to_group():
    llm = FakeLlm({"title": "X", "represents": "A", "worthGrouping": False})
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=20), _ev("c", "C", at=40)])
    assert sg.suggest_groups(llm, trip) == []


def test_a_group_suggestion_carries_the_operation_to_apply_it():
    llm = FakeLlm({"title": "Titanic Quarter", "represents": "SS Nomadic",
                   "worthGrouping": True})
    trip = _trip(
        [
            _ev("a", "Titanic Memorial", at=0),
            _ev("b", "SS Nomadic", at=20),
            _ev("c", "Titanic Names Wall", at=40),
        ]
    )
    s = sg.suggest_groups(llm, trip)[0]
    assert s.ops[0]["op"] == "group_events"
    assert set(s.ops[0]["payload"]["event_ids"]) == {"a", "b", "c"}


# ============================================================================ B. demote


def test_a_stop_with_a_photograph_is_never_proposed_for_hiding():
    """A photograph is proof the traveller cared. No model confidence outranks it."""
    llm = FakeLlm({"keep": []})
    trip = _trip([_ev("a", "Layby", at=0, minutes=3, media=["m1"])])
    assert sg.suggest_demotions(llm, trip) == []


def test_brief_photoless_stops_are_proposed():
    llm = FakeLlm({"keep": []})
    trip = _trip([_ev("a", "Roundabout", at=0, minutes=3),
                  _ev("b", "Traffic lights", at=30, minutes=2)])
    out = sg.suggest_demotions(llm, trip)
    assert len(out) == 1
    assert {o["payload"]["event_id"] for o in out[0].ops} == {"a", "b"}


def test_the_model_can_spare_a_real_destination():
    llm = FakeLlm({"keep": [0]})
    trip = _trip([_ev("a", "Giant's Causeway", at=0, minutes=8),
                  _ev("b", "Layby", at=30, minutes=2)])
    out = sg.suggest_demotions(llm, trip)
    assert {o["payload"]["event_id"] for o in out[0].ops} == {"b"}


def test_a_long_stop_is_not_passing_through():
    llm = FakeLlm({"keep": []})
    trip = _trip([_ev("a", "Museum", at=0, minutes=90)])
    assert sg.suggest_demotions(llm, trip) == []


def test_the_net_widens_when_a_model_can_discriminate():
    """Without a model only the obvious cases; with one, the band the Golden Rule spared.

    Anything under PRUNE_MIN_DURATION_MIN was already suppressed unless it had a name, so
    the survivors in this band are exactly the ones geocoding lent a significance they may
    not deserve. Judging those needs a model.
    """
    trip = _trip([_ev("a", "Named junction", at=0, minutes=25)])
    assert sg.suggest_demotions(NullProvider(), trip) == []
    assert sg.suggest_demotions(FakeLlm({"keep": []}), trip)


def test_overnights_are_never_demoted():
    llm = FakeLlm({"keep": []})
    trip = _trip([_ev("a", "Hotel", at=0, minutes=5, etype=EventType.OVERNIGHT)])
    assert sg.suggest_demotions(llm, trip) == []


# ============================================================================ C. day title


def test_a_day_title_can_combine_what_the_day_was_for():
    llm = FakeLlm({"title": "Titanic Quarter, then Belfast city centre"})
    trip = _trip([_ev("a", "Titanic Quarter", at=0, minutes=120),
                  _ev("b", "Belfast", at=200, minutes=90)])
    out = sg.suggest_day_titles(llm, trip)
    assert out and "Titanic" in out[0].title
    assert out[0].ops[0]["op"] == "set_day_title"


def test_a_day_title_may_not_invent_a_place():
    llm = FakeLlm({"title": "A day in Narnia"})
    trip = _trip([_ev("a", "Belfast", at=0, minutes=120)])
    assert sg.suggest_day_titles(llm, trip) == []


def test_a_hand_written_day_title_is_left_alone():
    llm = FakeLlm({"title": "Something else"})
    trip = _trip([_ev("a", "Belfast", at=0, minutes=120)])
    trip.days[0].user_title = True
    assert sg.suggest_day_titles(llm, trip) == []


# ============================================================================ D. activity


def _hike_trip() -> Trip:
    hike = Event(
        id="h",
        day_id="d1",
        type=EventType.HIKE,
        start=T0,
        end=T0 + timedelta(hours=4),
        title="County Down Hiking",
        place=Place(name="County Down Hiking", lat=54.1, lon=-6.0,
                    source=PlaceSource.GPX, confidence=1.0),
        track_ids=["trk"],
        detail=ActivityDetail(
            stats=ActivityStats(distance_m=12000, ascent_m=645, descent_m=650,
                                max_ele_m=745, moving_time_s=10800),
            highlights=[
                TrackHighlight(name="Slieve Binnian", kind="natural=peak",
                               lat=54.11, lon=-6.01, ele_m=745.9, offset_m=8000),
                TrackHighlight(name="Blue Lough", kind="natural=water",
                               lat=54.12, lon=-6.02, offset_m=4400),
            ],
        ),
    )
    trip = _trip([hike])
    trip.tracks = [
        TrackMeta(id="trk", source_id="s", name="County Down Hiking", start=T0,
                  end=T0 + timedelta(hours=4))
    ]
    return trip


def test_an_activity_is_described_from_its_own_telemetry():
    llm = FakeLlm({"summary": "An out-and-back over Slieve Binnian, steep past Blue Lough."})
    out = sg.suggest_activity_shapes(llm, _hike_trip())
    assert out
    assert "Slieve Binnian" in out[0].title
    assert out[0].ops[0]["op"] == "set_summary"


def test_the_prompt_carries_the_numbers_the_model_needs():
    llm = FakeLlm({"summary": "Over Slieve Binnian."})
    sg.suggest_activity_shapes(llm, _hike_trip())
    prompt = llm.prompts[0]
    assert "12.0 km" in prompt and "645" in prompt and "Slieve Binnian" in prompt


def test_an_activity_description_may_not_invent_a_summit():
    llm = FakeLlm({"summary": "A fine loop over Ben Invented."})
    assert sg.suggest_activity_shapes(llm, _hike_trip()) == []


def test_an_activity_already_described_is_left_alone():
    llm = FakeLlm({"summary": "Something."})
    trip = _hike_trip()
    trip.events[0].summary = "Already written."
    assert sg.suggest_activity_shapes(llm, trip) == []


# ============================================================================ F. names


def test_a_tiebreak_picks_from_the_candidates():
    llm = FakeLlm({"choices": [{"index": 0, "name": "Titanic Belfast"}]})
    trip = _trip([_ev("a", "Dr William Drennan", at=0, minutes=90, confidence=0.6)])
    out = sg.suggest_place_names(
        llm, trip, candidates_for=lambda e: ["Dr William Drennan", "Titanic Belfast"]
    )
    assert out and out[0].title == "Titanic Belfast"
    assert out[0].ops[0]["op"] == "rename_event"


def test_tiebreaks_are_batched():
    """54 contested names on the reference trip; one request each exhausts a free tier."""
    llm = FakeLlm({"choices": []})
    events = [
        _ev(f"e{i}", f"Name {i}", at=i * 60, confidence=0.6, lat=54.0 + i)
        for i in range(30)
    ]
    sg.suggest_place_names(
        llm, _trip(events), candidates_for=lambda e: ["One", "Two"]
    )
    assert len(llm.prompts) <= 3, f"expected batching, made {len(llm.prompts)} calls"


def test_a_tiebreak_may_not_borrow_another_stops_option():
    """Each stop may only be renamed to one of ITS OWN candidates."""
    llm = FakeLlm({"choices": [{"index": 0, "name": "Somewhere Else"}]})
    trip = _trip([_ev("a", "A", at=0, confidence=0.6)])
    assert sg.suggest_place_names(llm, trip, candidates_for=lambda e: ["A", "B"]) == []


def test_confident_names_are_left_alone():
    llm = FakeLlm({"choices": [{"index": 0, "name": "B"}]})
    trip = _trip([_ev("a", "A", at=0, confidence=0.95)])
    assert sg.suggest_place_names(llm, trip, candidates_for=lambda e: ["A", "B"]) == []


# ============================================================================ no model


@pytest.mark.parametrize(
    "fn", [sg.suggest_groups, sg.suggest_day_titles, sg.suggest_activity_shapes]
)
def test_model_driven_suggestions_are_silent_without_a_model(fn):
    """The app stays fully usable with no key; those suggestions simply do not appear."""
    trip = _trip([_ev("a", "A", at=0), _ev("b", "B", at=20), _ev("c", "C", at=40)])
    assert fn(NullProvider(), trip) == []


def test_demotion_works_without_a_model():
    """Short, photograph-less and unremarkable is a deterministic rule.

    Gating a safe cleanup behind an API key would be silly; the model only ever pulls a
    real destination back out of the pile.
    """
    trip = _trip([_ev("a", "Roundabout", at=0, minutes=3),
                  _ev("b", "Layby", at=30, minutes=2)])
    out = sg.suggest_demotions(NullProvider(), trip)
    assert len(out) == 1
    assert {o["payload"]["event_id"] for o in out[0].ops} == {"a", "b"}


@pytest.mark.parametrize(
    "fn", [sg.suggest_groups, sg.suggest_day_titles, sg.suggest_activity_shapes]
)
def test_a_broken_model_degrades_quietly(fn):
    trip = _hike_trip()
    assert fn(FakeLlm(ok=False), trip) == []
