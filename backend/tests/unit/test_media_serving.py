"""Tests for static media serving (thumbnails, web images, tracks)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from trippo.api.app import _STATE, app, load_capsule
from trippo.domain.models import DateRange, Trip


@pytest.fixture
def test_capsule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TRIPPO_WORKSPACE", str(tmp_path))
    cap_dir = tmp_path / "Test-Trip.capsule"
    cap_dir.mkdir(parents=True)

    now = datetime.now(UTC)
    trip = Trip(
        id="test-trip",
        title="Test Trip",
        date_range=DateRange(start=date(2023, 9, 21), end=date(2023, 9, 22)),
        created_at=now,
        updated_at=now,
    )
    (cap_dir / "capsule.json").write_text(
        json.dumps(trip.model_dump(mode="json")),
        encoding="utf-8",
    )

    # Dummy media derivative files
    thumb_dir = cap_dir / "media" / "thumb"
    thumb_dir.mkdir(parents=True)
    (thumb_dir / "abc12345.webp").write_bytes(b"RIFFdummywebpthumb")

    web_dir = cap_dir / "media" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / "abc12345.webp").write_bytes(b"RIFFdummywebimage")

    # Dummy track file
    track_dir = cap_dir / "tracks"
    track_dir.mkdir(parents=True)
    (track_dir / "trk_01.json").write_text(
        json.dumps({"simplified": [], "profile": []}),
        encoding="utf-8",
    )

    return cap_dir


def test_serve_media_open_capsule(test_capsule: Path) -> None:
    load_capsule(test_capsule)
    client = TestClient(app)

    res = client.get("/media/thumb/abc12345.webp")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/webp"
    assert "public" in res.headers.get("cache-control", "")
    assert res.content == b"RIFFdummywebpthumb"

    res_web = client.get("/media/web/abc12345.webp")
    assert res_web.status_code == 200
    assert res_web.content == b"RIFFdummywebimage"

    res_track = client.get("/tracks/trk_01.json")
    assert res_track.status_code == 200
    assert "simplified" in res_track.text


def test_serve_media_fallback_when_no_capsule_open(test_capsule: Path) -> None:
    _STATE["root"] = None
    _STATE["session"] = None
    client = TestClient(app)

    res = client.get("/media/thumb/abc12345.webp")
    assert res.status_code == 200
    assert res.content == b"RIFFdummywebpthumb"


def test_serve_capsule_media_endpoint(test_capsule: Path) -> None:
    client = TestClient(app)

    # Both with and without prefix
    res = client.get("/api/capsules/Test-Trip.capsule/media/thumb/abc12345.webp")
    assert res.status_code == 200
    assert res.content == b"RIFFdummywebpthumb"

    res2 = client.get("/api/capsules/Test-Trip.capsule/media/web/abc12345.webp")
    assert res2.status_code == 200
    assert res2.content == b"RIFFdummywebimage"


def test_serve_media_not_found(test_capsule: Path) -> None:
    load_capsule(test_capsule)
    client = TestClient(app)

    res = client.get("/media/thumb/nonexistent.webp")
    assert res.status_code == 404


def test_serve_media_path_traversal_blocked(test_capsule: Path) -> None:
    load_capsule(test_capsule)
    client = TestClient(app)

    res = client.get("/media/thumb/%2e%2e/%2e%2e/capsule.json")
    assert res.status_code == 404

