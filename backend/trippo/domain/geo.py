"""Pure geometry helpers. No I/O, no dependencies beyond the standard library."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

from trippo.config.heuristics import EARTH_RADIUS_M

Coord = tuple[float, float]  # (lat, lon)


def haversine_m(a: Coord, b: Coord) -> float:
    """Great-circle distance in metres between two (lat, lon) pairs."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def path_length_m(points: Sequence[Coord]) -> float:
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def centroid(points: Sequence[Coord]) -> Coord:
    """Spherical centroid. Correct across the antimeridian, unlike a naive mean."""
    if not points:
        raise ValueError("centroid of empty sequence")
    x = y = z = 0.0
    for lat, lon in points:
        la, lo = math.radians(lat), math.radians(lon)
        x += math.cos(la) * math.cos(lo)
        y += math.cos(la) * math.sin(lo)
        z += math.sin(la)
    n = len(points)
    x, y, z = x / n, y / n, z / n
    lon = math.atan2(y, x)
    lat = math.atan2(z, math.hypot(x, y))
    return (math.degrees(lat), math.degrees(lon))


def bbox(points: Sequence[Coord]) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon)."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (min(lats), min(lons), max(lats), max(lons))


def union_bbox(
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float] | None:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def pad_bbox(
    box: tuple[float, float, float, float], metres: float
) -> tuple[float, float, float, float]:
    """Grow a box by roughly `metres` on every side.

    A bbox fitted exactly to a track puts the trailhead against the window edge; the map
    needs breathing room before it looks deliberate.
    """
    dlat = metres / 111_320.0
    mid_lat = math.radians((box[0] + box[2]) / 2)
    dlon = metres / max(111_320.0 * math.cos(mid_lat), 1.0)
    return (box[0] - dlat, box[1] - dlon, box[2] + dlat, box[3] + dlon)


def distance_to_path(p: Coord, path: Sequence[Coord]) -> float:
    """Shortest distance in metres from a point to a polyline.

    Used to decide whether a summit lies *on* a hike or merely nearby.
    """
    if not path:
        return float("inf")
    if len(path) == 1:
        return haversine_m(p, path[0])
    return min(
        _perpendicular_distance_m(p, a, b) for a, b in pairwise(path)
    )


def offset_along_path(p: Coord, path: Sequence[Coord]) -> float:
    """Cumulative distance in metres to the point on `path` nearest to `p`.

    Lets summits and photographs be ordered along a route rather than by clock time --
    which matters on an out-and-back, where the clock doubles back on itself.
    """
    if len(path) < 2:
        return 0.0
    best_d = float("inf")
    best_offset = 0.0
    cum = 0.0
    for a, b in pairwise(path):
        d = _perpendicular_distance_m(p, a, b)
        if d < best_d:
            best_d = d
            best_offset = cum + haversine_m(a, p)
        cum += haversine_m(a, b)
    return best_offset


def interpolate(a: Coord, b: Coord, frac: float) -> Coord:
    """Linear interpolation. Adequate for the sub-kilometre gaps this is used for."""
    frac = max(0.0, min(1.0, frac))
    return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)


def _perpendicular_distance_m(p: Coord, a: Coord, b: Coord) -> float:
    """Distance from p to segment a-b, in metres, via a local equirectangular projection."""
    if a == b:
        return haversine_m(p, a)
    lat0 = math.radians((a[0] + b[0]) / 2)
    mx = EARTH_RADIUS_M * math.cos(lat0)

    def proj(c: Coord) -> tuple[float, float]:
        return (math.radians(c[1]) * mx, math.radians(c[0]) * EARTH_RADIUS_M)

    px, py = proj(p)
    ax, ay = proj(a)
    bx, by = proj(b)
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points: Sequence[Coord], tolerance_m: float) -> list[Coord]:
    """Iterative Douglas-Peucker. Iterative to avoid recursion limits on 10k-point tracks."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        worst_i, worst_d = -1, 0.0
        for i in range(start + 1, end):
            d = _perpendicular_distance_m(points[i], points[start], points[end])
            if d > worst_d:
                worst_i, worst_d = i, d
        if worst_d > tolerance_m:
            keep[worst_i] = True
            stack.append((start, worst_i))
            stack.append((worst_i, end))
    return [p for p, k in zip(points, keep, strict=True) if k]


def downsample(points: Sequence[Coord], max_points: int) -> list[Coord]:
    """Evenly thin a sequence, always preserving the first and last point."""
    if len(points) <= max_points or max_points < 2:
        return list(points)
    step = (len(points) - 1) / (max_points - 1)
    out = [points[round(i * step)] for i in range(max_points)]
    out[-1] = points[-1]
    return out
