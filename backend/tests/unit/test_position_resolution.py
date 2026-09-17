"""How a photo gets a position, and how it must not.

The cascade, best source first:

    1. EXIF GPS                     -- measured by the camera, always wins
    2. Interpolation from the       -- timeline breadcrumbs, GPX trackpoints,
       PositionIndex                   and OTHER photos' EXIF GPS
    3. `LocationSource.NONE`        -- admit defeat rather than invent

The rule that keeps this trustworthy: **only measured positions feed the index.** A
position Trippo inferred must never become evidence for the next inference.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from trippo.config.heuristics import (
    PLACE_CONFIDENCE_FROM_EXIF,
    PLACE_CONFIDENCE_FROM_INFERRED,
)
from trippo.domain.models import LocationSource, MediaAsset, MediaKind, TimeSource
from trippo.draft.builder import BuildInputs, build
from trippo.observe.index import PositionIndex
from trippo.observe.models import NormalizedObservation, ObservationKind

T0 = datetime(2023, 9, 25, 10, 0, tzinfo=UTC)


def _photo(minute: int, lat: float | None = None, lon: float | None = None) -> MediaAsset:
    return MediaAsset(
        id=f"med_{minute}",
        hash=f"h{minute}",
        kind=MediaKind.PHOTO,
        filename=f"p{minute}.jpg",
        normalized_filename=f"p{minute}.jpg",
        captured_at=T0 + timedelta(minutes=minute),
        time_source=TimeSource.EXIF,
        lat=lat,
        lon=lon,
        location_source=LocationSource.EXIF if lat is not None else LocationSource.NONE,
    )


def _crumb(minute: int, lat: float, lon: float = -6.0) -> NormalizedObservation:
    return NormalizedObservation(
        t=T0 + timedelta(minutes=minute),
        kind=ObservationKind.BREADCRUMB,
        source_id="timeline:0",
        lat=lat,
        lon=lon,
    )


def _media_obs(m: MediaAsset) -> NormalizedObservation:
    return NormalizedObservation(
        t=m.captured_at,
        kind=ObservationKind.MEDIA,
        source_id="media:0",
        lat=m.lat,
        lon=m.lon,
        ref=m.id,
        trusted_position=m.location_source is LocationSource.EXIF,
    )


def _build(media: list[MediaAsset], observations: list[NormalizedObservation]):
    return build(
        BuildInputs(
            title="t",
            observations=[*observations, *(_media_obs(m) for m in media)],
            media=media,
            window_start=date(2023, 9, 25),
            window_end=date(2023, 9, 25),
        )
    )


# --------------------------------------------------------------------------- the cascade


def test_exif_gps_always_wins_over_interpolation():
    """A camera fix must never be overwritten by a timeline guess."""
    photo = _photo(10, lat=54.5, lon=-6.5)
    _trip, _trace = _build([photo], [_crumb(0, 50.0), _crumb(20, 51.0)])
    assert photo.lat == 54.5
    assert photo.lon == -6.5
    assert photo.location_source is LocationSource.EXIF


def test_position_is_interpolated_from_the_timeline_when_exif_has_none():
    photo = _photo(10)
    _trip, trace = _build([photo], [_crumb(0, 54.0), _crumb(20, 54.2)])
    assert photo.location_source is LocationSource.INFERRED
    assert photo.lat is not None
    assert abs(photo.lat - 54.1) < 0.01
    assert trace.inferred_positions == 1


def test_a_geotagged_photo_locates_its_neighbours():
    """One geotagged shot should place the whole burst around it.

    This is the mixed-device case: a camera with GPS and a phone without, in the same
    album. Without it, the phone's photos would be unlocatable even though we know
    exactly where the user was.
    """
    anchor_a = _photo(0, lat=54.0, lon=-6.0)
    plain = _photo(10)
    anchor_b = _photo(20, lat=54.2, lon=-6.0)

    _trip, trace = _build([anchor_a, plain, anchor_b], [])

    assert plain.location_source is LocationSource.INFERRED
    assert plain.lat is not None
    assert abs(plain.lat - 54.1) < 0.01
    assert trace.media_gps_exif == 2
    assert trace.inferred_positions == 1


def test_an_inferred_position_never_becomes_evidence():
    """Otherwise error compounds and a route is manufactured out of nothing.

    Photo at minute 10 is inferred from the crumbs. Photo at minute 400 is hours past any
    measurement -- it must stay unlocatable rather than chain off the inferred one.
    """
    near = _photo(10)
    far = _photo(400)
    _trip, trace = _build([near, far], [_crumb(0, 54.0), _crumb(20, 54.2)])

    assert near.location_source is LocationSource.INFERRED
    assert far.location_source is LocationSource.NONE
    assert far.lat is None
    assert trace.unlocatable_media == 1


def test_unlocatable_is_reported_not_guessed():
    """The ferry-day case: photos exist, no source covers them. ADR-0007."""
    photo = _photo(10)
    _trip, trace = _build([photo], [])
    assert photo.location_source is LocationSource.NONE
    assert photo.lat is None
    assert trace.unlocatable_media == 1
    assert trace.inferred_positions == 0


# --------------------------------------------------------------------------- index rules


def test_only_trusted_positions_enter_the_index():
    trusted = _crumb(0, 54.0)
    inferred = NormalizedObservation(
        t=T0 + timedelta(minutes=5),
        kind=ObservationKind.MEDIA,
        source_id="media:0",
        lat=99.0,
        lon=99.0,
        trusted_position=False,
    )
    idx = PositionIndex([trusted, inferred])
    assert len(idx) == 1


def test_geotagged_media_do_enter_the_index():
    geotagged = NormalizedObservation(
        t=T0,
        kind=ObservationKind.MEDIA,
        source_id="media:0",
        lat=54.0,
        lon=-6.0,
        trusted_position=True,
    )
    assert len(PositionIndex([geotagged])) == 1


# --------------------------------------------------------------------------- events


def test_events_inherit_a_position_from_their_geotagged_photos():
    photos = [_photo(0, lat=54.0, lon=-6.0), _photo(5, lat=54.01, lon=-6.0)]
    trip, trace = _build(photos, [])

    assert trace.events_placed_by_media >= 1
    event = next(e for e in trip.events if e.media_ids)
    assert event.place is not None
    assert event.place.lat is not None
    assert abs(event.place.lat - 54.005) < 0.01
    assert event.place.confidence == PLACE_CONFIDENCE_FROM_EXIF


def test_events_placed_from_inferred_photos_say_so():
    trip, _trace = _build([_photo(10)], [_crumb(0, 54.0), _crumb(20, 54.2)])
    event = next(e for e in trip.events if e.media_ids)
    assert event.place is not None
    assert event.place.confidence == PLACE_CONFIDENCE_FROM_INFERRED, (
        "an inferred placement must be marked as weaker than a measured one"
    )


def test_unaccounted_gaps_never_acquire_a_location(trip_with_gap=None):
    """A gap is the absence of knowledge. Attaching photos to it must not locate it."""
    from trippo.domain.models import EventType

    photos = [_photo(0, lat=54.0, lon=-6.0), _photo(60 * 30)]
    trip, _trace = build(
        BuildInputs(
            title="t",
            observations=[
                _crumb(0, 54.0),
                _crumb(60 * 40, 43.0, -3.0),
                *(_media_obs(m) for m in photos),
            ],
            media=photos,
        )
    )
    for e in trip.events:
        if e.type is EventType.UNKNOWN:
            assert e.place is None or e.place.lat is None
