"""Candidate ranking -- deterministic, and aware of what kind of event it is naming.

The hard part of geocoding a trip is not fetching candidates, it is choosing between
them. Glendalough returns 15 named features; distance alone picks the wrong one.

    "Glendalough"                tourism=attraction   <- usually right
    "Glendalough Hotel"          tourism=hotel        <- right only if you slept there
    "Saint Kevin's Church"       historic=church      <- right for a 40 min stop
    "Lower Lake"                 natural=water        <- right if the photos are of water

So the scorer is given the event's type, duration and media count, and weights OSM tag
classes accordingly. An overnight prefers a campsite; a hike prefers a summit; a visit
prefers a monument.

Nothing here calls the network, so it is cheap to test exhaustively.
"""

from __future__ import annotations

from dataclasses import dataclass

from trippo.config.heuristics import (
    RANK_ADMIN_PENALTY,
    RANK_GENERIC_PENALTY,
    RANK_MIN_CLEAR_MARGIN,
    RANK_REPEAT_PENALTY,
    RANK_W_DISTANCE,
    RANK_W_DURATION,
    RANK_W_NOTABLE,
    RANK_W_TYPE,
)
from trippo.domain.models import EventType
from trippo.ports.geocoder import PlaceCandidate

#: Per-event-type affinity for OSM tag classes. Higher is more appropriate.
#: Absent entries score 0; negatives actively discourage.
_AFFINITY: dict[EventType, dict[str, float]] = {
    EventType.OVERNIGHT: {
        "tourism=camp_site": 1.0,
        "tourism=caravan_site": 1.0,
        "tourism=hotel": 0.95,
        "tourism=guest_house": 0.95,
        "tourism=hostel": 0.9,
        "tourism=motel": 0.9,
        "tourism=apartment": 0.8,
        "amenity=parking": 0.35,  # campervan bivouac -- plausible, not flattering
        "place": 0.5,
        "natural": 0.2,
        "historic": 0.05,
    },
    EventType.VISIT: {
        "tourism=attraction": 1.0,
        "tourism=museum": 1.0,
        "historic": 0.95,
        "tourism=viewpoint": 0.8,
        "amenity=restaurant": 0.8,
        "amenity=cafe": 0.7,
        "amenity=pub": 0.7,
        "natural": 0.6,
        "leisure": 0.55,
        "place": 0.5,
        "tourism=hotel": 0.3,
        "amenity=parking": 0.1,
        # An interpretation board is not a destination. Titanic Quarter alone returns a
        # dozen of them, and unchecked they out-compete the thing they describe.
        "tourism=information": -0.3,
        "tourism=artwork": 0.15,
        "historic=memorial": 0.35,
        "historic=wayside_cross": 0.2,
    },
    EventType.STOP: {
        "tourism=viewpoint": 1.0,
        "natural=beach": 0.95,
        "natural=peak": 0.9,
        "natural": 0.8,
        "tourism=picnic_site": 0.8,
        "amenity=parking": 0.6,  # a layby genuinely is the place
        "place": 0.5,
        "historic": 0.5,
    },
    EventType.HIKE: {
        "natural=peak": 1.0,
        "natural=saddle": 0.85,
        "natural=water": 0.7,
        "natural": 0.7,
        "leisure=nature_reserve": 0.7,
        "tourism=viewpoint": 0.6,
        "place": 0.4,
        "amenity=parking": 0.3,  # the trailhead, when nothing better exists
        "tourism=hotel": -0.5,
    },
    EventType.FERRY: {
        "amenity=ferry_terminal": 1.0,
        "place": 0.4,
    },
}
_AFFINITY[EventType.WALK] = _AFFINITY[EventType.VISIT]
_AFFINITY[EventType.BIKE] = _AFFINITY[EventType.HIKE]

#: Tag classes that are never a "place" for a travel journal, whatever the distance.
#: Roads are the original sin here: plain reverse geocoding answers "R757" for
#: Glendalough, and that answer must not survive into the itinerary.
REJECT_KEYS = frozenset({"highway", "barrier", "boundary", "landuse", "railway", "power"})

#: `place=*` is a mixed bag: a village is a real answer, a "locality" or an electoral
#: ward is administrative noise.
_PLACE_QUALITY: dict[str, float] = {
    "city": 0.7,
    "town": 0.7,
    "village": 0.7,
    "hamlet": 0.65,
    "suburb": 0.45,
    "neighbourhood": 0.4,
    "island": 0.6,
    "locality": 0.2,
    "quarter": 0.25,
}

#: Names that are technically correct and practically useless.
_GENERIC = {
    "car park",
    "parking",
    "car parking",
    "church",
    "chapel",
    "cemetery",
    "graveyard",
    "toilets",
    "bus stop",
    "picnic area",
    "viewpoint",
    "beach",
    "harbour",
    "pier",
    "the green",
}

#: Words that mark an administrative unit rather than a place you visit.
_ADMIN_WORDS = (
    "ward",
    "electoral",
    "municipal district",
    "townland",
    " ed ",
    "constituency",
)

