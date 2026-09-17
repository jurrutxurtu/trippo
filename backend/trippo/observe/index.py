"""PositionIndex -- "where was the user at time T?"

Built from every *measured* position: timeline breadcrumbs (Layer 2, ADR-0009), GPX
trackpoints, and EXIF-geotagged media. Used to give photos a position when EXIF has none
(pathology P6), and to give sparse crossings a geometry.

Two rules keep this honest:

* **Only trusted positions contribute.** A position Trippo inferred must never become
  evidence for the next inference -- that compounds error and manufactures a route out of
  nothing. Geotagged photos *are* measurements and do contribute; a single geotagged shot
  can locate the whole burst around it.
* **Never interpolate across a void.** Returns `None` rather than guessing. A photo taken
  mid-ferry with no covering source is genuinely unlocatable, and the product says so
  instead of inventing a coordinate (ADR-0007).
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta

from trippo.domain.geo import interpolate
from trippo.observe.models import NormalizedObservation

#: Never interpolate across a hole larger than this -- the result would be fiction.
MAX_INTERPOLATION_GAP = timedelta(hours=1)


class PositionIndex:
    def __init__(self, observations: list[NormalizedObservation]) -> None:
        fixes: list[tuple[datetime, float, float]] = []
        for o in observations:
            if not o.trusted_position:
                continue
            if o.has_position:
                fixes.append((o.t, o.lat, o.lon))  # type: ignore[arg-type]
            if o.end_t and o.end_lat is not None and o.end_lon is not None:
                fixes.append((o.end_t, o.end_lat, o.end_lon))
        fixes.sort(key=lambda f: f[0])
        self._times = [f[0] for f in fixes]
        self._coords = [(f[1], f[2]) for f in fixes]

    def __len__(self) -> int:
        return len(self._times)

    @property
    def covered(self) -> tuple[datetime, datetime] | None:
        return (self._times[0], self._times[-1]) if self._times else None

    def at(self, t: datetime) -> tuple[float, float] | None:
        """Interpolated position at `t`, or None when no source plausibly covers it."""
        if not self._times:
            return None
        i = bisect.bisect_left(self._times, t)
        if i == 0:
            return self._coords[0] if self._times[0] - t <= MAX_INTERPOLATION_GAP else None
        if i >= len(self._times):
            return self._coords[-1] if t - self._times[-1] <= MAX_INTERPOLATION_GAP else None

        t0, t1 = self._times[i - 1], self._times[i]
        if t1 - t0 > MAX_INTERPOLATION_GAP:
            # Inside a void. Snap only if genuinely close to one end.
            if t - t0 <= MAX_INTERPOLATION_GAP:
                return self._coords[i - 1]
            if t1 - t <= MAX_INTERPOLATION_GAP:
                return self._coords[i]
            return None

        span = (t1 - t0).total_seconds()
        frac = 0.0 if span <= 0 else (t - t0).total_seconds() / span
        return interpolate(self._coords[i - 1], self._coords[i], frac)

    def between(self, start: datetime, end: datetime) -> list[tuple[float, float]]:
        """Positions recorded within a window -- the geometry of a leg."""
        lo = bisect.bisect_left(self._times, start)
        hi = bisect.bisect_right(self._times, end)
        return self._coords[lo:hi]
