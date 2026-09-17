"""The plausibility gate. Pathology P1 -- the single most important heuristic in Trippo.

Google reported a `visit` of 8 h 36 m anchored at Rosslare Harbour while the phone was
actually in the middle of the Irish Sea. It spans local 02:00-05:00, so a naive overnight
rule emits "Overnight stay, Rosslare Harbour" -- precisely the "traffic jam treated as a
destination" failure this product exists to prevent.

A stationary period that would require impossible ground speed to reach the next known fix
was not stationary. It was motion. This runs BEFORE overnight detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trippo.config.heuristics import MAX_GROUND_SPEED_KMH
from trippo.domain.geo import haversine_m
from trippo.observe.models import NormalizedObservation, ObservationKind


@dataclass(slots=True)
class PhantomVerdict:
    observation: NormalizedObservation
    reason: str
    required_speed_kmh: float
    displacement_km: float


def find_phantoms(observations: list[NormalizedObservation]) -> list[PhantomVerdict]:
    """Visits that cannot have been stationary.

    Two independent tests, because real data defeats either one alone:

    A. **Exit test** -- reaching the next fix after the visit would require impossible
       ground speed.
    B. **Containment test** -- a position fix recorded *during* the visit is implausibly
       far from where the visit claims the user was standing.

    Test B is what catches the reference case: Google anchored an 8 h 36 m visit at
    Rosslare Harbour while a breadcrumb 400 km out in the Atlantic was logged inside that
    very window. Test A missed it, because the breadcrumb precedes the visit's own end
    timestamp, leaving a non-positive exit interval.
    """
    ordered = sorted(observations, key=lambda o: o.t)
    verdicts: list[PhantomVerdict] = []

    for i, o in enumerate(ordered):
        if o.kind is not ObservationKind.VISIT or not o.has_position or o.end_t is None:
            continue

        verdict = _exit_test(ordered, i, o) or _containment_test(ordered, o)
        if verdict is not None:
            prev_mode = _preceding_transit_mode(ordered, i)
            if prev_mode:
                verdict.reason += f" (follows a {prev_mode} segment)"
            verdicts.append(verdict)

    return verdicts


def _exit_test(
    ordered: list[NormalizedObservation], i: int, o: NormalizedObservation
) -> PhantomVerdict | None:
    nxt = _next_positioned(ordered, i + 1, after=o.end_t)
    if nxt is None or o.end_t is None:
        return None

    gap_h = (nxt.t - o.end_t).total_seconds() / 3600.0
    if gap_h <= 0:
        return None

    dist_km = haversine_m(o.coord, nxt.coord) / 1000.0  # type: ignore[arg-type]
    speed = dist_km / gap_h
    if speed <= MAX_GROUND_SPEED_KMH:
        return None

    return PhantomVerdict(
        observation=o,
        reason=(
            f"reaching the next fix would require {speed:.0f} km/h over {dist_km:.0f} km; "
            "this period was travel, not a stay"
        ),
        required_speed_kmh=round(speed, 1),
        displacement_km=round(dist_km, 1),
    )


def _containment_test(
    ordered: list[NormalizedObservation], o: NormalizedObservation
) -> PhantomVerdict | None:
    """A fix inside the visit window, too far away to be the same place."""
    if o.end_t is None:
        return None
    worst_km = 0.0
    for other in ordered:
        if other is o or not other.has_position or other.kind is ObservationKind.MEDIA:
            continue
        if not (o.t <= other.t <= o.end_t):
            continue
        # How far could the user plausibly have strayed and returned by this moment?
        elapsed_h = max((other.t - o.t).total_seconds() / 3600.0, 0.01)
        dist_km = haversine_m(o.coord, other.coord) / 1000.0  # type: ignore[arg-type]
        if dist_km / elapsed_h > MAX_GROUND_SPEED_KMH:
            worst_km = max(worst_km, dist_km)

    if worst_km <= 0:
        return None

    hours = (o.end_t - o.t).total_seconds() / 3600.0
    return PhantomVerdict(
        observation=o,
        reason=(
            f"a position {worst_km:.0f} km away was recorded during this {hours:.1f} h "
            "'stay'; the user was in transit, not stationary"
        ),
        required_speed_kmh=round(worst_km / max(hours, 0.01), 1),
        displacement_km=round(worst_km, 1),
    )


def _next_positioned(
    ordered: list[NormalizedObservation], start: int, after: datetime | None = None
) -> NormalizedObservation | None:
    for o in ordered[start:]:
        if not o.has_position or o.kind is ObservationKind.MEDIA:
            continue
        if after is not None and o.t < after:
            continue
        return o
    return None


def _preceding_transit_mode(ordered: list[NormalizedObservation], i: int) -> str | None:
    for o in reversed(ordered[:i]):
        if o.kind is ObservationKind.MOVE:
            mode = o.hints.get("mode")
            return str(mode) if mode else "transit"
        if o.kind is ObservationKind.VISIT:
            return None
    return None
