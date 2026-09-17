"""Media scanning: EXIF, timestamps, dedup, video metadata.

Timestamp cascade (docs/technical/ingestion.md):
  1. DateTimeOriginal + OffsetTimeOriginal -- exact instant
  2. DateTimeOriginal alone -- naive local, resolved later against the day timezone
  3. Filename pattern (Pixel `PXL_YYYYMMDD_HHMMSSmmm`, and friends)
  4. Filesystem mtime -- weak, flagged in the report

Never loads pixel data during the scan: EXIF comes from the header, and thumbnails are
extracted from the embedded preview whenever one exists.
"""

from __future__ import annotations

import hashlib
import re
import struct
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from trippo.domain.models import (
    IngestionReport,
    LocationSource,
    MediaAsset,
    MediaKind,
    MediaVariant,
    SourceKind,
    TimeSource,
)

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp"}
RAW_EXT = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2"}

#: Google Photos export prefix, e.g. `original_<uuid>_PXL_20230928_192141554.jpg` (P6 note).
_GPHOTOS_PREFIX = re.compile(r"^original_[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}_", re.I)
#: Duplicate suffix added on re-download, e.g. `PXL_20230927_101112131~2.jpg`.
_DUP_SUFFIX = re.compile(r"~\d+(?=\.[^.]+$)")

_FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"PXL_(\d{8})_(\d{6})(\d{0,3})"),  # Google Pixel
    re.compile(r"IMG_(\d{8})_(\d{6})"),  # many Android OEMs
    re.compile(r"VID_(\d{8})_(\d{6})"),
    re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_ T](\d{2})[-_:]?(\d{2})[-_:]?(\d{2})"),
)

_VARIANTS = {
    ".MP": MediaVariant.MOTION_PHOTO,
    ".NIGHT": MediaVariant.NIGHT,
    ".PANO": MediaVariant.PANO,
}


def normalize_filename(name: str) -> str:
    name = _GPHOTOS_PREFIX.sub("", name)
    return _DUP_SUFFIX.sub("", name)


def detect_variant(name: str) -> MediaVariant | None:
    stem = Path(name).stem
    for token, variant in _VARIANTS.items():
        if stem.upper().endswith(token) or token in stem.upper():
            return variant
    return None


def quick_hash(path: Path, size: int) -> str:
    """Content-addressed enough for dedup, cheap enough for 8 GB.

    Hashing 3.4 GB of pixels to notice two copies of a photo is not a good trade; the first
    64 KB plus the exact byte length is decisive in practice.
    """
    h = hashlib.sha1()
    h.update(str(size).encode())
    try:
        with path.open("rb") as fh:
            h.update(fh.read(65_536))
    except OSError:
        h.update(path.name.encode("utf-8", "replace"))
    return h.hexdigest()[:20]


def time_from_filename(name: str) -> datetime | None:
    """Naive local time encoded in the filename. Returns tz-naive on purpose."""
    for pat in _FILENAME_PATTERNS:
        m = pat.search(name)
        if not m:
            continue
        g = m.groups()
        try:
            if len(g) >= 6:
                y, mo, d, hh, mm, ss = (int(x) for x in g[:6])
            else:
                ymd, hms = g[0], g[1]
                y, mo, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])
                hh, mm, ss = int(hms[:2]), int(hms[2:4]), int(hms[4:6])
            return datetime(y, mo, d, hh, mm, ss)
        except (ValueError, IndexError):
            continue
    return None


# --------------------------------------------------------------------------- EXIF


def _read_exif(path: Path) -> dict[str, object]:
    """EXIF via Pillow, header only. Returns {} on any failure -- never raises."""
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return {}
    try:
        with Image.open(path) as im:
            width, height = im.size
            exif = im.getexif()
            if not exif:
                return {"width": width, "height": height}
            out: dict[str, object] = {"width": width, "height": height}
            for tag_id, value in exif.items():
                name = ExifTags.TAGS.get(tag_id)
                if name:
                    out[name] = value
            ifd = exif.get_ifd(0x8769)  # ExifIFD
            for tag_id, value in ifd.items():
                name = ExifTags.TAGS.get(tag_id)
                if name:
                    out[name] = value
            gps = exif.get_ifd(0x8825)  # GPSInfo
            if gps:
                out["_gps"] = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
            return out
    except Exception:
        return {}


