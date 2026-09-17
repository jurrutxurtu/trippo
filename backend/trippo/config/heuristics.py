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
THUMB_PX: Final = 256
WEB_PX: Final = 1_600

# --------------------------------------------------------------------------- enrichment
GEOCODE_RADIUS_MIN_M: Final = 80.0
GEOCODE_RADIUS_MAX_M: Final = 400.0
GEOCODE_CACHE_PRECISION: Final = 4
NOMINATIM_MIN_INTERVAL_S: Final = 1.0

# --------------------------------------------------------------------------- confidence
CONFIDENCE_TIMELINE_MOVE: Final = 0.6
CONFIDENCE_MEDIA_CLUSTER: Final = 0.4

# --------------------------------------------------------------------------- misc
EARTH_RADIUS_M: Final = 6_371_008.8
