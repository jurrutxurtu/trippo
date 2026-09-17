"""Trippo CLI -- build a draft capsule from any subset of sources.

    python -m trippo.cli build --timeline T.json --gpx tracks/ --media photos/ \
        --from 2023-09-20 --to 2023-10-16 --out ./Ireland.capsule

Every source is optional (ADR-0005). A trip can be built from photos alone.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from trippo.capsule import io as capsule_io
from trippo.domain.models import (
    EventStatus,
    EventType,
    IngestionReport,
    LocationSource,
    MediaAsset,
    MediaKind,
    Source,
    SourceKind,
)
from trippo.draft.builder import BuildInputs, build
from trippo.ingest.gpx.parse import parse_gpx
from trippo.ingest.media.scan import scan_media
from trippo.ingest.timeline.adapters import load as load_timeline


def _as_dt(d: date | None, end: bool = False) -> datetime | None:
    if d is None:
        return None
    return datetime.combine(d, time.max if end else time.min, tzinfo=UTC)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def cmd_build(args: argparse.Namespace) -> int:
    reports: list[IngestionReport] = []
    sources: list[Source] = []
    observations: list = []
    tracks: list = []
    media: list[MediaAsset] = []
    local_paths: dict[str, str] = {}

    win_start, win_end = _as_dt(args.date_from), _as_dt(args.date_to, end=True)

    # ---------------------------------------------------------------- timeline
    if args.timeline:
        path = Path(args.timeline)
        print(f"[timeline] reading {path.name} ...", flush=True)
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        obs, rep = load_timeline(payload, "timeline:0", win_start, win_end)
        observations.extend(obs)
        reports.append(rep)
        sources.append(
            Source(
                id="timeline:0",
                kind=SourceKind.TIMELINE,
                detected_format=rep.detected_format,
                display_name=path.name,
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        print(
            f"           format={rep.detected_format} "
            f"records={rep.records_total} in-window={rep.records_in_window}"
        )

    # ---------------------------------------------------------------- gpx
    if args.gpx:
        root = Path(args.gpx)
        files = sorted(root.rglob("*.gpx")) if root.is_dir() else [root]
        rep = IngestionReport(
            source_id="gpx:0",
            kind=SourceKind.GPX,
            detected_format="gpx",
            confidence=1.0,
            files_seen=len(files),
        )
        for f in files:
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
                    rep.skipped.append({"file": f.name, "reason": "before the date window"})
                    continue
                if win_end and t.start and t.start > win_end:
                    rep.skipped.append({"file": f.name, "reason": "after the date window"})
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
                display_name=str(root.name),
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        print(f"[gpx]      {len(tracks)} track(s) from {rep.files_parsed}/{len(files)} file(s)")

    # ---------------------------------------------------------------- media
    if args.media:
        roots = [Path(p) for p in args.media]
        print(f"[media]    scanning {', '.join(r.name for r in roots)} ...", flush=True)
        media, rep = scan_media(roots, "media:0", win_start, win_end)
        reports.append(rep)
        sources.append(
            Source(
                id="media:0",
                kind=SourceKind.MEDIA,
                detected_format="folder",
                display_name=", ".join(r.name for r in roots),
                imported_at=datetime.now(UTC),
                report=rep,
            )
        )
        for root in roots:
            base = root if root.is_dir() else root.parent
            for m in media:
                hit = next(base.rglob(m.filename), None)
                if hit:
                    local_paths[m.hash] = str(hit.resolve())
        photos = sum(1 for m in media if m.kind is MediaKind.PHOTO)
        videos = sum(1 for m in media if m.kind is MediaKind.VIDEO)
        print(f"           {photos} photo(s), {videos} video(s), {len(rep.skipped)} skipped")

    if not (observations or tracks or media):
        print("error: no usable data in any source", file=sys.stderr)
        return 2

    # ---------------------------------------------------------------- media observations
    from trippo.observe.models import NormalizedObservation, ObservationKind

    observations.extend(
        NormalizedObservation(
            t=m.captured_at,
            kind=ObservationKind.MEDIA,
            source_id="media:0",
            lat=m.lat,
            lon=m.lon,
            ref=m.id,
            # Only a camera-recorded fix counts as a measurement. Anything Trippo works
            # out later must not feed back into the position index.
            trusted_position=m.location_source is LocationSource.EXIF,
        )
        for m in media
        if m.captured_at is not None
    )

    # ---------------------------------------------------------------- build
    print("[build]    running the draft pipeline ...", flush=True)
    trip, trace = build(
        BuildInputs(
            title=args.title,
            observations=observations,
            tracks=tracks,
            media=media,
            window_start=args.date_from,
            window_end=args.date_to,
            default_offset_minutes=args.default_offset,
        )
    )
    trip.sources = sources

    # ---------------------------------------------------------------- enrich
    if args.enrich:
        _enrich(trip, args, {t.id: t for t in tracks})

    _print_summary(trip, trace, reports)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)

        if args.derivatives and local_paths:
            from trippo.ingest.media.derivatives import generate

            print("[thumbs]   generating derivatives ...", flush=True)

            def dprog(done: int, total: int) -> None:
                print(f"           {done}/{total}", flush=True, end="\r")

            dreport = generate(trip.media, local_paths, out, progress=dprog)
            print(" " * 40, end="\r")
            print(f"[thumbs]   {dreport.summary()}")
            for d in dreport.degradations:
                print(f"           ! {d}")

        capsule_io.write(trip, out, local_paths=local_paths, reports=reports)
        # Track originals and simplified geometry live beside capsule.json.
        for t in tracks:
            (out / "tracks").mkdir(parents=True, exist_ok=True)
            (out / "tracks" / f"{t.id}.json").write_text(
                json.dumps({"simplified": t.simplified, "profile": t.profile}),
                encoding="utf-8",
            )
        print(f"\n[capsule]  written to {out.resolve()}")
    return 0


def _enrich(trip, args: argparse.Namespace, tracks_by_id: dict) -> None:
    """Resolve place names. Never fatal -- providers are public and best-effort."""
    from trippo.domain.stats import compute_trip_stats
    from trippo.enrich.cache import GeocodeCache
    from trippo.enrich.label import enrich_trip
    from trippo.enrich.nominatim import NominatimGeocoder
    from trippo.enrich.overpass import OverpassGeocoder

    cache = GeocodeCache(Path(args.cache) if args.cache else None)
    if args.offline:
        # Cache-only: resolves whatever has been seen before, asks nothing of the network.
        providers: list = [_CacheOnly("overpass"), _CacheOnly("nominatim")]
        deep = None
        print("[enrich]   offline: using cached results only")
    else:
        overpass = OverpassGeocoder()
        providers = [overpass, NominatimGeocoder()]
        deep = overpass.lookup_single_deep
        print("[enrich]   resolving place names (Overpass -> Nominatim) ...", flush=True)

    def progress(done: int, total: int, label: str) -> None:
        print(f"           {done}/{total}  {label:<20}", flush=True, end="\r")

    report = enrich_trip(trip, providers, cache, deep_lookup=deep, progress=progress)

    if not args.offline:
        _find_summits(trip, tracks_by_id)

    cache.close()
    print(" " * 60, end="\r")
    print(f"[enrich]   {report.summary()}")
    for d in report.degradations:
        print(f"           ! {d}")
    trip.stats = compute_trip_stats(trip)


def _find_summits(trip, tracks_by_id: dict) -> None:
    """Name the summits, passes and lakes each activity passed.

    Uses full track points, not the simplified line: a summit is a few tens of metres
    off-route and simplification can move the line past it.
    """
    from trippo.domain.models import ActivityDetail
    from trippo.enrich.peaks import PeakFinder

    activities = [e for e in trip.active_events if e.track_ids]
    if not activities:
        return

    finder = PeakFinder()
    total = 0
    print(f"[summits]  scanning {len(activities)} activity track(s) ...", flush=True)
    for e in activities:
        parsed = tracks_by_id.get(e.track_ids[0])
        if parsed is None or not isinstance(e.detail, ActivityDetail):
            continue
        path = [(p.lat, p.lon) for p in parsed.points]
        eles = [p.ele for p in parsed.points]
        highlights = finder.find(path, eles)
        e.detail.highlights = highlights
        total += len(highlights)
        peaks = [h.name for h in highlights if h.kind == "natural=peak"]
        if peaks:
            print(f"           {e.title}: {', '.join(peaks[:3])}")

    print(f"[summits]  {total} feature(s) across {len(activities)} track(s)")
    if finder.failures:
        print(f"           ! {finder.failures} Overpass request(s) failed")


class _CacheOnly:
    """A provider that never leaves the machine. Used by --offline and by tests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.failures = 0

    def lookup(self, queries):
        return {i: [] for i in range(len(queries))}


