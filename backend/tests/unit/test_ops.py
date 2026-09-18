"""Curation operations and the session that applies them.

The two guarantees under test throughout:

* nothing is ever lost -- media and tracks survive every destructive operation;
* a user's edit is final -- re-deriving must not overwrite it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from trippo.capsule.session import CurationSession
from trippo.domain import ops
from trippo.domain.invariants import collect
from trippo.domain.models import (
    ActivityDetail,
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
    TrackMeta,
    Trip,
    UnknownDetail,
)
from trippo.domain.stats import compute_trip_stats
from trippo.domain.summarize import summarize

T0 = datetime(2023, 9, 25, 9, 0, tzinfo=UTC)


def _media(n: int) -> MediaAsset:
    return MediaAsset(
        id=f"m{n}",
        hash=f"h{n}",
        kind=MediaKind.PHOTO,
        filename=f"p{n}.jpg",
        normalized_filename=f"p{n}.jpg",
        captured_at=T0 + timedelta(minutes=n * 3),
        thumb_ref=f"media/thumb/h{n}.webp",
    )


def _trip() -> Trip:
    media = [_media(i) for i in range(6)]
    a = Event(
        id="a",
        day_id="d1",
        type=EventType.VISIT,
        start=T0,
        end=T0 + timedelta(hours=1),
        place=Place(name="Kylemore Abbey", lat=53.5, lon=-9.9, source=PlaceSource.OSM,
                    confidence=0.9),
        title="Kylemore Abbey",
        media_ids=["m0", "m1", "m2"],
        selected_media_ids=["m0", "m1"],
        detail=PlaceDetail(),
    )
    b = Event(
        id="b",
        day_id="d1",
        type=EventType.HIKE,
        start=T0 + timedelta(hours=2),
        end=T0 + timedelta(hours=5),
        place=Place(name="Diamond Hill", lat=53.55, lon=-9.95, source=PlaceSource.OSM,
                    confidence=0.9),
        title="Diamond Hill",
        media_ids=["m3", "m4"],
        track_ids=["trk"],
        detail=ActivityDetail(),
    )
    gap = Event(
        id="g",
        day_id="d2",
        type=EventType.UNKNOWN,
        start=T0 + timedelta(days=1),
        end=T0 + timedelta(days=1, hours=20),
        media_ids=["m5"],
        detail=UnknownDetail(gap_hours=20, displacement_km=900,
                             candidate_types=[EventType.FERRY]),
    )
    d1 = Day(id="d1", index=1, date=date(2023, 9, 25), event_ids=["a", "b"])
    d2 = Day(id="d2", index=2, date=date(2023, 9, 26), event_ids=["g"])
    trip = Trip(
        id="t",
        title="Ireland",
        date_range=DateRange(start=d1.date, end=d2.date),
        created_at=T0,
        updated_at=T0,
        days=[d1, d2],
        events=[a, b, gap],
        media=media,
        tracks=[
            TrackMeta(id="trk", source_id="s", name="Diamond Hill",
                      start=T0 + timedelta(hours=2), end=T0 + timedelta(hours=5))
        ],
    )
    summarize(trip)
    trip.stats = compute_trip_stats(trip)
    return trip


@pytest.fixture
def session() -> CurationSession:
    return CurationSession(trip=_trip())


def _ids(trip: Trip) -> set[str]:
    """Every media id accounted for, wherever it lives."""
    owned = {m for e in trip.events if e.status is EventStatus.ACTIVE for m in e.media_ids}
    return owned | set(trip.unassigned_media_ids)


# --------------------------------------------------------------------------- naming


def test_renaming_marks_the_place_as_the_users_and_survives_rederivation(session):
    session.apply("rename_event", {"event_id": "a", "name": "The Abbey"})
    e = session.trip.event_by_id("a")
    assert e.place.source is PlaceSource.USER
    assert e.place.confidence == 1.0
    # Enrichment treats USER as final (ADR-0008); re-deriving must not undo it either.
    summarize(session.trip)
    assert session.trip.event_by_id("a").title == "The Abbey"


def test_an_empty_name_is_rejected(session):
    with pytest.raises(ops.OpError):
        session.apply("rename_event", {"event_id": "a", "name": "   "})


# --------------------------------------------------------------------------- type


def test_changing_type_keeps_the_photographs(session):
    session.apply("set_event_type", {"event_id": "a", "type": "overnight"})
    e = session.trip.event_by_id("a")
    assert e.type is EventType.OVERNIGHT
    assert e.media_ids == ["m0", "m1", "m2"]


def test_resolving_a_gap_keeps_its_photographs_and_asserts_no_route(session):
    """59 photographs of the Bay of Biscay must survive becoming a ferry."""
    session.apply(
        "resolve_gap",
        {"event_id": "g", "type": "ferry", "name": "Rosslare \u2192 Bilbao"},
    )
    e = session.trip.event_by_id("g")
    assert e.type is EventType.FERRY
    assert e.media_ids == ["m5"]
    assert e.title == "Rosslare \u2192 Bilbao"
    # The user saying it was a ferry does not tell us the route it took.
    assert e.geometry is None or e.geometry.polyline is None


def test_only_a_gap_can_be_resolved(session):
    with pytest.raises(ops.OpError):
        session.apply("resolve_gap", {"event_id": "a", "type": "ferry"})


# --------------------------------------------------------------------------- lifecycle


def test_deleting_an_event_never_deletes_a_photograph(session):
    before = _ids(session.trip)
    session.apply("delete_event", {"event_id": "a"})
    assert session.trip.event_by_id("a") is None
    assert _ids(session.trip) == before
    assert {"m0", "m1", "m2"} <= set(session.trip.unassigned_media_ids)


def test_deleting_an_event_returns_its_track_to_the_pool(session):
    session.apply("delete_event", {"event_id": "b"})
    assert "trk" in session.trip.unassigned_track_ids


def test_suppressing_keeps_the_event_and_frees_its_media(session):
    before = _ids(session.trip)
    session.apply("suppress_event", {"event_id": "a"})
    e = session.trip.event_by_id("a")
    assert e is not None and e.status is EventStatus.SUPPRESSED
    assert _ids(session.trip) == before


def test_restoring_pins_the_event_so_pruning_cannot_hide_it_again(session):
    session.apply("suppress_event", {"event_id": "a"})
    session.apply("restore_event", {"event_id": "a"})
    e = session.trip.event_by_id("a")
    assert e.status is EventStatus.ACTIVE
    assert e.user_pinned is True


def test_adding_an_event_lands_on_the_right_day(session):
    session.apply("add_event", {"day_id": "d1", "type": "stop", "title": "Roadside cross"})
    day = session.trip.day_by_id("d1")
    added = [session.trip.event_by_id(i) for i in day.event_ids]
    assert any(e.title == "Roadside cross" for e in added)
    assert collect(session.trip) == []


# --------------------------------------------------------------------------- days


def test_excluding_a_day_renumbers_the_rest_and_keeps_media(session):
    before = _ids(session.trip)
    session.apply("set_day_excluded", {"day_id": "d1", "excluded": True})
    remaining = [d.index for d in session.trip.days if not d.excluded]
    assert remaining == [1]
    assert _ids(session.trip) == before


def test_including_a_day_again_restores_it(session):
    session.apply("set_day_excluded", {"day_id": "d1", "excluded": True})
    session.apply("set_day_excluded", {"day_id": "d1", "excluded": False})
    assert [d.index for d in session.trip.days if not d.excluded] == [1, 2]


def test_a_hand_written_day_title_is_not_overwritten(session):
    session.apply("set_day_title", {"day_id": "d1", "title": "The day it rained"})
    summarize(session.trip)
    assert session.trip.day_by_id("d1").title == "The day it rained"


# --------------------------------------------------------------------------- media


def test_moving_photographs_between_events(session):
    session.apply("move_media", {"media_ids": ["m0"], "target_event_id": "b"})
    assert "m0" not in session.trip.event_by_id("a").media_ids
    assert "m0" in session.trip.event_by_id("b").media_ids
    assert collect(session.trip) == []


def test_moving_photographs_to_the_pool(session):
    session.apply("move_media", {"media_ids": ["m0", "m1"], "target_event_id": None})
    assert {"m0", "m1"} <= set(session.trip.unassigned_media_ids)
    assert collect(session.trip) == []


def test_a_photograph_can_only_be_owned_once(session):
    session.apply("move_media", {"media_ids": ["m0"], "target_event_id": "b"})
    session.apply("move_media", {"media_ids": ["m0"], "target_event_id": "a"})
    owners = [e.id for e in session.trip.events if "m0" in e.media_ids]
    assert owners == ["a"]


def test_curating_the_selection_freezes_it(session):
    session.apply("set_selected_media", {"event_id": "a", "media_ids": ["m2"]})
    e = session.trip.event_by_id("a")
    assert e.selected_media_ids == ["m2"]
    assert e.user_selected_media is True
    summarize(session.trip)  # would normally recompute the selection
    assert session.trip.event_by_id("a").selected_media_ids == ["m2"]


def test_cannot_select_a_photograph_the_event_does_not_own(session):
    with pytest.raises(ops.OpError):
        session.apply("set_selected_media", {"event_id": "a", "media_ids": ["m5"]})


def test_attaching_a_track_moves_it_off_its_previous_event(session):
    session.apply("detach_track", {"event_id": "b", "track_id": "trk"})
    assert "trk" in session.trip.unassigned_track_ids
    session.apply("attach_track", {"event_id": "a", "track_id": "trk"})
    assert session.trip.event_by_id("a").track_ids == ["trk"]
    assert "trk" not in session.trip.unassigned_track_ids
    assert collect(session.trip) == []


# --------------------------------------------------------------------------- session


def test_undo_and_redo_round_trip(session):
    original = session.trip.event_by_id("a").title
    session.apply("rename_event", {"event_id": "a", "name": "Changed"})
    assert session.undo() is True
    assert session.trip.event_by_id("a").title == original
    assert session.redo() is True
    assert session.trip.event_by_id("a").title == "Changed"


def test_undo_restores_deleted_events_and_their_photographs(session):
    session.apply("delete_event", {"event_id": "a"})
    session.undo()
    e = session.trip.event_by_id("a")
    assert e is not None
    assert e.media_ids == ["m0", "m1", "m2"]
    assert collect(session.trip) == []


def test_a_new_operation_clears_the_redo_stack(session):
    session.apply("rename_event", {"event_id": "a", "name": "One"})
    session.undo()
    session.apply("rename_event", {"event_id": "a", "name": "Two"})
    assert session.can_redo is False


def test_undo_on_an_untouched_session_is_a_no_op(session):
    assert session.undo() is False


def test_a_rejected_operation_leaves_the_capsule_unchanged(session):
    before = session.trip.model_dump(mode="json")
    with pytest.raises(ops.OpError):
        session.apply("set_selected_media", {"event_id": "a", "media_ids": ["m5"]})
    assert session.trip.model_dump(mode="json") == before
    assert session.can_undo is False, "a failed operation must not enter the history"


def test_an_unknown_operation_is_rejected(session):
    with pytest.raises(ops.OpError):
        session.apply("drop_database", {})


def test_invariants_hold_after_a_long_sequence_of_edits(session):
    """The property that matters: no sequence of curation can corrupt ownership."""
    session.apply("move_media", {"media_ids": ["m0"], "target_event_id": "b"})
    session.apply("suppress_event", {"event_id": "b"})
    session.apply("restore_event", {"event_id": "b"})
    session.apply("set_event_type", {"event_id": "a", "type": "overnight"})
    session.apply("delete_event", {"event_id": "a"})
    session.apply("add_event", {"day_id": "d1", "title": "Replacement"})
    session.apply("set_day_excluded", {"day_id": "d2", "excluded": True})
    session.undo()
    session.undo()
    assert collect(session.trip) == []
    assert _ids(session.trip) == {f"m{i}" for i in range(6)}


def test_derived_data_is_refreshed_after_every_operation(session):
    session.apply("rename_event", {"event_id": "b", "name": "Benbaun"})
    # The day title is derived from its most significant named event.
    assert session.trip.day_by_id("d1").title == "Benbaun"
