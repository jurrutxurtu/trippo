"""GPX parsing -> Track + telemetry.

Uses ElementTree rather than a GPX library: the file layouts in the wild vary (Garmin
Connect, Strava, Wikiloc, AllTrails), namespaces are inconsistent, and we need the Garmin
`TrackPointExtension` (heart rate, cadence, temperature) which most libraries drop.

Track identity comes from `<trk><name>` plus a start-time hash, NEVER the filename:
six reference files were `activity_<garminId>.gpx` and one was `Activity1.gpx` (P8).
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise

from dateutil import parser as dtparse

from trippo.config.heuristics import (
    ELEVATION_SMOOTH_WINDOW,
    ELEVATION_THRESHOLD_M,
    GPX_SIMPLIFY_MAX_POINTS,
    GPX_SIMPLIFY_TOLERANCE_M,
    MOVING_SPEED_MIN_KMH,
)
from trippo.domain.geo import bbox, downsample, haversine_m, simplify
from trippo.domain.models import TrackStats


@dataclass(slots=True)
class TrackPoint:
    t: datetime | None
    lat: float
    lon: float
    ele: float | None = None
    hr: int | None = None


@dataclass(slots=True)
class ParsedTrack:
    id: str
    name: str
    activity_type: str | None
    points: list[TrackPoint]
    stats: TrackStats
    simplified: list[tuple[float, float]] = field(default_factory=list)
    profile: list[dict[str, float]] = field(default_factory=list)

    @property
    def start(self) -> datetime | None:
        return next((p.t for p in self.points if p.t), None)

    @property
    def end(self) -> datetime | None:
        return next((p.t for p in reversed(self.points) if p.t), None)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_local(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el.iter() if _local(c.tag) == name), None)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = dtparse.isoparse(value.strip())
    except (ValueError, OverflowError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def parse_gpx(data: bytes, fallback_name: str) -> list[ParsedTrack]:
    """Parse every `<trk>` in a GPX document. Malformed input raises `ET.ParseError`."""
    root = ET.fromstring(data)
    tracks: list[ParsedTrack] = []

    for ti, trk in enumerate(c for c in root.iter() if _local(c.tag) == "trk"):
        name_el = next((c for c in trk if _local(c.tag) == "name"), None)
        type_el = next((c for c in trk if _local(c.tag) == "type"), None)
        name = (name_el.text or "").strip() if name_el is not None else ""
        activity_type = (type_el.text or "").strip().lower() if type_el is not None else None

        points: list[TrackPoint] = []
        for pt in (c for c in trk.iter() if _local(c.tag) == "trkpt"):
            try:
                lat = float(pt.attrib["lat"])
                lon = float(pt.attrib["lon"])
            except (KeyError, ValueError):
                continue
            ele_el = next((c for c in pt if _local(c.tag) == "ele"), None)
            time_el = next((c for c in pt if _local(c.tag) == "time"), None)
            hr_el = _find_local(pt, "hr")
            ele = None
            if ele_el is not None and ele_el.text:
                try:
                    ele = float(ele_el.text)
                except ValueError:
                    ele = None
            hr = None
            if hr_el is not None and hr_el.text:
                try:
                    hr = int(float(hr_el.text))
                except ValueError:
                    hr = None
            points.append(
                TrackPoint(
                    t=_parse_time(time_el.text if time_el is not None else None),
                    lat=lat,
                    lon=lon,
                    ele=ele,
                    hr=hr,
                )
            )

        if not points:
            continue

        display = name or fallback_name or f"Track {ti + 1}"
        tid = _track_id(display, points[0].t)
        coords = [(p.lat, p.lon) for p in points]
        simp = simplify(coords, GPX_SIMPLIFY_TOLERANCE_M)
        if len(simp) > GPX_SIMPLIFY_MAX_POINTS:
            simp = downsample(simp, GPX_SIMPLIFY_MAX_POINTS)

        tracks.append(
            ParsedTrack(
                id=tid,
                name=display,
                activity_type=activity_type,
                points=points,
                stats=compute_stats(points),
                simplified=simp,
                profile=build_profile(points),
            )
        )
    return tracks


def _track_id(name: str, start: datetime | None) -> str:
    seed = f"{name}|{start.isoformat() if start else 'no-time'}"
    return "trk_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _smooth(values: list[float], window: int) -> list[float]:
    """Centred moving average. Kills oscillation without shifting real gradients."""
    if window <= 1 or len(values) <= window:
        return list(values)
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo, hi = max(0, i - half), min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def accumulate_elevation(eles: list[float]) -> tuple[float, float]:
    """Return (ascent, descent) in metres.

    Two stages, because either alone is insufficient:

    1. **Smooth.** A bare threshold filter still accumulates when the noise amplitude
       exceeds the threshold -- alternating +-2.5 m samples produce 5 m swings and a flat
       ride reports hundreds of metres of climbing.
    2. **Threshold.** Smoothing alone leaves small residual drift over thousands of points.

    Together they give figures that match what a watch reports.
    """
    if len(eles) < 2:
        return (0.0, 0.0)

    smoothed = _smooth(eles, ELEVATION_SMOOTH_WINDOW)
    ascent = descent = 0.0
    anchor = smoothed[0]
    for e in smoothed[1:]:
        delta = e - anchor
        if delta >= ELEVATION_THRESHOLD_M:
            ascent += delta
            anchor = e
        elif delta <= -ELEVATION_THRESHOLD_M:
            descent += -delta
            anchor = e
    return (ascent, descent)


def compute_stats(points: list[TrackPoint]) -> TrackStats:
    """Distance, filtered ascent/descent, moving time and heart rate.

    The elevation filter is load-bearing: raw GPS altitude noise makes a flat ride report
    +1,400 m of climbing. The threshold is stored in the result so the UI can disclose it.
    """
    dist = 0.0
    moving = 0.0
    elapsed = 0.0

    eles = [p.ele for p in points if p.ele is not None]
    hrs = [p.hr for p in points if p.hr is not None]

    ascent, descent = accumulate_elevation(eles)

    for a, b in pairwise(points):
        d = haversine_m((a.lat, a.lon), (b.lat, b.lon))
        dist += d
        if a.t and b.t:
            dt = (b.t - a.t).total_seconds()
            if dt > 0:
                elapsed += dt
                if (d / dt) * 3.6 >= MOVING_SPEED_MIN_KMH:
                    moving += dt

    return TrackStats(
        distance_m=round(dist, 1),
        ascent_m=round(ascent, 1),
        descent_m=round(descent, 1),
        max_ele_m=round(max(eles), 1) if eles else None,
        min_ele_m=round(min(eles), 1) if eles else None,
        moving_time_s=round(moving, 1),
        elapsed_time_s=round(elapsed, 1),
        avg_hr=round(sum(hrs) / len(hrs), 1) if hrs else None,
        max_hr=float(max(hrs)) if hrs else None,
        elevation_threshold_m=ELEVATION_THRESHOLD_M,
    )


def build_profile(points: list[TrackPoint], max_points: int = 800) -> list[dict[str, float]]:
    """Resampled array for the elevation chart.

    Each entry carries cumulative distance, elevation AND lat/lon, so the chart and the map
    share a single cursor index -- hovering either drives the other with no lookup.
    """
    if not points:
        return []
    rows: list[dict[str, float]] = []
    cum = 0.0
    prev: TrackPoint | None = None
    for p in points:
        if prev is not None:
            cum += haversine_m((prev.lat, prev.lon), (p.lat, p.lon))
        rows.append(
            {
                "d": round(cum, 1),
                "ele": round(p.ele, 1) if p.ele is not None else 0.0,
                "lat": p.lat,
                "lon": p.lon,
                "t": p.t.timestamp() if p.t else 0.0,
            }
        )
        prev = p
    if len(rows) <= max_points:
        return rows
    step = (len(rows) - 1) / (max_points - 1)
    out = [rows[round(i * step)] for i in range(max_points)]
    out[-1] = rows[-1]
    return out


def track_bbox(points: list[TrackPoint]) -> tuple[float, float, float, float]:
    return bbox([(p.lat, p.lon) for p in points])
