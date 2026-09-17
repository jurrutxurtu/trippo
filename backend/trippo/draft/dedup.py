"""Deduplicate overlapping visit observations. Pathology P4.

Google's on-device export nests visits by `hierarchyLevel`: a venue inside a district
inside a city can all be reported for the same time range. The reference export contained
`10-15 07:20 -> 08:45` twice, at different coordinates.

Keep the most specific level; retain the rest as provenance so nothing is lost.
"""

from __future__ import annotations

from trippo.observe.models import NormalizedObservation, ObservationKind


def dedup_visits(
    observations: list[NormalizedObservation],
) -> tuple[list[NormalizedObservation], list[tuple[NormalizedObservation, str]]]:
    """Return (kept, [(dropped, reason)])."""
    visits = [o for o in observations if o.kind is ObservationKind.VISIT]
    others = [o for o in observations if o.kind is not ObservationKind.VISIT]
    if not visits:
        return observations, []

    visits.sort(key=lambda o: (o.t, -(o.end_t.timestamp() if o.end_t else 0)))
    kept: list[NormalizedObservation] = []
    dropped: list[tuple[NormalizedObservation, str]] = []

    for v in visits:
        clash = next((k for k in kept if _same_window(k, v)), None)
        if clash is None:
            kept.append(v)
            continue
        if _specificity(v) > _specificity(clash):
            kept[kept.index(clash)] = v
            dropped.append((clash, f"less specific duplicate of {v.ref}"))
        else:
            dropped.append((v, f"duplicate of {clash.ref} at the same time range"))

    merged = sorted(kept + others, key=lambda o: o.t)
    return merged, dropped


def _same_window(a: NormalizedObservation, b: NormalizedObservation) -> bool:
    """Near-identical time ranges. Deliberately strict: only true duplicates, not nesting
    in time (a short visit inside a long one is two real events)."""
    if a.end_t is None or b.end_t is None:
        return False
    return abs((a.t - b.t).total_seconds()) < 60 and abs((a.end_t - b.end_t).total_seconds()) < 60


def _specificity(o: NormalizedObservation) -> tuple[int, float]:
    """Higher is better. A deeper hierarchy level is a more specific place."""
    level = o.hints.get("hierarchy_level", 0)
    level_i = int(level) if isinstance(level, (int, float)) else 0
    prob = o.hints.get("probability", 0.0)
    prob_f = float(prob) if isinstance(prob, (int, float)) else 0.0
    named = 1 if o.hints.get("name") else 0
    return (level_i + named, prob_f)
