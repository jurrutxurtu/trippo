"""Choosing which photographs represent an event.

A three-hour hike can own 87 photographs. The selection has to be small, well spread, and
free of near-duplicates -- and it must never lose anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trippo.config.heuristics import PHOTO_SELECTION_MAX
from trippo.domain.models import LocationSource, MediaAsset, MediaKind, MediaVariant
from trippo.domain.photos import bursts, score, select

T0 = datetime(2023, 9, 25, 10, 0, tzinfo=UTC)


def _m(
    n: int,
    *,
    seconds: int,
    variant: MediaVariant | None = None,
    loc: LocationSource = LocationSource.NONE,
    kind: MediaKind = MediaKind.PHOTO,
    width: int | None = None,
    height: int | None = None,
) -> MediaAsset:
    return MediaAsset(
        id=f"m{n}",
        hash=f"h{n}",
        kind=kind,
        filename=f"p{n}.jpg",
        normalized_filename=f"p{n}.jpg",
        captured_at=T0 + timedelta(seconds=seconds),
        variant=variant,
        location_source=loc,
        width=width,
        height=height,
    )


# --------------------------------------------------------------------------- scoring


def test_deliberate_captures_score_higher():
    """A panorama took effort, so it probably mattered."""
    plain = score(_m(1, seconds=0))
    pano = score(_m(2, seconds=0, variant=MediaVariant.PANO))
    assert pano.score > plain.score


def test_a_measured_position_is_worth_more_than_an_inferred_one():
    """It can be placed on the map exactly, which is the point of a photo pin."""
    exact = score(_m(1, seconds=0, loc=LocationSource.EXIF))
    guessed = score(_m(2, seconds=0, loc=LocationSource.INFERRED))
    nowhere = score(_m(3, seconds=0, loc=LocationSource.NONE))
    assert exact.score > guessed.score > nowhere.score


def test_videos_are_poor_representatives():
    """They are excluded from export in this version, so they should not headline."""
    photo = score(_m(1, seconds=0))
    video = score(_m(2, seconds=0, kind=MediaKind.VIDEO))
    assert video.score < photo.score


def test_a_wide_aspect_counts_as_a_panorama_without_the_filename_tag():
    wide = score(_m(1, seconds=0, width=8000, height=2000))
    normal = score(_m(2, seconds=0, width=4000, height=3000))
    assert wide.score > normal.score


# --------------------------------------------------------------------------- bursts


def test_consecutive_shots_group_into_one_burst():
    """Six frames of the same waterfall are one photograph, as far as a summary goes."""
    media = [_m(i, seconds=i * 5) for i in range(6)]
    assert len(bursts(media)) == 1


def test_a_long_gap_starts_a_new_burst():
    media = [_m(0, seconds=0), _m(1, seconds=5), _m(2, seconds=600)]
    groups = bursts(media)
    assert len(groups) == 2
    assert len(groups[0]) == 2


def test_bursts_cope_with_identical_timestamps():
    """Two shots can share a timestamp; sorting must not try to compare the models."""
    media = [_m(0, seconds=0), _m(1, seconds=0), _m(2, seconds=0)]
    assert len(bursts(media)) == 1


def test_media_without_a_timestamp_are_ignored():
    m = _m(0, seconds=0)
    m.captured_at = None
    assert bursts([m]) == []


# --------------------------------------------------------------------------- selection


def test_everything_is_kept_when_there_is_little_to_choose_from():
    media = [_m(i, seconds=i * 300) for i in range(5)]
    chosen = select(media)
    assert len(chosen) == 5


def test_the_selection_is_capped():
    media = [_m(i, seconds=i * 300) for i in range(60)]
    assert len(select(media)) <= PHOTO_SELECTION_MAX


def test_a_single_burst_cannot_fill_the_whole_selection():
    """Otherwise a summary of a six-hour walk is six shots of lunch."""
    lunch = [_m(i, seconds=3600 + i * 3) for i in range(40)]
    rest = [_m(100 + i, seconds=i * 1800) for i in range(6)]
    chosen = set(select(lunch + rest))
    from_lunch = sum(1 for m in lunch if m.id in chosen)
    assert from_lunch <= 2, f"{from_lunch} of the selection came from one burst"


def test_the_selection_is_spread_across_the_event():
    media = [_m(i, seconds=i * 120) for i in range(120)]  # four hours
    chosen_ids = set(select(media))
    times = sorted(
        (m.captured_at for m in media if m.id in chosen_ids),
    )
    span = (times[-1] - times[0]).total_seconds()
    total = (media[-1].captured_at - media[0].captured_at).total_seconds()  # type: ignore[operator]
    assert span > total * 0.5, "the selection clusters instead of spanning the event"


def test_the_selection_is_returned_in_capture_order():
    media = [_m(i, seconds=i * 400) for i in range(40)]
    chosen = select(media)
    by_id = {m.id: m for m in media}
    times = [by_id[i].captured_at for i in chosen]
    assert times == sorted(times)


def test_videos_never_reach_the_selection():
    media = [_m(i, seconds=i * 300, kind=MediaKind.VIDEO) for i in range(10)]
    assert select(media) == []


def test_selection_is_deterministic():
    media = [_m(i, seconds=i * 137) for i in range(50)]
    assert select(media) == select(media)