def _print_summary(trip, trace, reports: list[IngestionReport]) -> None:
    print("\n" + "=" * 78)
    print(f"  {trip.title}   {trip.date_range.start} -> {trip.date_range.end}")
    print("=" * 78)

    s = trip.stats
    print(
        f"  days={s.day_count}  events={s.event_count}  suppressed={s.suppressed_event_count}  "
        f"overnights={s.overnight_count}  tracks={s.track_count}"
    )
    print(f"  photos={s.photo_count}  videos={s.video_count}  blind days={s.days_blind}")
    if s.distance_by_mode_m:
        modes = "  ".join(f"{k}={v / 1000:.0f}km" for k, v in sorted(s.distance_by_mode_m.items()))
        print(f"  distance: {modes}")
    print(f"  unaccounted: {s.unaccounted_count} gap(s), {s.unaccounted_hours:.1f} h")
    located = trace.media_gps_exif + trace.inferred_positions
    total_media = s.photo_count + s.video_count
    if total_media:
        print(
            f"  media positions: {trace.media_gps_exif} from EXIF GPS, "
            f"{trace.inferred_positions} inferred, {trace.unlocatable_media} unlocatable "
            f"({located}/{total_media} located)"
        )
    if trace.events_placed_by_media:
        print(f"  {trace.events_placed_by_media} event(s) located from their photos")

    degradations = [d for r in reports for d in r.degradations]
    if degradations:
        print("\n  -- degradations ------------------------------------------------")
        for d in degradations:
            print(f"   ! {d}")

    if trace.phantoms:
        print("\n  -- phantom stops absorbed (P1) ---------------------------------")
        for p in trace.phantoms:
            print(f"   ~ {p}")

    if trace.gaps:
        print("\n  -- unaccounted gaps (ADR-0007) ---------------------------------")
        for g in trace.gaps:
            print(f"   ? {g}")

    if trace.masked_by_gpx:
        print(f"\n  -- {len(trace.masked_by_gpx)} segment(s) superseded by GPX (ADR-0004)")
    if trace.dropped_duplicates:
        print(f"  -- {len(trace.dropped_duplicates)} duplicate visit(s) removed (P4)")

    print("\n  -- itinerary ---------------------------------------------------")
    for day in trip.days:
        active = [
            e
            for e in (trip.event_by_id(i) for i in day.event_ids)
            if e and e.status is EventStatus.ACTIVE
        ]
        spanning = [
            e
            for e in (trip.event_by_id(i) for i in day.spanning_event_ids)
            if e and e.status is EventStatus.ACTIVE
        ]
        hidden = len(day.event_ids) - len(active)
        cov = next((c for c in s.coverage if c.date == day.date), None)
        flag = "  [NO DATA]" if cov and cov.blind else ""
        print(f"\n  D{day.index:<2} {day.date}  ({len(active)} events, {hidden} hidden){flag}")
        for e in spanning:
            label = e.title or (e.place.name if e.place else "")
            print(f"     ...    continues  {label[:44]}")
        for e in active:
            mark = "?" if e.type is EventType.UNKNOWN else " "
            label = e.title or (e.place.name if e.place else "")
            extra = ""
            if e.track_ids:
                st = trip.track_by_id(e.track_ids[0])
                if st:
                    extra = f"  [{st.stats.distance_m / 1000:.1f} km, +{st.stats.ascent_m:.0f} m]"
            if e.media_ids:
                extra += f"  ({len(e.media_ids)} media)"
            local_start = e.start + timedelta(minutes=e.utc_offset_minutes or 0)
            print(f"   {mark} {local_start:%H:%M}  {e.type.value:<9} {label[:44]:<44}{extra}")


