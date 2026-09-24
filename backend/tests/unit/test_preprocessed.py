"""Unit tests for preprocessed build pipeline."""

import json
from pathlib import Path

from trippo.domain.models import MediaKind
from trippo.service.jobs import start_preprocessed
from trippo.service.preprocessed import PreprocessedBuildRequest, run_build_preprocessed


def test_run_build_preprocessed(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    out = tmp_path / "test_trip.capsule"

    # Create dummy media derivatives
    (staging / "media" / "thumb").mkdir(parents=True)
    (staging / "media" / "web").mkdir(parents=True)

    dummy_thumb = staging / "media" / "thumb" / "hash123.webp"
    dummy_thumb.write_bytes(b"dummy webp thumb")
    dummy_web = staging / "media" / "web" / "hash123.webp"
    dummy_web.write_bytes(b"dummy webp web")

    # Create media metadata
    metadata = [
        {
            "id": "med_hash123",
            "hash": "hash123",
            "kind": MediaKind.PHOTO.value,
            "filename": "PXL_20230921_120000.jpg",
            "normalized_filename": "PXL_20230921_120000.jpg",
            "captured_at": "2023-09-21T12:00:00Z",
            "timezone": "UTC",
            "time_source": "exif",
            "lat": 54.123,
            "lon": -6.456,
            "location_source": "exif",
            "width": 1920,
            "height": 1080,
            "thumb_ref": "media/thumb/hash123.webp",
            "web_ref": "media/web/hash123.webp",
        }
    ]
    (staging / "media_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    req = PreprocessedBuildRequest(
        title="Test Preprocessed Trip",
        out=out,
        staging_dir=staging,
        enrich=False,
    )

    result = run_build_preprocessed(req)
    assert result.out == out
    assert (out / "capsule.json").exists()
    assert (out / "media" / "thumb" / "hash123.webp").exists()
    assert (out / "media" / "web" / "hash123.webp").exists()
    assert len(result.trip.media) == 1
    assert result.trip.media[0].id == "med_hash123"


def test_start_preprocessed_job(tmp_path: Path):
    staging = tmp_path / "staging2"
    staging.mkdir()
    out = tmp_path / "test_job_trip.capsule"

    metadata = [
        {
            "id": "med_hash999",
            "hash": "hash999",
            "kind": MediaKind.PHOTO.value,
            "filename": "IMG_20230922_140000.jpg",
            "normalized_filename": "IMG_20230922_140000.jpg",
            "captured_at": "2023-09-22T14:00:00Z",
            "timezone": "UTC",
            "time_source": "filename",
            "lat": 54.200,
            "lon": -6.500,
            "location_source": "none",
            "thumb_ref": "media/thumb/hash999.webp",
            "web_ref": "media/web/hash999.webp",
        }
    ]
    (staging / "media_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    req = PreprocessedBuildRequest(
        title="Test Job Trip",
        out=out,
        staging_dir=staging,
        enrich=False,
    )

    job = start_preprocessed(req, cleanup_staging=False)
    assert job.status in ("running", "done")
