"""Unit tests for ingestion adapters and the pure helpers they rely on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trippo.domain.geo import haversine_m, simplify
from trippo.ingest.gpx.parse import TrackPoint, compute_stats, parse_gpx
from trippo.ingest.media.scan import detect_variant, normalize_filename, time_from_filename
from trippo.ingest.timeline.sniff import parse_lat_lng, sniff
from trippo.observe.index import PositionIndex
from trippo.observe.models import NormalizedObservation, ObservationKind

UTC = UTC


# --------------------------------------------------------------------------- sniffing


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"semanticSegments": []}, "on_device"),
        ({"timelineObjects": []}, "semantic_lh"),
        ({"locations": []}, "records"),
        ({"somethingElse": 1}, "unknown"),
        ([], "unknown"),
    ],
)
def test_timeline_formats_are_detected(payload, expected):
    assert sniff(payload).format == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("43.248688\u00b0, -2.8871506\u00b0", (43.248688, -2.8871506)),
        ("43.248688, -2.8871506", (43.248688, -2.8871506)),
        ("geo:43.248688,-2.8871506", (43.248688, -2.8871506)),
        # The degree sign arrives mojibaked from some exports; tolerate it.
        ("43.248688\ufffd, -2.8871506\ufffd", (43.248688, -2.8871506)),
        ("not a coordinate", None),
        (None, None),
        ("999.0, 0.0", None),
    ],
)
def test_coordinate_strings_are_parsed_tolerantly(raw, expected):
    assert parse_lat_lng(raw) == expected


# --------------------------------------------------------------------------- media naming


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "original_2467ac28-c22f-4c4e-a4c3-b859137728d8_PXL_20230928_192141554.jpg",
            "PXL_20230928_192141554.jpg",
        ),
        ("PXL_20230927_101112131~2.jpg", "PXL_20230927_101112131.jpg"),
        ("PXL_20230920_172632893.jpg", "PXL_20230920_172632893.jpg"),
    ],
)
def test_google_photos_export_artifacts_are_stripped(raw, expected):
    assert normalize_filename(raw) == expected


def test_timestamps_are_recovered_from_filenames():
    """The EXIF fallback that saves a scan when metadata has been stripped."""
    assert time_from_filename("PXL_20230928_192141554.jpg") == datetime(2023, 9, 28, 19, 21, 41)
    assert time_from_filename("IMG_20230928_192141.jpg") == datetime(2023, 9, 28, 19, 21, 41)
    assert time_from_filename("holiday-snap.jpg") is None


def test_capture_variants_are_detected():
    assert detect_variant("PXL_20230928_192141554.NIGHT.jpg") is not None
    assert detect_variant("PXL_20230928_192141554.PANO.jpg") is not None
    assert detect_variant("PXL_20230928_192141554.jpg") is None


# --------------------------------------------------------------------------- gpx


def _pt(i: int, ele: float) -> TrackPoint:
    return TrackPoint(
        t=datetime(2023, 9, 25, 10, 0, tzinfo=UTC) + timedelta(seconds=30 * i),
        lat=54.0 + i * 0.001,
        lon=-6.0,
        ele=ele,
    )


def test_elevation_noise_does_not_become_ascent():
    """Without a threshold, GPS altitude jitter reports hundreds of metres on flat ground.

    This is the single most consequential constant in activity telemetry.
    """
    flat_but_noisy = [_pt(i, 100.0 + (2.5 if i % 2 else -2.5)) for i in range(200)]
    stats = compute_stats(flat_but_noisy)
    assert stats.ascent_m < 10, f"noise accumulated into {stats.ascent_m} m of ascent"


def test_real_climbs_are_still_measured():
    climb = [_pt(i, 100.0 + i * 5) for i in range(100)]
    stats = compute_stats(climb)
    assert stats.ascent_m == pytest.approx(495, abs=15)
    assert stats.descent_m == 0


def test_gpx_name_and_type_are_read_from_the_track_not_the_filename():
    gpx = b"""<?xml version="1.0"?>
    <gpx xmlns="http://www.topografix.com/GPX/1/1"
         xmlns:ns3="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
      <trk><name>County Down Hiking</name><type>hiking</type><trkseg>
        <trkpt lat="54.1" lon="-5.9"><ele>144.6</ele>
          <time>2023-09-25T10:44:52.000Z</time>
          <extensions><ns3:TrackPointExtension><ns3:hr>59</ns3:hr>
          </ns3:TrackPointExtension></extensions></trkpt>
        <trkpt lat="54.2" lon="-5.9"><ele>244.6</ele>
          <time>2023-09-25T11:44:52.000Z</time>
          <extensions><ns3:TrackPointExtension><ns3:hr>141</ns3:hr>
          </ns3:TrackPointExtension></extensions></trkpt>
      </trkseg></trk></gpx>"""
    tracks = parse_gpx(gpx, fallback_name="Activity1")
    assert len(tracks) == 1
    t = tracks[0]
    assert t.name == "County Down Hiking"
    assert t.activity_type == "hiking"
    assert t.stats.avg_hr == pytest.approx(100.0)
    assert t.stats.max_hr == 141


def test_track_ids_are_stable_and_filename_independent():
    gpx = b"""<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1">
      <trk><name>Kerry Walk</name><trkseg>
        <trkpt lat="52.1" lon="-10.4"><time>2023-10-08T18:02:00Z</time></trkpt>
        <trkpt lat="52.2" lon="-10.4"><time>2023-10-08T19:16:00Z</time></trkpt>
      </trkseg></trk></gpx>"""
    a = parse_gpx(gpx, "activity_12231912600")[0]
    b = parse_gpx(gpx, "Activity1")[0]
    assert a.id == b.id, "track identity must not depend on the export filename"


# --------------------------------------------------------------------------- geometry


def test_simplify_preserves_shape_and_endpoints():
    line = [(54.0 + i * 0.0001, -6.0) for i in range(500)]
    out = simplify(line, tolerance_m=8.0)
    assert out[0] == line[0]
    assert out[-1] == line[-1]
    assert len(out) < len(line)


def test_haversine_is_sane():
    # Rosslare -> Bilbao, roughly.
    assert 800_000 < haversine_m((52.25, -6.34), (43.36, -3.07)) < 1_100_000


# --------------------------------------------------------------------------- position index


def _crumb(minute: int, lat: float) -> NormalizedObservation:
    return NormalizedObservation(
        t=datetime(2023, 9, 25, 10, minute, tzinfo=UTC),
        kind=ObservationKind.BREADCRUMB,
        source_id="t",
        lat=lat,
        lon=-6.0,
    )


def test_position_is_interpolated_between_nearby_fixes():
    idx = PositionIndex([_crumb(0, 54.0), _crumb(20, 54.2)])
    pos = idx.at(datetime(2023, 9, 25, 10, 10, tzinfo=UTC))
    assert pos is not None
    assert pos[0] == pytest.approx(54.1, abs=0.01)


def test_position_is_not_invented_across_a_void():
    """A photo taken mid-ferry with no covering source is genuinely unlocatable.

    Returning a plausible-looking coordinate here would be exactly the hallucination the
    product exists to avoid (ADR-0007).
    """
    idx = PositionIndex(
        [
            _crumb(0, 54.0),
            NormalizedObservation(
                t=datetime(2023, 9, 27, 10, 0, tzinfo=UTC),
                kind=ObservationKind.BREADCRUMB,
                source_id="t",
                lat=43.0,
                lon=-3.0,
            ),
        ]
    )
    assert idx.at(datetime(2023, 9, 26, 10, 0, tzinfo=UTC)) is None


def test_media_observations_do_not_feed_the_index():
    """Otherwise a photo's inferred position would become evidence for the next photo."""
    idx = PositionIndex(
        [
            NormalizedObservation(
                t=datetime(2023, 9, 25, 10, 0, tzinfo=UTC),
                kind=ObservationKind.MEDIA,
                source_id="m",
                lat=54.0,
                lon=-6.0,
            )
        ]
    )
    assert len(idx) == 0
