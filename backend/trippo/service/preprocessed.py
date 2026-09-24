"""Build pipeline from client-side preprocessed data.

Used when ingesting via web / remote server, where raw media (several GB)
was preprocessed in the browser into lightweight metadata and WebP derivatives.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from trippo.capsule import io as capsule_io
from trippo.domain.models import (
    IngestionReport,
    MediaAsset,
    MediaKind,
    Source,
    SourceKind,
)
from trippo.draft.builder import BuildInputs, build
from trippo.ingest.gpx.parse import ParsedTrack, parse_gpx
from trippo.ingest.timeline.adapters import load as load_timeline
from trippo.observe.models import NormalizedObservation, ObservationKind
from trippo.service.build import BuildRequest, BuildResult, Progress, _as_dt, _enrich, _noop


@dataclass
class PreprocessedBuildRequest:
    title: str
    out: Path
    staging_dir: Path
    description: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    default_offset_minutes: int = 0
    enrich: bool = True
    offline: bool = False


def run_build_preprocessed(
    req: PreprocessedBuildRequest, progress: Progress = _noop
) -> BuildResult:
    reports: list[IngestionReport] = []
    sources: list[Source] = []
    observations: list[NormalizedObservation] = []
    tracks: list[ParsedTrack] = []
    media: list[MediaAsset] = []

    win_start, win_end = _as_dt(req.date_from), _as_dt(req.date_to, end=True)

    # 1. Timeline
    timeline_path = req.staging_dir / "timeline.json"
    if timeline_path.is_file():
        progress("timeline", f"Reading {timeline_path.name}", 0, 0)
        payload = json.loads(timeline_path.read_text(encoding="utf-8", errors="replace"))
        obs, rep = load_timeline(payload, "timeline:0", win_start, win_end)
        observations.extend(obs)
        reports.append(rep)
        sources.append(
            Source(
                id="timeline:0",
                kind=SourceKind.TIMELINE,
                detected_format=rep.detected_format,
                display_name=timeline_path.name,
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        progress(
            "timeline",
            f"{rep.detected_format}: {rep.records_in_window:,} records in range",
            1,
            1,
        )

    # 2. GPX
    tracks_dir = req.staging_dir / "tracks"
    if tracks_dir.is_dir():
        files = sorted(tracks_dir.glob("*.gpx"))
        if files:
            rep = IngestionReport(
                source_id="gpx:0",
                kind=SourceKind.GPX,
                detected_format="gpx",
                confidence=1.0,
                files_seen=len(files),
            )
            for i, f in enumerate(files, start=1):
                progress("gpx", f"Parsing {f.name}", i, len(files))
                try:
                    parsed = parse_gpx(f.read_bytes(), f.stem)
                except Exception as exc:
                    rep.skipped.append({"file": f.name, "reason": f"parse error: {exc}"})
                    continue
                if not parsed:
                    rep.skipped.append({"file": f.name, "reason": "no track points"})
                    continue
                for t in parsed:
                    if win_start and t.end and t.end < win_start:
                        rep.skipped.append({"file": f.name, "reason": "before the window"})
                        continue
                    if win_end and t.start and t.start > win_end:
                        rep.skipped.append({"file": f.name, "reason": "after the window"})
                        continue
                    tracks.append(t)
                rep.files_parsed += 1
            rep.records_total = rep.records_in_window = len(tracks)
            reports.append(rep)
            sources.append(
                Source(
                    id="gpx:0",
                    kind=SourceKind.GPX,
                    detected_format="gpx",
                    display_name=f"{len(files)} track(s)",
                    imported_at=datetime.now(UTC),
                    report=rep,
                )
            )
            progress("gpx", f"{len(tracks)} track(s)", len(files), len(files))

    # 3. Media Metadata
    meta_path = req.staging_dir / "media_metadata.json"
    if meta_path.is_file():
        progress("media", "Loading preprocessed media metadata", 0, 0)
        items = json.loads(meta_path.read_text(encoding="utf-8"))
        rep = IngestionReport(
            source_id="media:0",
            kind=SourceKind.MEDIA,
            detected_format="preprocessed_web",
            confidence=1.0,
            files_seen=len(items),
            files_parsed=len(items),
        )
        for item in items:
            asset = MediaAsset.model_validate(item)
            if win_start and asset.captured_at and asset.captured_at < win_start:
                rep.skipped.append({"file": asset.filename, "reason": "before the window"})
                continue
            if win_end and asset.captured_at and asset.captured_at > win_end:
                rep.skipped.append({"file": asset.filename, "reason": "after the window"})
                continue
            media.append(asset)

        rep.records_total = len(items)
        rep.records_in_window = len(media)
        reports.append(rep)
        sources.append(
            Source(
                id="media:0",
                kind=SourceKind.MEDIA,
                detected_format="preprocessed_web",
                display_name=f"{len(media)} item(s)",
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        photos = sum(1 for m in media if m.kind is MediaKind.PHOTO)
        videos = sum(1 for m in media if m.kind is MediaKind.VIDEO)
        progress("media", f"{photos:,} photographs, {videos} videos", 1, 1)

    if not (observations or tracks or media):
        raise ValueError("No usable data in any source.")

    # Observations from media
    observations.extend(
        NormalizedObservation(
            t=m.captured_at,
            kind=ObservationKind.MEDIA,
            source_id="media:0",
            lat=m.lat,
            lon=m.lon,
            ref=m.id,
            trusted_position=m.location_source.value == "exif",
        )
        for m in media
        if m.captured_at is not None
    )

    # 4. Working out itinerary
    progress("build", "Working out the itinerary", 0, 0)
    trip, trace = build(
        BuildInputs(
            title=req.title,
            observations=observations,
            tracks=tracks,
            media=media,
            window_start=req.date_from,
            window_end=req.date_to,
            default_offset_minutes=req.default_offset_minutes,
        )
    )
    trip.sources = sources
    if req.description:
        trip.subtitle = req.description
    progress("build", f"{len(trip.days)} days, {len(trip.active_events)} events", 1, 1)

    # 5. Enrich
    if req.enrich:
        dummy_req = BuildRequest(
            title=req.title,
            out=req.out,
            date_from=req.date_from,
            date_to=req.date_to,
            offline=req.offline,
        )
        _enrich(trip, tracks, dummy_req, progress)

    # 6. Save
    req.out.mkdir(parents=True, exist_ok=True)

    # Copy preprocessed thumbnails and web images into capsule
    media_src = req.staging_dir / "media"
    if media_src.is_dir():
        media_dest = req.out / "media"
        media_dest.mkdir(parents=True, exist_ok=True)
        for subdir in ("thumb", "web"):
            src_sub = media_src / subdir
            if src_sub.is_dir():
                dest_sub = media_dest / subdir
                dest_sub.mkdir(parents=True, exist_ok=True)
                for f in src_sub.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dest_sub / f.name)

    progress("save", "Writing the capsule", 0, 0)
    capsule_io.write(trip, req.out, reports=reports)
    for t in tracks:
        (req.out / "tracks").mkdir(parents=True, exist_ok=True)
        (req.out / "tracks" / f"{t.id}.json").write_text(
            json.dumps({"simplified": t.simplified, "profile": t.profile}),
            encoding="utf-8",
        )
    progress("save", f"Saved to {req.out.name}", 1, 1)

    return BuildResult(trip=trip, trace=trace, reports=reports, out=req.out)
