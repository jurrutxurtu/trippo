"""Export: a self-contained page that opens from disk with no server."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from trippo.capsule.export import export_html
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
    PlaceSource,
    TrackHighlight,
    Trip,
    UnknownDetail,
)
from trippo.domain.summarize import summarize

T0 = datetime(2023, 9, 25, 9, 0, tzinfo=UTC)


@pytest.fixture
def capsule(tmp_path):
    """A capsule on disk with real derivative files, so copying is exercised."""
    root = tmp_path / "cap"
    (root / "media" / "thumb").mkdir(parents=True)
    (root / "media" / "web").mkdir(parents=True)

    media = []
    for i in range(3):
        (root / "media" / "thumb" / f"h{i}.webp").write_bytes(b"thumb")
        (root / "media" / "web" / f"h{i}.webp").write_bytes(b"web-sized")
        media.append(
            MediaAsset(
                id=f"m{i}",
                hash=f"h{i}",
                kind=MediaKind.PHOTO,
                filename=f"p{i}.jpg",
                normalized_filename=f"p{i}.jpg",
                captured_at=T0 + timedelta(minutes=i * 10),
                thumb_ref=f"media/thumb/h{i}.webp",
                web_ref=f"media/web/h{i}.webp",
            )
        )
    media.append(
        MediaAsset(
            id="v0",
            hash="hv",
            kind=MediaKind.VIDEO,
            filename="clip.mp4",
            normalized_filename="clip.mp4",
            captured_at=T0,
        )
    )

    hike = Event(
        id="h",
        day_id="d1",
        type=EventType.HIKE,
        start=T0,
        end=T0 + timedelta(hours=3),
        title="County Down Hiking",
        place=Place(name="County Down Hiking", lat=54.1, lon=-6.0,
                    source=PlaceSource.GPX, confidence=1.0),
        media_ids=["m0", "m1", "m2"],
        selected_media_ids=["m0", "m1"],
        # Frozen, so summarize() leaves the hand-picked pair alone.
        user_selected_media=True,
        track_ids=["trk"],
        note="Hail at the summit.",
        detail=ActivityDetail(
            stats=ActivityStats(distance_m=12_000, ascent_m=645, max_ele_m=745),
            highlights=[
                TrackHighlight(name="Slieve Binnian", kind="natural=peak",
                               lat=54.11, lon=-6.01, ele_m=745.9, offset_m=8000)
            ],
        ),
    )
    gap = Event(
        id="g",
        day_id="d2",
        type=EventType.UNKNOWN,
        start=T0 + timedelta(days=1),
        end=T0 + timedelta(days=1, hours=19),
        detail=UnknownDetail(gap_hours=19, displacement_km=1018),
    )
    trip = Trip(
        id="t",
        title="Ireland 2023",
        subtitle="Three weeks in the van",
        date_range=DateRange(start=date(2023, 9, 25), end=date(2023, 9, 26)),
        created_at=T0,
        updated_at=T0,
        days=[
            Day(id="d1", index=1, date=date(2023, 9, 25), event_ids=["h"]),
            Day(id="d2", index=2, date=date(2023, 9, 26), event_ids=["g"]),
        ],
        events=[hike, gap],
        media=media,
        unassigned_media_ids=["v0"],
    )
    summarize(trip)
    return trip, root


def _html(tmp_path, capsule) -> str:
    trip, root = capsule
    out = tmp_path / "out"
    export_html(trip, root, out)
    return (out / "index.html").read_text(encoding="utf-8")


def test_the_page_opens_without_a_server(tmp_path, capsule):
    trip, root = capsule
    out = tmp_path / "out"
    export_html(trip, root, out)
    page = out / "index.html"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    # Every image reference must be relative, or the file is useless off this machine.
    assert 'src="media/' in text
    assert "http://localhost" not in text
    assert "/api/" not in text


def test_photographs_are_copied_but_videos_only_referenced(tmp_path, capsule):
    trip, root = capsule
    out = tmp_path / "out"
    report = export_html(trip, root, out)
    assert report.photos_copied == 3
    assert report.videos_skipped == 1
    assert (out / "media" / "thumb" / "h0.webp").exists()
    assert (out / "media" / "web" / "h0.webp").exists()
    assert not list((out / "media").rglob("*.mp4"))


def test_originals_are_never_copied(tmp_path, capsule):
    """Derivatives travel; originals stay on the machine that made them (ADR-0001)."""
    trip, root = capsule
    out = tmp_path / "out"
    export_html(trip, root, out)
    assert not list(out.rglob("*.jpg"))


def test_the_itinerary_is_rendered(tmp_path, capsule):
    text = _html(tmp_path, capsule)
    assert "Ireland 2023" in text
    assert "County Down Hiking" in text
    assert "Three weeks in the van" in text


def test_activity_telemetry_and_summits_survive_the_export(tmp_path, capsule):
    text = _html(tmp_path, capsule)
    assert "12.0 km" in text
    assert "+645 m" in text
    assert "Slieve Binnian" in text


def test_an_unaccounted_gap_stays_honest_in_the_export(tmp_path, capsule):
    """The zero-hallucination rule does not stop at the studio door."""
    text = _html(tmp_path, capsule)
    assert "19 hours unaccounted" in text
    assert "1,018 km that no source explains" in text


def test_the_users_note_is_included(tmp_path, capsule):
    assert "Hail at the summit." in _html(tmp_path, capsule)


def test_only_the_selected_photographs_are_shown(tmp_path, capsule):
    text = _html(tmp_path, capsule)
    assert "media/thumb/h0.webp" in text
    assert "media/thumb/h1.webp" in text
    assert "+1 more not shown" in text


def test_missing_derivatives_are_counted_not_fatal(tmp_path, capsule):
    trip, root = capsule
    (root / "media" / "thumb" / "h1.webp").unlink()
    out = tmp_path / "out"
    report = export_html(trip, root, out)
    assert report.missing == 1
    assert (out / "index.html").exists()


def test_excluded_days_do_not_appear(tmp_path, capsule):
    trip, root = capsule
    trip.days[1].excluded = True
    out = tmp_path / "out"
    export_html(trip, root, out)
    text = (out / "index.html").read_text(encoding="utf-8")
    assert "unaccounted" not in text.lower()


def test_html_is_escaped(tmp_path, capsule):
    trip, root = capsule
    trip.title = '<script>alert("x")</script>'
    out = tmp_path / "out"
    export_html(trip, root, out)
    text = (out / "index.html").read_text(encoding="utf-8")
    assert '<script>alert("x")</script>' not in text
    assert "&lt;script&gt;" in text


def test_suppressed_events_are_not_exported(tmp_path, capsule):
    trip, root = capsule
    trip.events[0].status = EventStatus.SUPPRESSED
    trip.events[0].suppress_reason = "hidden"
    out = tmp_path / "out"
    export_html(trip, root, out)
    text = (out / "index.html").read_text(encoding="utf-8")
    assert "County Down Hiking" not in text
