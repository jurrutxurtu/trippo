"""The build pipeline as a service, driven by both the CLI and the API.

Extracted from `cli.py` so the web UI runs exactly the same code path. A second
implementation for HTTP would drift from the command line within a week.

Progress is reported through a callback rather than printed, so the caller decides whether
it becomes a terminal line or a server-sent event.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from trippo.capsule import io as capsule_io
from trippo.domain.models import (
    IngestionReport,
    MediaAsset,
    MediaKind,
    Source,
    SourceKind,
    Trip,
)
from trippo.draft.builder import BuildInputs, BuildTrace, build
from trippo.ingest.gpx.parse import ParsedTrack, parse_gpx
from trippo.ingest.media.scan import scan_media
from trippo.ingest.timeline.adapters import load as load_timeline
from trippo.observe.models import NormalizedObservation, ObservationKind

#: (stage, message, done, total). `total` of 0 means indeterminate.
Progress = Callable[[str, str, int, int], None]

STAGES = ("timeline", "gpx", "media", "build", "enrich", "summits", "thumbnails", "save")


def _noop(_stage: str, _msg: str, _done: int, _total: int) -> None:
    pass


@dataclass
class BuildRequest:
    title: str
    out: Path
    timeline: Path | None = None
    gpx: Path | None = None
    media: list[Path] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    default_offset_minutes: int = 0
    enrich: bool = True
    derivatives: bool = True
    offline: bool = False
    description: str | None = None


@dataclass
class BuildResult:
    trip: Trip
    trace: BuildTrace
    reports: list[IngestionReport]
    out: Path


def _as_dt(d: date | None, end: bool = False) -> datetime | None:
    if d is None:
        return None
    return datetime.combine(d, time.max if end else time.min, tzinfo=UTC)


def propose_dates(media_roots: list[Path], limit: int = 4000) -> tuple[date, date] | None:
    """Guess a trip's dates from photo timestamps, without a full ingest.

    Reads filenames and EXIF headers only -- fast enough to run while the user is still
    filling in the form, which is the point: nobody remembers exactly when they left.
    """
    from trippo.ingest.media.scan import (
        PHOTO_EXT,
        VIDEO_EXT,
        normalize_filename,
        time_from_filename,
    )

    stamps: list[datetime] = []
    for root in media_roots:
        if not root.exists():
            continue
        files = [root] if root.is_file() else list(root.rglob("*"))
        for p in files[:limit]:
            if not p.is_file() or p.suffix.lower() not in (PHOTO_EXT | VIDEO_EXT):
                continue
            t = time_from_filename(normalize_filename(p.name))
            if t is None:
                try:
                    t = datetime.fromtimestamp(p.stat().st_mtime)
                except OSError:
                    continue
            stamps.append(t)
    if not stamps:
        return None
    return (min(stamps).date(), max(stamps).date())


def run_build(req: BuildRequest, progress: Progress = _noop) -> BuildResult:
    reports: list[IngestionReport] = []
    sources: list[Source] = []
    observations: list[NormalizedObservation] = []
    tracks: list[ParsedTrack] = []
    media: list[MediaAsset] = []
    local_paths: dict[str, str] = {}

    win_start, win_end = _as_dt(req.date_from), _as_dt(req.date_to, end=True)

    # ---------------------------------------------------------------- timeline
    if req.timeline:
        progress("timeline", f"Reading {req.timeline.name}", 0, 0)
        payload = json.loads(req.timeline.read_text(encoding="utf-8", errors="replace"))
        obs, rep = load_timeline(payload, "timeline:0", win_start, win_end)
        observations.extend(obs)
        reports.append(rep)
        sources.append(
            Source(
                id="timeline:0",
                kind=SourceKind.TIMELINE,
                detected_format=rep.detected_format,
                display_name=req.timeline.name,
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

    # ---------------------------------------------------------------- gpx
    if req.gpx:
        files = sorted(req.gpx.rglob("*.gpx")) if req.gpx.is_dir() else [req.gpx]
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
                display_name=req.gpx.name,
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        progress("gpx", f"{len(tracks)} track(s)", len(files), len(files))

    # ---------------------------------------------------------------- media
    if req.media:
        progress("media", "Scanning photographs", 0, 0)
        media, rep = scan_media(req.media, "media:0", win_start, win_end)
        reports.append(rep)
        sources.append(
            Source(
                id="media:0",
                kind=SourceKind.MEDIA,
                detected_format="folder",
                display_name=", ".join(r.name for r in req.media),
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        for root in req.media:
            base = root if root.is_dir() else root.parent
            index = {p.name: p for p in base.rglob("*") if p.is_file()}
            for m in media:
                hit = index.get(m.filename)
                if hit:
                    local_paths[m.hash] = str(hit.resolve())
        photos = sum(1 for m in media if m.kind is MediaKind.PHOTO)
        videos = sum(1 for m in media if m.kind is MediaKind.VIDEO)
        progress("media", f"{photos:,} photographs, {videos} videos", 1, 1)

    if not (observations or tracks or media):
        raise ValueError("No usable data in any source.")

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

    # ---------------------------------------------------------------- build
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

    # ---------------------------------------------------------------- enrich
    if req.enrich:
        _enrich(trip, tracks, req, progress)

    # ---------------------------------------------------------------- save
    req.out.mkdir(parents=True, exist_ok=True)

    if req.derivatives and local_paths:
        from trippo.ingest.media.derivatives import generate

        progress("thumbnails", "Making thumbnails", 0, len(media))
        dreport = generate(
            trip.media,
            local_paths,
            req.out,
            progress=lambda d, t: progress("thumbnails", f"{d:,} of {t:,}", d, t),
        )
        if reports:
            reports[-1].degradations.extend(dreport.degradations)
        progress("thumbnails", dreport.summary(), len(media), len(media))

    progress("save", "Writing the capsule", 0, 0)
    capsule_io.write(trip, req.out, local_paths=local_paths, reports=reports)
    for t in tracks:
        (req.out / "tracks").mkdir(parents=True, exist_ok=True)
        (req.out / "tracks" / f"{t.id}.json").write_text(
            json.dumps({"simplified": t.simplified, "profile": t.profile}),
            encoding="utf-8",
        )
    progress("save", f"Saved to {req.out.name}", 1, 1)

    return BuildResult(trip=trip, trace=trace, reports=reports, out=req.out)


def _enrich(trip: Trip, tracks: list[ParsedTrack], req: BuildRequest, progress: Progress) -> None:
    from trippo.domain.models import ActivityDetail
    from trippo.enrich.cache import GeocodeCache
    from trippo.enrich.label import enrich_trip
    from trippo.enrich.nominatim import NominatimGeocoder
    from trippo.enrich.overpass import OverpassGeocoder
    from trippo.enrich.peaks import PeakFinder
    from trippo.enrich.places import resolver_from_env

    cache = GeocodeCache()
    if req.offline:
        progress("enrich", "Offline: using cached names only", 0, 0)
        providers: list[Any] = []
        deep = None
        places = None
    else:
        overpass = OverpassGeocoder()
        providers = [overpass, NominatimGeocoder()]
        deep = overpass.lookup_single_deep
        places = resolver_from_env()
        progress("enrich", "Looking up place names", 0, 0)

    report = enrich_trip(
        trip,
        providers,
        cache,
        deep_lookup=deep,
        places=places,
        progress=lambda d, t, label: progress("enrich", label, d, t),
    )
    progress("enrich", report.summary(), 1, 1)

    if not req.offline:
        by_id = {t.id: t for t in tracks}
        activities = [e for e in trip.active_events if e.track_ids]
        if activities:
            progress("summits", "Looking for summits", 0, len(activities))
            finder = PeakFinder()
            found = 0
            for i, e in enumerate(activities, start=1):
                parsed = by_id.get(e.track_ids[0])
                if parsed is None or not isinstance(e.detail, ActivityDetail):
                    continue
                e.detail.highlights = finder.find(
                    [(p.lat, p.lon) for p in parsed.points],
                    [p.ele for p in parsed.points],
                )
                found += len(e.detail.highlights)
                progress("summits", e.title or "track", i, len(activities))
            progress("summits", f"{found} summits and lakes", len(activities), len(activities))

    cache.close()
