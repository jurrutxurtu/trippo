"""AI layer: coherence checks, output validation, and suggestions with a fake model.

No network. The real provider is exercised only by its availability check -- everything
else here is about the guard rails, which is where the risk actually lives.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from trippo.ai import suggest as s
from trippo.ai.coherence import Severity, check_trip
from trippo.ai.validators import (
    choice_is_offered,
    invented_names,
    is_grounded,
    proper_nouns,
    within_length,
)
from trippo.domain.models import (
    DateRange,
    Day,
    Event,
    EventType,
    MediaAsset,
    MediaKind,
    Place,
    PlaceDetail,
    PlaceSource,
    Trip,
    UnknownDetail,
)
from trippo.domain.summarize import summarize
from trippo.ports.llm import LlmResponse, NullProvider

T0 = datetime(2023, 9, 25, 9, 0, tzinfo=UTC)


class FakeLlm:
    """Returns whatever it is told to, so validators can be tested in isolation."""

    name = "fake"
    available = True

    def __init__(self, data: dict[str, Any] | None = None, ok: bool = True) -> None:
        self._data = data or {}
        self._ok = ok
        self.calls = 0

    def complete(self, *, system: str, prompt: str, schema: dict) -> LlmResponse:
        self.calls += 1
        return LlmResponse(data=self._data, ok=self._ok)


def _trip(*, gap: bool = False, unassigned: int = 0) -> Trip:
    ev = Event(
        id="a",
        day_id="d1",
        type=EventType.VISIT,
        start=T0,
        end=T0 + timedelta(hours=2),
        title="Kylemore Abbey",
        place=Place(name="Kylemore Abbey", lat=53.5, lon=-9.9, source=PlaceSource.OSM,
                    confidence=0.95),
        detail=PlaceDetail(),
    )
    events = [ev]
    days = [Day(id="d1", index=1, date=date(2023, 9, 25), event_ids=["a"])]
    if gap:
        events.append(
            Event(
                id="g",
                day_id="d1",
                type=EventType.UNKNOWN,
                start=T0 + timedelta(hours=3),
                end=T0 + timedelta(hours=23),
                detail=UnknownDetail(gap_hours=20, displacement_km=900),
            )
        )
        days[0].event_ids.append("g")

    media = [
        MediaAsset(id=f"m{i}", hash=f"h{i}", kind=MediaKind.PHOTO,
                   filename=f"p{i}.jpg", normalized_filename=f"p{i}.jpg")
        for i in range(unassigned)
    ]
    trip = Trip(
        id="t",
        title="Ireland",
        date_range=DateRange(start=days[0].date, end=days[0].date),
        created_at=T0,
        updated_at=T0,
        days=days,
        events=events,
        media=media,
        unassigned_media_ids=[m.id for m in media],
    )
    summarize(trip)
    return trip


# --------------------------------------------------------------------------- coherence


def test_an_unaccounted_gap_blocks_a_finished_trip():
    findings = check_trip(_trip(gap=True))
    blocking = [f for f in findings if f.severity is Severity.BLOCKING]
    assert len(blocking) == 1
    assert blocking[0].code == "unaccounted_gap"
    assert blocking[0].action


def test_a_clean_trip_has_nothing_blocking():
    assert not [f for f in check_trip(_trip()) if f.severity is Severity.BLOCKING]


def test_photographs_in_the_pool_are_flagged_but_do_not_block():
    findings = check_trip(_trip(unassigned=3))
    pool = [f for f in findings if f.code == "unassigned_media"]
    assert len(pool) == 1
    assert pool[0].severity is Severity.WARNING


def test_findings_are_ordered_by_severity():
    findings = check_trip(_trip(gap=True, unassigned=2))
    severities = [f.severity for f in findings]
    assert severities == sorted(
        severities, key=lambda x: {"blocking": 0, "warning": 1, "info": 2}[x.value]
    )


def test_an_empty_day_is_flagged():
    trip = _trip()
    trip.days.append(Day(id="d2", index=2, date=date(2023, 9, 26)))
    assert any(f.code == "empty_day" for f in check_trip(trip))


def test_an_excluded_day_is_not_flagged_as_empty():
    trip = _trip()
    trip.days.append(Day(id="d2", index=2, date=date(2023, 9, 26), excluded=True))
    assert not any(f.code == "empty_day" for f in check_trip(trip))


# --------------------------------------------------------------------------- validators


def test_sentence_initial_capitals_are_not_treated_as_names():
    assert "Walked" not in proper_nouns("Walked up to the col. Rain all afternoon.")


def test_a_real_place_name_is_detected():
    assert "Glendalough" in proper_nouns("We reached Glendalough by noon.")


def test_invention_is_caught():
    invented = invented_names(
        "A fine walk from Glendalough up to Mount Fictional.",
        ["Glendalough", "Upper Lake"],
    )
    assert "Fictional" in invented or "Mount" in invented


def test_a_grounded_paraphrase_passes():
    """Matching is loose on purpose: a substring of a known name is still grounded."""
    assert is_grounded(
        "Above Glendalough, with the Upper Lake below.",
        ["Glendalough Round Tower", "Upper Lake"],
    )


def test_length_limits_are_enforced():
    assert within_length("short", 20)
    assert not within_length("x" * 30, 20)


def test_a_disambiguation_must_pick_from_the_list():
    assert choice_is_offered("Glendalough", ["Glendalough", "Glendalough Hotel"])
    assert not choice_is_offered("Somewhere Else", ["Glendalough"])


# --------------------------------------------------------------------------- suggestions


def test_every_suggestion_is_none_without_a_model():
    """The app must be completely usable with no key -- features hide, nothing breaks."""
    llm = NullProvider()
    trip = _trip()
    assert s.suggest_day_title(llm, trip, "d1") is None
    assert s.suggest_trip_summary(llm, trip) is None
    assert s.polish_note(llm, "rough note") is None
    assert s.pick_place_label(llm, ["a", "b"], context="") is None


def test_a_day_title_suggestion_returns_options():
    llm = FakeLlm({"titles": ["Kylemore Abbey", "Abbey and lake", "A day at Kylemore"]})
    out = s.suggest_day_title(llm, _trip(), "d1")
    assert out is not None
    assert out.value == "Kylemore Abbey"
    assert len(out.alternatives) == 2


def test_an_invented_title_is_rejected():
    """The whole point: the model may phrase, never invent."""
    llm = FakeLlm({"titles": ["A morning at Castle Nonexistent"]})
    assert s.suggest_day_title(llm, _trip(), "d1") is None


def test_an_over_long_title_is_rejected():
    llm = FakeLlm({"titles": ["Kylemore Abbey " * 20]})
    assert s.suggest_day_title(llm, _trip(), "d1") is None


def test_a_failed_model_call_degrades_to_none():
    assert s.suggest_day_title(FakeLlm(ok=False), _trip(), "d1") is None


def test_polishing_a_note_may_not_rewrite_it():
    note = "steep from the saddle, hail at the top"
    llm = FakeLlm({"text": "A" * 500})
    assert s.polish_note(llm, note) is None


def test_polishing_keeps_a_reasonable_result():
    llm = FakeLlm({"text": "Steep from the saddle. Hail at the top."})
    out = s.polish_note(llm, "steep from the saddle, hail at the top")
    assert out is not None
    assert "saddle" in out.value


def test_a_tiebreak_may_not_invent_an_option():
    llm = FakeLlm({"choice": "Something Entirely Different"})
    assert s.pick_place_label(llm, ["Glendalough", "Glendalough Hotel"], context="") is None


def test_a_tiebreak_returns_the_chosen_option():
    llm = FakeLlm({"choice": "Glendalough"})
    out = s.pick_place_label(llm, ["Glendalough", "Glendalough Hotel"], context="45 min stop")
    assert out is not None
    assert out.value == "Glendalough"


def test_contested_events_are_listed_for_review():
    trip = _trip()
    trip.events[0].place.confidence = 0.6
    assert s.contested_events(trip) == ["a"]


@pytest.mark.parametrize("kind", ["day_title", "trip_summary"])
def test_suggestions_never_raise_on_a_broken_model(kind):
    class Broken:
        name = "broken"
        available = True

        def complete(self, **_kw):
            return LlmResponse(ok=False, error="boom")

    trip = _trip()
    fn = s.suggest_day_title if kind == "day_title" else s.suggest_trip_summary
    assert (fn(Broken(), trip, "d1") if kind == "day_title" else fn(Broken(), trip)) is None