#: How long a visit "should" last at a given class of place, in minutes.
_TYPICAL_MINUTES: dict[str, tuple[float, float]] = {
    "tourism=museum": (45, 240),
    "tourism=attraction": (20, 180),
    "amenity=restaurant": (40, 150),
    "amenity=cafe": (15, 90),
    "amenity=pub": (30, 240),
    "tourism=viewpoint": (5, 45),
    "natural=peak": (5, 60),
    "amenity=parking": (2, 60),
    "tourism=camp_site": (480, 1000),
    "tourism=hotel": (420, 1000),
    # Small roadside features. A three-hour "visit" to a memorial means the memorial is
    # not what the stop was about.
    "historic=memorial": (2, 40),
    "historic=monument": (5, 60),
    "historic=wayside_cross": (2, 20),
    "tourism=artwork": (2, 30),
    "tourism=information": (2, 20),
}


@dataclass(slots=True)
class RankedCandidate:
    candidate: PlaceCandidate
    score: float
    reasons: list[str]


@dataclass(slots=True)
class RankContext:
    event_type: EventType
    duration_s: float = 0.0
    media_count: int = 0
    #: Confidence in the query point itself. A weakly-placed event (one located from
    #: interpolated photos) must not be penalised for candidates being far away.
    position_confidence: float = 1.0
    search_radius_m: float = 300.0
    #: Names already given to nearby events. In a dense city centre the same monument
    #: otherwise wins four consecutive stops, which tells the reader nothing and looks
    #: broken. Repetition is strong evidence of a poor pick.
    used_names: frozenset[str] = frozenset()


def rank(candidates: list[PlaceCandidate], ctx: RankContext) -> list[RankedCandidate]:
    usable = [c for c in candidates if c.tag_key not in REJECT_KEYS]
    scored = [_score(c, ctx) for c in usable]
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored


def best(
    candidates: list[PlaceCandidate], ctx: RankContext
) -> tuple[RankedCandidate | None, bool]:
    """Return (winner, is_clear).

    `is_clear` is False when the top two are close enough that an LLM tiebreak would add
    value (E4). Until then a close call is simply taken with lower confidence.
    """
    ranked = rank(candidates, ctx)
    if not ranked:
        return None, False
    if len(ranked) == 1:
        return ranked[0], True
    margin = ranked[0].score - ranked[1].score
    return ranked[0], margin >= RANK_MIN_CLEAR_MARGIN


def _score(c: PlaceCandidate, ctx: RankContext) -> RankedCandidate:
    reasons: list[str] = []

    # --- tag affinity to this kind of event
    table = _AFFINITY.get(ctx.event_type, _AFFINITY[EventType.VISIT])
    affinity = table.get(c.kind or "", table.get(c.tag_key, 0.0))
    if c.tag_key == "place":
        # Replace the blanket `place` affinity with the specific subtype: a village is a
        # real answer, a "locality" or an electoral ward is administrative noise. Taking
        # a min() here would cap the good subtypes at the generic value and let a nearby
        # locality beat a slightly further village.
        affinity = _PLACE_QUALITY.get(c.tag_value, min(affinity, 0.25))
    if affinity:
        reasons.append(f"{c.kind or c.tag_key} suits a {ctx.event_type.value} ({affinity:+.2f})")
    score = RANK_W_TYPE * affinity

    # --- proximity, forgiving when the query point itself is uncertain
    if c.distance_m is not None and ctx.search_radius_m > 0:
        tolerance = ctx.search_radius_m * (2.0 - ctx.position_confidence)
        proximity = max(0.0, 1.0 - (c.distance_m / tolerance))
        score += RANK_W_DISTANCE * proximity
        reasons.append(f"{c.distance_m:.0f} m away ({proximity:+.2f})")

    # --- does the stay length fit this class of place?
    window = _TYPICAL_MINUTES.get(c.kind or "")
    if window and ctx.duration_s > 0:
        minutes = ctx.duration_s / 60.0
        lo, hi = window
        fit = 1.0 if lo <= minutes <= hi else -0.5
        score += RANK_W_DURATION * fit
        reasons.append(f"{minutes:.0f} min {'fits' if fit > 0 else 'does not fit'} {c.kind}")

    # --- notability: a wikidata or heritage tag separates a real destination from a
    # plaque. Free, already in the data, and a strong discriminator in dense cities.
    if c.notable:
        score += RANK_W_NOTABLE
        reasons.append("notable (wikidata/heritage)")

    # --- penalise names that carry no information
    lowered = c.name.strip().lower()
    if lowered in _GENERIC:
        score -= RANK_GENERIC_PENALTY
        reasons.append("generic name")
    if any(w in f" {lowered} " for w in _ADMIN_WORDS):
        score -= RANK_ADMIN_PENALTY
        reasons.append("administrative unit, not a destination")
    if lowered in ctx.used_names:
        score -= RANK_REPEAT_PENALTY
        reasons.append("already used by a neighbouring event")

    return RankedCandidate(candidate=c, score=round(score, 4), reasons=reasons)