def _force_utf8_stdout() -> None:
    """Windows consoles still default to cp1252, which cannot print an arrow.

    Place names are arbitrary Unicode -- Irish, Basque, accented French -- so the CLI
    must never die on output. Reconfigure where possible, and replace what cannot be
    encoded rather than raising.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    p = argparse.ArgumentParser(prog="trippo", description="Trippo travel memory studio")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build a draft capsule from raw sources")
    b.add_argument("--timeline", help="Google Timeline export JSON")
    b.add_argument("--gpx", help="GPX file or folder")
    b.add_argument("--media", nargs="*", default=[], help="photo/video folder(s)")
    b.add_argument("--from", dest="date_from", type=_parse_date)
    b.add_argument("--to", dest="date_to", type=_parse_date)
    b.add_argument("--title", default="Untitled trip")
    b.add_argument("--default-offset", type=int, default=0, help="fallback UTC offset, minutes")
    b.add_argument("--out", help="capsule directory to write")
    b.add_argument(
        "--enrich", action="store_true", help="resolve place names (Overpass -> Nominatim)"
    )
    b.add_argument(
        "--offline", action="store_true", help="enrich from the cache only; no network"
    )
    b.add_argument("--cache", help="geocode cache path (default ~/.trippo/)")
    b.add_argument(
        "--derivatives",
        action="store_true",
        help="generate thumbnails and web-sized copies into the capsule",
    )
    b.set_defaults(func=cmd_build)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