def _gps_to_degrees(value: object, ref: object) -> float | None:
    try:
        d, m, s = (float(x) for x in value)  # type: ignore[misc,attr-defined]
    except (TypeError, ValueError):
        return None
    deg = d + m / 60 + s / 3600
    if str(ref).upper() in {"S", "W"}:
        deg = -deg
    return deg


def _parse_offset(value: object) -> timezone | None:
    """`OffsetTimeOriginal` looks like `+02:00`."""
    s = str(value or "").strip()
    m = re.match(r"^([+-])(\d{2}):?(\d{2})$", s)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


# --------------------------------------------------------------------------- video


def _mp4_creation_time(path: Path) -> datetime | None:
    """Read `mvhd` creation time without ffmpeg. Returns None when unreadable.

    MP4 timestamps are seconds since 1904-01-01 UTC.
    """
    epoch_1904 = datetime(1904, 1, 1, tzinfo=UTC)
    try:
        with path.open("rb") as fh:
            data = fh.read(2_000_000)
    except OSError:
        return None
    idx = data.find(b"mvhd")
    if idx < 0:
        return None
    try:
        version = data[idx + 4]
        if version == 1:
            created = struct.unpack(">Q", data[idx + 8 : idx + 16])[0]
        else:
            created = struct.unpack(">I", data[idx + 8 : idx + 12])[0]
    except (struct.error, IndexError):
        return None
    if created <= 0:
        return None
    try:
        dt = epoch_1904 + timedelta(seconds=created)
    except OverflowError:
        return None
    return dt if 1990 < dt.year < 2100 else None


# --------------------------------------------------------------------------- scan


