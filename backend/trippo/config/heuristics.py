"""Every tunable heuristic constant in Trippo.

Rationale for each value is documented in ``docs/technical/heuristics-tunables.md``.
Changing a value here will produce a golden snapshot diff -- that is intentional.

NO MAGIC NUMBERS ELSEWHERE. See AGENTS.md section 3.5.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- clustering
CLUSTER_TIME_GAP_MIN: Final = 90
CLUSTER_DIST_M: Final = 2_000.0
STOP_RADIUS_M: Final = 120.0
STOP_MIN_MIN: Final = 10

# --------------------------------------------------------------------------- overnight
NIGHT_CORE_START_H: Final = 2
NIGHT_CORE_END_H: Final = 5
OVERNIGHT_MIN_HOURS: Final = 5.0

# --------------------------------------------------------------------------- plausibility (P1)
MAX_GROUND_SPEED_KMH: Final = 130.0
PHANTOM_ABSORB_AFTER_TRANSIT: Final = True

# --------------------------------------------------------------------------- gaps (P3, ADR-0007)
GAP_MIN_HOURS: Final = 3.0
GAP_MIN_KM: Final = 25.0
GAP_STATIONARY_KM: Final = 2.0
GAP_ISOLATED_FIX_HOURS: Final = 2.5

# --------------------------------------------------------------------------- transport
SPEED_WALK_MAX_KMH: Final = 7.0
SPEED_BIKE_MAX_KMH: Final = 25.0
SPEED_DRIVE_MAX_KMH: Final = 130.0
SPEED_FLIGHT_MIN_KMH: Final = 250.0
FERRY_MIN_KM: Final = 20.0
TZ_CHANGE_IS_CROSSING: Final = True

# --------------------------------------------------------------------------- pruning (Golden Rule)
PRUNE_MIN_DURATION_MIN: Final = 20
PRUNE_MIN_DISTANCE_KM: Final = 5.0

# --------------------------------------------------------------------------- gpx (ADR-0004)
GPX_ABSORB_OVERLAP: Final = 0.5
GPX_SIMPLIFY_TOLERANCE_M: Final = 8.0
GPX_SIMPLIFY_MAX_POINTS: Final = 1_500
ELEVATION_THRESHOLD_M: Final = 4.0
ELEVATION_SMOOTH_WINDOW: Final = 5
TRACK_MERGE_GAP_MIN: Final = 15
MOVING_SPEED_MIN_KMH: Final = 0.8

# --------------------------------------------------------------------------- media
PHOTO_MATCH_DEFAULT_MIN: Final = 45
PHOTO_MATCH_MAX_MIN: Final = 120
PHOTO_BURST_GAP_S: Final = 20
#: How many photographs represent an event by default.
PHOTO_SELECTION_MAX: Final = 8
#: Minimum separation between chosen photographs, as a fraction of the event's duration.
#: Stops a summary of a six-hour walk being six shots of lunch.
PHOTO_SELECTION_MIN_SPREAD: Final = 0.08
THUMB_PX: Final = 256
WEB_PX: Final = 1_600

# --------------------------------------------------------------------------- enrichment
GEOCODE_RADIUS_MIN_M: Final = 80.0
GEOCODE_RADIUS_MAX_M: Final = 400.0
GEOCODE_CACHE_PRECISION: Final = 4

NOMINATIM_URL: Final = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_MIN_INTERVAL_S: Final = 1.0

#: Mirrors, fastest first. Measured 2026-09-18 on an identical query:
#:   kumi.systems    4.7 s
#:   private.coffee  7.8 s
#:   overpass-api.de 22.2 s   <- the reference implementation, and by far the slowest
#: Order matters more than it looks: the first mirror is tried for every batch, so putting
#: the 22-second one first made a Morocco import crawl.
OVERPASS_ENDPOINTS: Final = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
OVERPASS_BATCH_SIZE: Final = 6
#: Client-side budget per request. The server-side directive is separate and larger; this
#: bounds how long a single stalled mirror can block an import. Two mirrors at 60 s each
#: meant a two-minute silence, which is what broke the progress stream.
OVERPASS_CLIENT_TIMEOUT_S: Final = 25
#: Query points sent to a provider per request during enrichment.
FETCH_BATCH: Final = 6
OVERPASS_TIMEOUT_S: Final = 60
OVERPASS_MAX_FEATURES: Final = 200

#: Points sampled along an activity track when looking for summits and lakes.
TRACK_SAMPLE_POINTS: Final = 6

# --------------------------------------------------------------------------- track highlights
#: A summit is something you stand on; GPS drift allows for a few tens of metres.
PEAK_MAX_DIST_M: Final = 250.0
#: A lake is something you walk beside, and its tagged centre may be far from the shore.
WATER_MAX_DIST_M: Final = 600.0

# --------------------------------------------------------------------------- map geometry
#: Douglas-Peucker tolerance for the overview route. Coarser than a track profile: at trip
#: zoom nobody can see 8 m of detail.
ROUTE_SIMPLIFY_TOLERANCE_M: Final = 40.0
ROUTE_MAX_POINTS_PER_SEGMENT: Final = 300
#: Breathing room when fitting the map to a bbox, so nothing sits against the window edge.
TRIP_BBOX_PAD_M: Final = 400.0

# --------------------------------------------------------------------------- ranking
RANK_W_TYPE: Final = 1.0
RANK_W_DISTANCE: Final = 0.7
RANK_W_DURATION: Final = 0.3
RANK_GENERIC_PENALTY: Final = 0.4
RANK_ADMIN_PENALTY: Final = 0.8
RANK_W_NOTABLE: Final = 0.35
RANK_REPEAT_PENALTY: Final = 0.5
#: How many neighbouring events count as "nearby" for the repetition penalty.
RANK_REPEAT_WINDOW: Final = 4
RANK_MIN_CLEAR_MARGIN: Final = 0.15

PLACE_CONFIDENCE_CLEAR: Final = 0.9
PLACE_CONFIDENCE_CONTESTED: Final = 0.6

# --------------------------------------------------------------------------- suggestions
#: A run of stops closer together than this in time is probably one visit.
GROUP_MAX_GAP_MIN: Final = 40
#: ...and closer than this in space. A city block, not a district: grouping too widely
#: turns a day of real places into one vague blob.
GROUP_MAX_SPAN_M: Final = 700.0
#: Below this it is not a group, it is two stops.
GROUP_MIN_EVENTS: Final = 3
#: End to end. Without it, a nearby overnight drags a group across 31 hours and the
#: result is not a visit to anywhere -- it is a day and a half of being in a town.
GROUP_MAX_TOTAL_SPAN_MIN: Final = 300
#: A stop shorter than this, with no photographs, was passing through beyond reasonable
#: doubt. Proposed even with no model. Never applied to anything with a photograph.
PASSING_MAX_MINUTES: Final = 12
#: With a model available, widen the net to here and let it judge. The Golden Rule already
#: suppressed everything under PRUNE_MIN_DURATION_MIN unless it had a name, so the events
#: left in this band are precisely the ones geocoding lent a significance they may not
#: deserve -- a named junction is still a junction.
PASSING_REVIEW_MAX_MINUTES: Final = 35

# --------------------------------------------------------------------------- confidence
CONFIDENCE_TIMELINE_MOVE: Final = 0.6
CONFIDENCE_MEDIA_CLUSTER: Final = 0.4
PLACE_CONFIDENCE_FROM_EXIF: Final = 0.8
PLACE_CONFIDENCE_FROM_INFERRED: Final = 0.3

# --------------------------------------------------------------------------- misc
EARTH_RADIUS_M: Final = 6_371_008.8
