"""Pure geometry helpers. No I/O, no dependencies beyond the standard library."""

from __future__ import annotations

import math
from collections.abc import Sequence

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