def scan_media(
    roots: list[Path],
    source_id: str,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    default_tz: timezone = UTC,
) -> tuple[list[MediaAsset], IngestionReport]:
    report = IngestionReport(
        source_id=source_id, kind=SourceKind.MEDIA, detected_format="folder", confidence=1.0
    )
    assets: list[MediaAsset] = []
    seen_hashes: dict[str, str] = {}
    gps_count = 0
    exact_time = 0
    pad = timedelta(days=1)

    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(p for p in root.rglob("*") if p.is_file())
    report.files_seen = len(files)

    for path in sorted(files):
        ext = path.suffix.lower()
        if ext in RAW_EXT:
            report.skipped.append({"file": path.name, "reason": "RAW not supported in the POC"})
            continue
        if ext in PHOTO_EXT:
            kind = MediaKind.PHOTO
        elif ext in VIDEO_EXT:
            kind = MediaKind.VIDEO
        else:
            report.skipped.append({"file": path.name, "reason": f"unsupported extension {ext}"})
            continue

        try:
            stat = path.stat()
        except OSError as exc:
            report.skipped.append({"file": path.name, "reason": f"unreadable: {exc}"})
            continue

        norm = normalize_filename(path.name)
        h = quick_hash(path, stat.st_size)
        if h in seen_hashes:
            report.skipped.append({"file": path.name, "reason": f"duplicate of {seen_hashes[h]}"})
            continue

        # Read EXIF exactly once per file and share it with the timestamp cascade.
        exif = _read_exif(path) if kind is MediaKind.PHOTO else {}
        captured, tsource, tz_used = _resolve_time(
            path, kind, norm, stat.st_mtime, default_tz, exif
        )
        lat = lon = None
        loc_source = LocationSource.NONE
        width = height = orientation = None
        device = None
        duration = None

        if kind is MediaKind.PHOTO:
            width = exif.get("width")  # type: ignore[assignment]
            height = exif.get("height")  # type: ignore[assignment]
            orientation = exif.get("Orientation")  # type: ignore[assignment]
            make, model = exif.get("Make"), exif.get("Model")
            if make or model:
                device = f"{make or ''} {model or ''}".strip()
            gps = exif.get("_gps")
            if isinstance(gps, dict):
                lat = _gps_to_degrees(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
                lon = _gps_to_degrees(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
                if lat is not None and lon is not None:
                    loc_source = LocationSource.EXIF
                    gps_count += 1

        if captured is not None and tsource is TimeSource.EXIF:
            exact_time += 1

        if captured is not None and not _within(captured, window_start, window_end, pad):
            report.skipped.append({"file": path.name, "reason": "outside the selected date window"})
            continue

        seen_hashes[h] = path.name
        assets.append(
            MediaAsset(
                id=f"med_{h}",
                hash=h,
                kind=kind,
                filename=path.name,
                normalized_filename=norm,
                captured_at=captured,
                timezone=str(tz_used),
                time_source=tsource,
                lat=lat,
                lon=lon,
                location_source=loc_source,
                width=width,
                height=height,
                orientation=orientation if isinstance(orientation, int) else None,
                device_id=device,
                variant=detect_variant(norm),
                duration_s=duration,
                excluded_from_export=kind is MediaKind.VIDEO,
                size_bytes=stat.st_size,
            )
        )

    report.files_parsed = len(assets)
    report.records_total = len(files)
    report.records_in_window = len(assets)
    _media_degradations(report, assets, gps_count)
    return assets, report


def _within(t: datetime, start: datetime | None, end: datetime | None, pad: timedelta) -> bool:
    if start and t < start - pad:
        return False
    return not (end and t > end + pad)


def _resolve_time(
    path: Path,
    kind: MediaKind,
    norm_name: str,
    mtime: float,
    default_tz: timezone,
    exif: dict[str, object],
) -> tuple[datetime | None, TimeSource, timezone]:
    if kind is MediaKind.PHOTO:
        raw = exif.get("DateTimeOriginal") or exif.get("DateTime")
        offset = _parse_offset(exif.get("OffsetTimeOriginal") or exif.get("OffsetTime"))
        if raw:
            try:
                naive = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            except ValueError:
                naive = None
            if naive is not None:
                if offset is not None:
                    return naive.replace(tzinfo=offset), TimeSource.EXIF, offset
                return naive.replace(tzinfo=default_tz), TimeSource.EXIF_NO_OFFSET, default_tz
    elif (created := _mp4_creation_time(path)) is not None:
        return created, TimeSource.EXIF, UTC

    if (from_name := time_from_filename(norm_name)) is not None:
        return from_name.replace(tzinfo=default_tz), TimeSource.FILENAME, default_tz

    return datetime.fromtimestamp(mtime, tz=default_tz), TimeSource.MTIME, default_tz


def _media_degradations(report: IngestionReport, assets: list[MediaAsset], gps_count: int) -> None:
    total = len(assets)
    if total == 0:
        report.degradations.append("No supported media found.")
        return

    if gps_count == 0:
        # Actionable, and it materially changes what the app can do. Pathology P6.
        report.degradations.append(
            f"0 of {total} media files contain GPS coordinates. Positions will be inferred "
            "from timeline or GPX data where possible. If these came from a Google Photos "
            "export, re-exporting with location data enabled would substantially improve "
            "results."
        )
    elif gps_count < total // 2:
        report.degradations.append(
            f"Only {gps_count} of {total} media files contain GPS; the rest will be "
            "positioned by inference."
        )

    weak = sum(1 for a in assets if a.time_source is TimeSource.MTIME)
    if weak:
        report.degradations.append(
            f"{weak} file(s) have no reliable timestamp and fell back to file modification "
            "time. They may land on the wrong day."
        )

    videos = sum(1 for a in assets if a.kind is MediaKind.VIDEO)
    if videos:
        report.notes.append(
            f"{videos} video(s) imported (metadata only; excluded from export in this version)."
        )

    by_source: dict[str, int] = {}
    for a in assets:
        by_source[a.time_source.value] = by_source.get(a.time_source.value, 0) + 1
    report.notes.append("timestamp sources: " + ", ".join(f"{k}={v}" for k, v in by_source.items()))

    devices = {a.device_id for a in assets if a.device_id}
    if len(devices) > 1:
        report.notes.append(
            f"{len(devices)} capture devices detected: {', '.join(sorted(devices))}. "
            "Per-device clock offsets may need correcting."
        )
