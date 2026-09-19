"""The curation phase: the agenda, and the draft-to-agreed lifecycle.

A capsule exists the moment ingestion finishes, but it is a machine's guess until someone
has been through it. These cover the queue that guides that pass, and the state that
records it happened.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from trippo.ai.agenda import Kind, blocking_count, build_agenda
from trippo.capsule.session import CurationSession
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
    TripStatus,
    UnknownDetail,
)
from trippo.domain.stats import compute_trip_stats
from trippo.domain.summarize import summarize

T0 = datetime(2024, 4, 2, 9, 0, tzinfo=UTC)


def _trip(*, gap=False, contested=False, pool=0, empty_day=False) -> Trip:
    events = [
        Event(
            id="a",
            day_id="d1",
            type=EventType.VISIT,
            start=T0,
            end=T0 + timedelta(hours=2),
            title="Jemaa el-Fnaa",
            place=Place(
                name="Jemaa el-Fnaa",
                lat=31.62,
                lon=-7.99,
                source=PlaceSource.OSM,
                confidence=0.6 if contested else 0.95,
                category="tourism=attraction",
            ),
            media_ids=["m0"],
            detail=PlaceDetail(),
        )
    ]
    days = [Day(id="d1", index=1, date=date(2024, 4, 2), event_ids=["a"])]

    if gap:
        events.append(
            Event(
                id="g",
                day_id="d1",
                type=EventType.UNKNOWN,
                start=T0 + timedelta(hours=3),
                end=T0 + timedelta(hours=20),
                media_ids=["m1"],
                detail=UnknownDetail(
                    gap_hours=17,
                    displacement_km=520,
                    candidate_types=[EventType.DRIVE, EventType.FERRY],
                ),
            )
        )
        days[0].event_ids.append("g")

    if empty_day:
        days.append(Day(id="d2", index=2, date=date(2024, 4, 3)))

    media = [
        MediaAsset(
            id=f"m{i}",
            hash=f"h{i}",
            kind=MediaKind.PHOTO,
            filename=f"p{i}.jpg",
            normalized_filename=f"p{i}.jpg",
            captured_at=T0 + timedelta(minutes=i),
            thumb_ref=f"media/thumb/h{i}.webp",
        )
        for i in range(2 + pool)
    ]
    trip = Trip(
        id="t",
        title="Morocco",
        date_range=DateRange(start=days[0].date, end=days[-1].date),
        created_at=T0,
        updated_at=T0,
        days=days,
        events=events,
        media=media,
        unassigned_media_ids=[f"m{2 + i}" for i in range(pool)]
        + ([] if gap else ["m1"]),
    )
    summarize(trip)
    trip.stats = compute_trip_stats(trip)
    return trip


# --------------------------------------------------------------------------- lifecycle


def test_a_fresh_trip_is_a_draft():
    """Ingestion produces a guess, not an agreement."""
    assert _trip().status is TripStatus.DRAFT


def test_finishing_records_that_a_human_went_through_it():
    session = CurationSession(trip=_trip())
    session.apply("finalise", {})
    assert session.trip.status is TripStatus.CURATED
    assert session.trip.curated_at is not None


def test_finishing_locks_nothing():
    """The point is to record agreement, not to freeze the trip."""
    session = CurationSession(trip=_trip())
    session.apply("finalise", {})
    session.apply("rename_event", {"event_id": "a", "name": "The square"})
    assert session.trip.event_by_id("a").title == "The square"


def test_a_trip_can_be_reopened():
    session = CurationSession(trip=_trip())
    session.apply("finalise", {})
    session.apply("reopen", {})
    assert session.trip.status is TripStatus.DRAFT
    assert session.trip.curated_at is None


def test_finishing_is_undoable():
    session = CurationSession(trip=_trip())
    session.apply("finalise", {})
    session.undo()
    assert session.trip.status is TripStatus.DRAFT


# --------------------------------------------------------------------------- agenda


def test_an_unaccounted_gap_is_a_decision_not_a_defect():
    """It is a question only the traveller can answer, so nothing finishes while it is open."""
    items = build_agenda(_trip(gap=True))
    gaps = [i for i in items if i.code == "unaccounted_gap"]
    assert len(gaps) == 1
    assert gaps[0].kind is Kind.DECIDE
    assert blocking_count(items) == 1


def test_a_gap_offers_the_conversions_the_data_suggests():
    item = next(i for i in build_agenda(_trip(gap=True)) if i.code == "unaccounted_gap")
    ops = {a["op"] for a in item.actions}
    labels = " ".join(a["label"] for a in item.actions)
    assert "resolve_gap" in ops
    assert "drive" in labels and "ferry" in labels
    # And always a way to say "I do not know either".
    assert any(a.get("dismiss") for a in item.actions)


def test_a_gap_mentions_the_photographs_inside_it():
    item = next(i for i in build_agenda(_trip(gap=True)) if i.code == "unaccounted_gap")
    assert item.media_count == 1
    assert "photograph" in item.detail


def test_a_clean_trip_blocks_nothing():
    assert blocking_count(build_agenda(_trip())) == 0


def test_photographs_in_the_pool_are_a_check_not_a_decision():
    items = build_agenda(_trip(pool=3))
    pool = [i for i in items if i.code == "unassigned_media"]
    assert len(pool) == 1
    assert pool[0].kind is Kind.CHECK


def test_an_empty_day_offers_to_be_excluded():
    items = build_agenda(_trip(empty_day=True))
    empty = next(i for i in items if i.code == "empty_day")
    assert empty.kind is Kind.CHECK
    assert any(a["op"] == "set_day_excluded" for a in empty.actions)


def test_a_contested_name_is_optional_polish():
    items = build_agenda(_trip(contested=True))
    name = next(i for i in items if i.code == "contested_place")
    assert name.kind is Kind.POLISH
    assert name.event_id == "a"


def test_generated_day_titles_are_offered_for_rewording():
    items = build_agenda(_trip())
    assert any(i.code == "day_title" for i in items)


def test_a_hand_written_day_title_is_not_raised_again():
    session = CurationSession(trip=_trip())
    session.apply("set_day_title", {"day_id": "d1", "title": "Marrakesh, slowly"})
    items = build_agenda(session.trip)
    assert not [i for i in items if i.code == "day_title" and i.day_id == "d1"]


def test_decisions_come_before_checks_and_polish():
    """The queue has to put the irreplaceable judgement first, or it reads as a chore."""
    items = build_agenda(_trip(gap=True, contested=True, pool=2, empty_day=True))
    order = [i.kind for i in items]
    assert order[0] is Kind.DECIDE
    first_polish = next(i for i, k in enumerate(order) if k is Kind.POLISH)
    last_decide = max(i for i, k in enumerate(order) if k is Kind.DECIDE)
    assert last_decide < first_polish


def test_resolving_a_gap_removes_it_from_the_agenda():
    session = CurationSession(trip=_trip(gap=True))
    assert blocking_count(build_agenda(session.trip)) == 1
    session.apply("resolve_gap", {"event_id": "g", "type": "drive"})
    assert blocking_count(build_agenda(session.trip)) == 0


def test_agenda_items_carry_enough_to_act_on():
    for item in build_agenda(_trip(gap=True, contested=True, pool=1, empty_day=True)):
        assert item.id and item.title
        assert item.kind in (Kind.DECIDE, Kind.CHECK, Kind.POLISH)


@pytest.mark.parametrize("kind", [Kind.DECIDE, Kind.CHECK, Kind.POLISH])
def test_every_kind_appears_when_it_should(kind):
    items = build_agenda(_trip(gap=True, contested=True, pool=2))
    assert any(i.kind is kind for i in items)
