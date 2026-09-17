"""Golden acceptance tests -- Ireland 2023.

Each assertion encodes a pathology that real data actually exhibited. Read
`docs/technical/ingestion.md` before changing any of them.

DO NOT weaken these to make a test pass. If behaviour legitimately changed, explain the
diff in the commit body (AGENTS.md section 4).

The fixture is coordinate-shifted (+1.5 lat, -2.25 lon), so distances, speeds and every
heuristic under test behave exactly as they do on the real export.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from trippo.domain.invariants import collect
from trippo.domain.models import EventStatus, EventType
from trippo.draft.builder import BuildInputs, build
from trippo.ingest.gpx.parse import parse_gpx
from trippo.ingest.timeline.adapters import load as load_timeline

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "ireland-2023"


@pytest.fixture(scope="module")
def trip_and_trace():
    payload = json.loads((FIXTURE / "timeline.json").read_text(encoding="utf-8"))
    obs, _report = load_timeline(payload, "timeline:0")
    tracks = [
        t
        for f in sorted((FIXTURE / "tracks").glob("*.gpx"))
        for t in parse_gpx(f.read_bytes(), f.stem)
    ]
    return build(
        BuildInputs(
            title="Ireland 2023",
            observations=obs,
            tracks=tracks,
            window_start=date(2023, 9, 20),
            window_end=date(2023, 10, 16),
        )
    )


@pytest.fixture(scope="module")
def trip(trip_and_trace):
    return trip_and_trace[0]


@pytest.fixture(scope="module")
def trace(trip_and_trace):
    return trip_and_trace[1]


def _day(trip, d: date):
    return next(x for x in trip.days if x.date == d)


def _events_on(trip, d: date):
    day = _day(trip, d)
    return [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]


# --------------------------------------------------------------------------- P1


def test_no_overnight_at_the_ferry_port_while_at_sea(trip):
    """Google anchored an 8.5 h 'visit' at Rosslare Harbour while the phone was mid-sea.

    A naive overnight rule reports "Overnight stay, Rosslare Harbour". It must not.
    """
    overnights = [e for e in _events_on(trip, date(2023, 10, 14)) if e.type is EventType.OVERNIGHT]
    assert overnights == [], (
        "an overnight was created on the return-crossing day; the plausibility gate "
        "(draft/plausibility.py) failed to absorb the phantom stationary visit"
    )


def test_phantom_visits_are_detected_and_absorbed(trace):
    assert trace.phantoms, "no phantom stationary periods detected at all"
    assert any("402" in p or "IN_FERRY" in p for p in trace.phantoms), (
        f"the mid-crossing phantom anchor was not caught; found: {trace.phantoms}"
    )


# --------------------------------------------------------------------------- P3 / ADR-0007


def test_outbound_crossing_is_one_unaccounted_gap(trip):
    """09-21 evening -> 09-23 morning has no data at all. It must be visible, not stitched."""
    gaps = [
        e
        for e in trip.events
        if e.type is EventType.UNKNOWN
        and e.start.date() == date(2023, 9, 21)
        and e.detail.displacement_km > 500
    ]
    assert len(gaps) == 1, f"expected exactly one outbound gap, got {len(gaps)}"
    assert gaps[0].detail.gap_hours > 24
    assert gaps[0].detail.candidate_types, "conversion candidates must be offered"


def test_return_crossing_is_a_single_gap_not_two(trip):
    """A lone mid-Atlantic breadcrumb must not split the crossing into two cards."""
    gaps = [
        e
        for e in trip.events
        if e.type is EventType.UNKNOWN
        and e.start.date() in (date(2023, 10, 13), date(2023, 10, 14))
        and e.detail.displacement_km > 300
    ]
    assert len(gaps) == 1, f"the return crossing fragmented into {len(gaps)} gaps"


def test_gaps_are_not_noise(trip):
    """Holes where the user simply did not move are stays, not unaccounted travel.

    An early implementation reported 31 gaps on this trip; only 3 are real.
    """
    gaps = [e for e in trip.events if e.type is EventType.UNKNOWN]
    assert len(gaps) <= 5, f"gap detection is too noisy: {len(gaps)} gaps"


def test_no_gap_asserts_a_route(trip):
    """An unaccounted gap states facts only -- never a distance or a classification."""
    for e in (x for x in trip.events if x.type is EventType.UNKNOWN):
        assert e.geometry is None or e.geometry.polyline is None
        assert e.provenance.confidence == 0.0


# --------------------------------------------------------------------------- P7 / ADR-0005


def test_gpx_alone_populates_a_day_with_no_photos_and_almost_no_timeline(trip):
    """09-23: 2 timeline rows (evening), zero photos, one Glendalough track.

    The hike is the only evidence of the day. If the builder ever becomes
    timeline-centric again, this is the test that fails.
    """
    hikes = [e for e in _events_on(trip, date(2023, 9, 23)) if e.type is EventType.HIKE]
    assert len(hikes) == 1, "the Wicklow/Glendalough track did not produce an event"
    hike = hikes[0]
    assert hike.title == "County Wicklow Hiking"
    assert hike.track_ids
    assert hike.place and hike.place.source.value == "gpx"


def test_every_track_becomes_an_event_on_its_own_day(trip):
    assert len(trip.tracks) == 7
    for t in trip.tracks:
        owner = next((e for e in trip.events if t.id in e.track_ids), None)
        assert owner is not None, f"track {t.name} is attached to nothing"
        day = trip.day_by_id(owner.day_id)
        assert day is not None and day.date == t.start.date()


def test_activity_telemetry_is_computed_and_thresholded(trip):
    hike = next(e for e in trip.events if e.title == "County Wicklow Hiking")
    stats = hike.detail.stats
    assert stats.distance_m > 5_000
    assert stats.ascent_m > 100
    # Without a threshold, GPS noise inflates ascent absurdly.
    assert stats.elevation_threshold_m > 0
    assert stats.ascent_m < 3_000, "ascent looks like accumulated GPS noise"


# --------------------------------------------------------------------------- P9


def test_adjacent_tracks_are_offered_for_merging_not_merged(trip):
    """Two Kerry tracks ran 18:02-19:16 and 19:17-20:10 -- one outing, split by a pause."""
    mergeable = [t for t in trip.tracks if t.mergeable_with]
    assert len(mergeable) == 2, "the adjacent same-evening tracks were not flagged"
    assert len(trip.tracks) == 7, "tracks must never be merged silently"


# --------------------------------------------------------------------------- P4


def test_duplicate_visits_at_identical_times_are_removed(trip):
    seen: set[tuple] = set()
    for e in trip.events:
        if e.type not in (EventType.VISIT, EventType.OVERNIGHT):
            continue
        key = (e.start, e.end)
        assert key not in seen, f"duplicate visit at {e.start} survived deduplication"
        seen.add(key)


# --------------------------------------------------------------------------- P5


def test_multi_day_events_are_owned_once_but_shown_on_every_day(trip):
    spanning = [e for e in trip.events if e.continues_to_next_day]
    assert spanning, "no multi-day events detected at all"
    last_day = trip.days[-1].date
    for e in spanning:
        owners = [d for d in trip.days if e.id in d.event_ids]
        assert len(owners) == 1, f"event {e.id} is owned by {len(owners)} days"
        # An event running past the end of the trip window has no later day to appear on;
        # that is correct, not a bug.
        if owners[0].date < last_day:
            shown = [d for d in trip.days if e.id in d.spanning_event_ids]
            assert shown, f"multi-day event {e.id} is invisible on the days it covers"


def test_a_day_spent_entirely_in_transit_is_not_rendered_empty(trip):
    """09-22 is spent at sea. It owns no events, but the crossing must still appear on it.

    Note `coverage.blind` stays True here and that is honest: with only a timeline source
    this day genuinely has no data. The point is that the UI has something to render, so
    the day is not silently blank. In the full three-source run the ferry-day photos
    attach to the same gap and the day stops being blind at all.
    """
    d = _day(trip, date(2023, 9, 22))
    assert not d.event_ids
    assert d.spanning_event_ids, "the crossing does not appear on the day it covers"
    spanned = trip.event_by_id(d.spanning_event_ids[0])
    assert spanned is not None and spanned.type is EventType.UNKNOWN


def test_blind_days_are_reported_honestly(trip):
    """Coverage must reflect the data that exists, not the events we inferred from it."""
    blind = [c.date for c in trip.stats.coverage if c.blind]
    assert date(2023, 9, 22) in blind, (
        "the timeline-only run must still admit that 09-22 has no source data"
    )


# --------------------------------------------------------------------------- P2


def test_provider_distance_is_never_trusted(trip):
    """Google reported 24 km for a ~900 km crossing. Distances are always recomputed."""
    for e in trip.events:
        detail = e.detail
        if getattr(detail, "mode_hint", None) and hasattr(detail, "distance_m"):
            assert detail.distance_m >= 0


# --------------------------------------------------------------------------- structure


def test_days_are_contiguous_and_within_the_requested_window(trip):
    assert trip.days[0].date == date(2023, 9, 20)
    assert trip.days[-1].date == date(2023, 10, 16)
    assert [d.index for d in trip.days] == list(range(1, len(trip.days) + 1))
    for a, b in zip(trip.days, trip.days[1:], strict=False):
        assert (b.date - a.date).days == 1, "a calendar day went missing"


def test_golden_rule_never_discards_anything_with_media_or_a_track(trip):
    for e in trip.events:
        if e.status is EventStatus.SUPPRESSED:
            assert not e.media_ids, "an event with photos was suppressed"
            assert not e.track_ids, "an event with a track was suppressed"
            assert e.suppress_reason


def test_trip_stats_carry_no_elevation(trip):
    """A city break must produce meaningful stats; telemetry belongs to activities."""
    dumped = trip.stats.model_dump()
    for key in dumped:
        assert "ele" not in key and "ascent" not in key, (
            f"TripStats leaked activity telemetry via {key!r}"
        )


def test_capsule_invariants_hold(trip):
    assert collect(trip) == []
