"""Derived presentation data: day titles, stats, bounds and the overview route.

All pure functions, so these run without fixtures or a network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from trippo.domain.geo import distance_to_path, offset_along_path, pad_bbox, union_bbox
from trippo.domain.models import (
    ActivityDetail,
    ActivityStats,
    DateRange,
    Day,
    Event,
    EventType,
    Geometry,
    GeometryReliability,
    MediaAsset,
    MediaKind,
    Place,
    PlaceDetail,
    PlaceSource,
    TrackMeta,
    TransitDetail,
    Trip,
    UnknownDetail,
)
from trippo.domain.summarize import summarize

T0 = datetime(2023, 9, 25, 9, 0, tzinfo=UTC)


def _ev(
    eid: str,
    etype: EventType,
    *,
    minutes: int = 60,
    name: str | None = None,
    source: PlaceSource = PlaceSource.OSM,
    lat: float = 54.1,
    lon: float = -6.0,
    detail=None,
    track_ids: list[str] | None = None,
    media_ids: list[str] | None = None,
    start: datetime | None = None,
) -> Event:
    s = start or T0
    return Event(
        id=eid,
        type=etype,
        start=s,
        end=s + timedelta(minutes=minutes),
        place=None
        if name is None
        else Place(name=name, lat=lat, lon=lon, source=source, confidence=0.9),
        title=name,
        track_ids=track_ids or [],
        media_ids=media_ids or [],
        detail=detail or PlaceDetail(),
    )


def _trip(events: list[Event], **kw) -> Trip:
    day = Day(id="d1", index=1, date=date(2023, 9, 25), event_ids=[e.id for e in events])
    for e in events:
        e.day_id = "d1"
    return Trip(
        id="t",
        title="t",
        date_range=DateRange(start=day.date, end=day.date),
        created_at=T0,
        updated_at=T0,
        days=[day],
        events=events,
        **kw,
    )


# --------------------------------------------------------------------------- titles


def test_an_activity_headlines_the_day():
    """"Slieve Binnian" is the day. A three-hour cafe stop is not."""
    trip = _trip(
        [
            _ev("a", EventType.VISIT, minutes=180, name="Carrick Cottage Cafe"),
            _ev(
                "b",
                EventType.HIKE,
                name="County Down Hiking",
                track_ids=["trk"],
                detail=ActivityDetail(stats=ActivityStats(distance_m=12_000)),
            ),
        ]
    )
    summarize(trip)
    assert trip.days[0].title == "County Down Hiking"


def test_the_longest_named_visit_wins_when_there_is_no_activity():
    trip = _trip(
        [
            _ev("a", EventType.VISIT, minutes=20, name="Rory Gallagher Statue"),
            _ev("b", EventType.VISIT, minutes=150, name="Museum of Free Derry"),
        ]
    )
    summarize(trip)
    assert trip.days[0].title == "Museum of Free Derry"


def test_coordinate_labels_never_become_a_title():
    """An unresolved place is not a name, and must not headline a day."""
    trip = _trip([_ev("a", EventType.VISIT, name="53.3451, -6.2674",
                      source=PlaceSource.COORDS)])
    summarize(trip)
    assert trip.days[0].title == "A quiet day"


def test_a_day_covered_only_by_a_crossing_says_so():
    trip = _trip([])
    gap = _ev("g", EventType.UNKNOWN, minutes=600, detail=UnknownDetail(gap_hours=10))
    gap.day_id = None
    trip.events.append(gap)
    trip.days[0].event_ids = []
    trip.days[0].spanning_event_ids = ["g"]
    summarize(trip)
    assert trip.days[0].title == "Unaccounted"


def test_subtitle_does_not_restate_the_title():
    """"Lime Kiln" beside "Lime Kiln, Carrick-a-rede" tells the reader nothing."""
    trip = _trip(
        [
            _ev("a", EventType.VISIT, minutes=120, name="Lime Kiln"),
            _ev("b", EventType.VISIT, minutes=30, name="Lime Kiln, Carrick-a-rede"),
            _ev("c", EventType.VISIT, minutes=30, name="Giant's Gate"),
        ]
    )
    summarize(trip)
    assert trip.days[0].title == "Lime Kiln"
    assert trip.days[0].subtitle == "Giant's Gate"


def test_subtitle_excludes_transits_and_gaps():
    """"A -> B" is a derived label, not a place; a gap is not a place at all."""
    trip = _trip(
        [
            _ev("a", EventType.VISIT, minutes=120, name="Kylemore Abbey"),
            _ev("b", EventType.DRIVE, name="Kylemore Abbey \u2192 Leenaun",
                detail=TransitDetail(distance_m=20_000)),
            _ev("c", EventType.UNKNOWN, name="Unaccounted", detail=UnknownDetail()),
            _ev("d", EventType.VISIT, minutes=20, name="Letterfrack"),
        ]
    )
    summarize(trip)
    sub = trip.days[0].subtitle or ""
    assert "Letterfrack" in sub
    assert "\u2192" not in sub
    assert "Unaccounted" not in sub


def test_repeated_places_appear_once():
    trip = _trip(
        [
            _ev("a", EventType.VISIT, minutes=120, name="Galway City Museum"),
            _ev("b", EventType.VISIT, minutes=30, name="Claddagh"),
            _ev("c", EventType.VISIT, minutes=30, name="Claddagh"),
        ]
    )
    summarize(trip)
    assert (trip.days[0].subtitle or "").count("Claddagh") == 1


# --------------------------------------------------------------------------- stats


def test_elevation_appears_only_when_the_day_had_an_activity():
    """The scoping rule: a city day must not carry climbing figures."""
    city = _trip([_ev("a", EventType.VISIT, name="Galway City Museum")])
    summarize(city)
    assert city.days[0].stats.ascent_m is None
    assert city.days[0].stats.has_activity is False

    hill = _trip(
        [
            _ev(
                "b",
                EventType.HIKE,
                name="County Down Hiking",
                track_ids=["trk"],
                detail=ActivityDetail(
                    stats=ActivityStats(distance_m=12_000, ascent_m=645)
                ),
            )
        ]
    )
    summarize(hill)
    assert hill.days[0].stats.ascent_m == pytest.approx(645)
    assert hill.days[0].stats.has_activity is True


def test_day_distance_is_split_by_mode():
    trip = _trip(
        [
            _ev("a", EventType.DRIVE, detail=TransitDetail(distance_m=100_000)),
            _ev(
                "b",
                EventType.HIKE,
                track_ids=["t"],
                detail=ActivityDetail(stats=ActivityStats(distance_m=12_000)),
            ),
        ]
    )
    summarize(trip)
    modes = trip.days[0].stats.distance_by_mode_m
    assert modes["drive"] == pytest.approx(100_000)
    assert modes["hike"] == pytest.approx(12_000)


def test_media_counts_split_photos_from_videos():
    trip = _trip([_ev("a", EventType.VISIT, name="X", media_ids=["m1", "m2"])])
    trip.media = [
        MediaAsset(id="m1", hash="h1", kind=MediaKind.PHOTO, filename="a.jpg",
                   normalized_filename="a.jpg"),
        MediaAsset(id="m2", hash="h2", kind=MediaKind.VIDEO, filename="b.mp4",
                   normalized_filename="b.mp4"),
    ]
    summarize(trip)
    assert trip.days[0].stats.photo_count == 1
    assert trip.days[0].stats.video_count == 1


# --------------------------------------------------------------------------- bounds


def test_day_and_trip_bounds_cover_everything_that_happened():
    trip = _trip(
        [
            _ev("a", EventType.VISIT, name="West", lat=54.0, lon=-7.0),
            _ev("b", EventType.VISIT, name="East", lat=54.5, lon=-6.0),
        ]
    )
    summarize(trip)
    box = trip.days[0].bbox
    assert box is not None
    assert box.min_lat < 54.0 and box.max_lat > 54.5
    assert box.min_lon < -7.0 and box.max_lon > -6.0
    assert trip.bbox is not None


def test_a_day_with_nothing_positioned_has_no_bounds():
    """Better no bbox than a bbox around (0, 0)."""
    trip = _trip([_ev("a", EventType.VISIT, name=None)])
    summarize(trip)
    assert trip.days[0].bbox is None


def test_bounds_are_padded_so_nothing_sits_on_the_window_edge():
    tight = (54.0, -6.0, 54.0, -6.0)
    padded = pad_bbox(tight, 400.0)
    assert padded[0] < 54.0 < padded[2]
    assert padded[1] < -6.0 < padded[3]


def test_union_of_no_boxes_is_none():
    assert union_bbox([]) is None


# --------------------------------------------------------------------------- route


def test_route_is_segmented_so_the_map_can_style_each_leg():
    """A measured trail and a guessed ferry must not merge into one confident line."""
    trip = _trip(
        [
            _ev(
                "a",
                EventType.DRIVE,
                detail=TransitDetail(distance_m=50_000),
            ),
            _ev("g", EventType.UNKNOWN, detail=UnknownDetail(
                from_place=Place(name="A", lat=52.2, lon=-6.3),
                to_place=Place(name="B", lat=43.3, lon=-3.0),
            )),
        ]
    )
    trip.events[0].geometry = Geometry(
        kind="line",
        polyline=[(54.0, -6.0), (54.1, -6.1), (54.2, -6.2)],
        reliability=GeometryReliability.SPARSE,
    )
    summarize(trip)

    kinds = {s.kind: s for s in trip.route}
    assert set(kinds) == {"drive", "unknown"}
    assert kinds["drive"].reliability is GeometryReliability.SPARSE
    # A gap asserts nothing: endpoints only, explicitly flagged as assumed.
    assert kinds["unknown"].reliability is GeometryReliability.ASSUMED
    assert len(kinds["unknown"].points) == 2


def test_a_track_contributes_a_segment_from_its_bounds():
    trip = _trip([_ev("h", EventType.HIKE, track_ids=["trk"], detail=ActivityDetail())])
    trip.tracks = [
        TrackMeta(
            id="trk",
            source_id="s",
            name="County Down Hiking",
            start=T0,
            end=T0 + timedelta(hours=3),
            bbox=(54.10, -6.05, 54.20, -5.95),
        )
    ]
    summarize(trip)
    seg = next(s for s in trip.route if s.kind == "hike")
    assert seg.reliability is GeometryReliability.MEASURED
    assert len(seg.points) == 2


def test_summarize_is_idempotent():
    """It runs after both the build and enrichment; twice must equal once."""
    trip = _trip([_ev("a", EventType.VISIT, minutes=90, name="Kylemore Abbey")])
    summarize(trip)
    first = (trip.days[0].title, trip.days[0].subtitle, len(trip.route))
    summarize(trip)
    assert (trip.days[0].title, trip.days[0].subtitle, len(trip.route)) == first


# --------------------------------------------------------------------------- geo


def test_distance_to_path_measures_to_the_line_not_the_vertices():
    """A summit beside the midpoint of a long leg is close, even if both ends are far."""
    path = [(54.0, -6.0), (54.0, -5.0)]
    assert distance_to_path((54.001, -5.5), path) < 200


def test_offset_along_path_orders_features_by_progress():
    path = [(54.0, -6.0), (54.0, -5.9), (54.0, -5.8)]
    near_start = offset_along_path((54.0, -5.98), path)
    near_end = offset_along_path((54.0, -5.82), path)
    assert near_start < near_end
