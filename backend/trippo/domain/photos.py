"""Choosing which photographs represent an event.

A three-hour hike can carry 87 photographs. Showing all of them in a timeline row is
useless, and picking the first six is worse -- they are usually six near-identical frames
from the same burst at the trailhead.

So each event gets a **selection**: a small, well-spread set that represents it. The rest
remain owned by the event and one click away. Nothing is hidden and nothing is lost -- the
Golden Rule applies to selection exactly as it does to pruning.

Selection is a suggestion. `Event.user_selected_media` marks it as the user's own choice,
after which it is never recomputed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from trippo.config.heuristics import (
    PHOTO_BURST_GAP_S,
    PHOTO_SELECTION_MAX,
    PHOTO_SELECTION_MIN_SPREAD,
)
from trippo.domain.models import LocationSource, MediaAsset, MediaKind, MediaVariant

#: Deliberate captures. A panorama or a night shot took effort, so it probably mattered.
_VARIANT_BONUS: dict[MediaVariant, float] = {
    MediaVariant.PANO: 0.35,
    MediaVariant.NIGHT: 0.25,
    MediaVariant.MOTION_PHOTO: 0.05,
}


@dataclass(slots=True)
class ScoredMedia:
    media: MediaAsset
    score: float
    reasons: list[str]


def score(m: MediaAsset) -> ScoredMedia:
    """How representative is this single item, ignoring its neighbours?"""
    s = 0.0
    why: list[str] = []

    if m.variant and (bonus := _VARIANT_BONUS.get(m.variant)):
        s += bonus
        why.append(m.variant.value.lower())

    # A measured position is worth more than an interpolated one: it can be placed on the
    # map exactly, which is the whole point of a photo pin.
    if m.location_source is LocationSource.EXIF:
        s += 0.2
        why.append("gps")
    elif m.location_source is LocationSource.INFERRED:
        s += 0.05

    if m.width and m.height:
        pixels = m.width * m.height
        if pixels >= 8_000_000:
            s += 0.1
        ratio = max(m.width, m.height) / max(min(m.width, m.height), 1)
        if ratio > 2.2:  # a panorama even without the filename tag
            s += 0.15
            why.append("wide")

    # Videos are excluded from export in this version, so they make poor representatives.
    if m.kind is MediaKind.VIDEO:
        s -= 0.5

    return ScoredMedia(media=m, score=round(s, 3), reasons=why)


def bursts(media: list[MediaAsset]) -> list[list[MediaAsset]]:
    """Group consecutive shots taken within `PHOTO_BURST_GAP_S` of each other.

    Six frames of the same waterfall are one photograph as far as a summary is concerned.
    """
    # Sort on the timestamp alone. Tupling the model in would make Python fall through to
    # comparing MediaAsset when two shots share a timestamp, which raises.
    pairs: list[tuple[datetime, MediaAsset]] = sorted(
        ((m.captured_at, m) for m in media if m.captured_at is not None),
        key=lambda pair: pair[0],
    )
    if not pairs:
        return []

    groups: list[list[MediaAsset]] = [[pairs[0][1]]]
    for (prev_t, _p), (cur_t, cur) in pairwise(pairs):
        if (cur_t - prev_t).total_seconds() <= PHOTO_BURST_GAP_S:
            groups[-1].append(cur)
        else:
            groups.append([cur])
    return groups


def select(
    media: list[MediaAsset], limit: int = PHOTO_SELECTION_MAX
) -> list[str]:
    """Pick up to `limit` representative photographs, spread across the event.

    Three passes, in order:

    1. **Collapse bursts** -- keep the best frame from each, so a single moment cannot
       occupy the whole selection.
    2. **Spread across time** -- greedily take the highest-scoring candidate that is at
       least `PHOTO_SELECTION_MIN_SPREAD` of the event's duration away from everything
       already chosen. A summary of a six-hour walk should not be six shots of lunch.
    3. **Backfill** -- if the spread rule leaves fewer than `limit`, relax it and take the
       next best, so a short event still gets a full set.
    """
    usable: list[tuple[MediaAsset, datetime]] = [
        (m, m.captured_at)
        for m in media
        if m.captured_at is not None and m.kind is MediaKind.PHOTO
    ]
    if not usable:
        return []
    if len(usable) <= limit:
        return [m.id for m, _t in sorted(usable, key=lambda pair: pair[1])]

    # Keyed by id: Pydantic models are not hashable.
    at: dict[str, datetime] = {m.id: t for m, t in usable}
    best_of_burst = [
        max(group, key=lambda m: score(m).score)
        for group in bursts([m for m, _t in usable])
    ]
    ranked = sorted(best_of_burst, key=lambda m: score(m).score, reverse=True)

    times = [t for _m, t in usable]
    span = max((max(times) - min(times)).total_seconds(), 1.0)
    min_gap = span * PHOTO_SELECTION_MIN_SPREAD

    chosen: list[MediaAsset] = []
    for m in ranked:
        if len(chosen) >= limit:
            break
        if all(
            abs((at[m.id] - at[c.id]).total_seconds()) >= min_gap for c in chosen
        ):
            chosen.append(m)

    if len(chosen) < limit:
        taken = {m.id for m in chosen}
        for m in ranked:
            if len(chosen) >= limit:
                break
            if m.id not in taken:
                chosen.append(m)

    chosen.sort(key=lambda m: at[m.id])
    return [m.id for m in chosen]
