# Heuristics and tunables

Every constant below lives in `backend/trippo/config/heuristics.py`. **No magic numbers elsewhere.**
If you change one, update the rationale here in the same commit and expect a golden snapshot diff.

## Clustering

| Constant | Value | Rationale |
|---|---|---|
| `CLUSTER_TIME_GAP_MIN` | 90 | Below this, a pause is part of the same visit. Chosen so a long lunch inside a city visit does not split it, while an afternoon drive does. |
| `CLUSTER_DIST_M` | 2000 | Urban visits drift by hundreds of metres across a district; 2 km separates "still here" from "somewhere else". |
| `STOP_RADIUS_M` | 120 | GPS drift while parked (especially in a vehicle, under trees) routinely reaches 100 m. |
| `STOP_MIN_MIN` | 10 | Shorter stationary periods are traffic, not stops. |

## Overnight detection

| Constant | Value | Rationale |
|---|---|---|
| `NIGHT_CORE_START` / `NIGHT_CORE_END` | 02:00 / 05:00 | The core hours a person is almost certainly asleep, in **local** time. Narrow on purpose: late dinners and early ferries must not qualify. |
| `OVERNIGHT_MIN_HOURS` | 5.0 | Alternative trigger for a long duskâ†’dawn stay that misses the core window. |

Runs **after** the plausibility gate. See pathology P1 in `ingestion.md`.

## Plausibility gate

| Constant | Value | Rationale |
|---|---|---|
| `MAX_GROUND_SPEED_KMH` | 130 | Motorway speed plus margin. A "stationary" visit that requires more than this to reach the next fix was not stationary â€” it was a crossing. Deliberately generous: false negatives are safer than deleting a real stop. |
| `PHANTOM_ABSORB_AFTER_TRANSIT` | `True` | A visit directly following a ferry/flight segment and preceding a distant fix is absorbed into that crossing. |

## Gap detection

| Constant | Value | Rationale |
|---|---|---|
| `GAP_MIN_HOURS` | 3.0 | Shorter holes are ordinary signal loss (tunnels, buildings, battery saver). |
| `GAP_MIN_KM` | 100 | A large displacement across a hole means real travel happened and must be accounted for. |

Either condition triggers an `unknown` event. Never auto-classified â€” see ADR-0007.

## Transport classification

| Constant | Value | Rationale |
|---|---|---|
| `SPEED_WALK_MAX_KMH` | 7 | Brisk walking upper bound. |
| `SPEED_BIKE_MAX_KMH` | 25 | Touring cycling upper bound. |
| `SPEED_DRIVE_MAX_KMH` | 130 | Above this on a long leg implies air travel. |
| `SPEED_FLIGHT_MIN_KMH` | 250 | Unambiguously airborne. |
| `FERRY_MIN_KM` | 20 | Below this a water crossing is a short hop, not a ferry leg worth its own event. |
| `TZ_CHANGE_IS_CROSSING` | `True` | A UTC-offset change between consecutive segments is a free, reliable international-crossing signal (P10). |

## Pruning â€” the Golden Rule

```python
keep = has_media or has_track or is_overnight or user_pinned
       or duration_min >= PRUNE_MIN_DURATION_MIN
       or distance_km  >= PRUNE_MIN_DISTANCE_KM
       or is_named_poi
```

| Constant | Value | Rationale |
|---|---|---|
| `PRUNE_MIN_DURATION_MIN` | 20 | A stop worth remembering lasts longer than a fuel stop. |
| `PRUNE_MIN_DISTANCE_KM` | 5 | Keeps real legs, drops micro-drives. |

Failing events are `suppressed` with a reason, **never deleted**.

## GPX

| Constant | Value | Rationale |
|---|---|---|
| `GPX_ABSORB_OVERLAP` | 0.5 | â‰¥50% temporal overlap with a timeline segment â‡’ the track absorbs it; otherwise the track becomes a standalone activity. |
| `GPX_SIMPLIFY_TOLERANCE_M` | 8 | Douglas-Peucker tolerance. ~3,200 points â†’ ~1,200 with no visible change at z14. |
| `GPX_SIMPLIFY_MAX_POINTS` | 1500 | Render budget per track. |
| `ELEVATION_THRESHOLD_M` | 4 | **Critical.** Without a threshold, GPS altitude noise reports +1,400 m on a flat ride. Every ascent/descent figure uses it, and the UI states it. |
| `ELEVATION_SMOOTH_WINDOW` | 5 | Applied **before** the threshold. A bare threshold still accumulates when noise amplitude exceeds it — ±2.5 m samples give 5 m swings, which a 4 m threshold happily counts (P15). Smoothing kills the oscillation; the threshold removes residual drift. |
| `TRACK_MERGE_GAP_MIN` | 15 | Below this, adjacent tracks are offered for merging (P9). Never merged silently. |

## Media matching

| Constant | Value | Rationale |
|---|---|---|
| `PHOTO_MATCH_DEFAULT_MIN` | 45 | Default half-window for "Find nearby photos". |
| `PHOTO_MATCH_MAX_MIN` | 120 | Upper bound offered in the UI. |
| `PHOTO_BURST_GAP_S` | 20 | Photos closer than this are one burst; only one becomes a hero candidate. |
| `PHOTO_SELECTION_MAX` | 8 | How many photographs represent an event by default. Enough to convey a day, few enough to scan in a timeline row. |
| `PHOTO_SELECTION_MIN_SPREAD` | 0.08 | Minimum separation between chosen photographs, as a fraction of the event's duration. Without it a summary of a six-hour walk is six shots of lunch. |
| `THUMB_PX` / `WEB_PX` | 256 / 1600 | Grid thumbnail and capsule/web derivative sizes. |

## Confidence priors

| Constant | Value | Rationale |
|---|---|---|
| `CONFIDENCE_TIMELINE_MOVE` | 0.6 | A provider-asserted move is usually right about *that* movement happened, less so about its mode. |
| `CONFIDENCE_MEDIA_CLUSTER` | 0.4 | A cluster inferred from photo timestamps alone is a suggestion, and the UI should show it as one. |
| `PLACE_CONFIDENCE_FROM_EXIF` | 0.8 | An event located from geotagged photos rests on a camera measurement. |
| `PLACE_CONFIDENCE_FROM_INFERRED` | 0.3 | An event located from photos that were themselves interpolated. Two inferences deep — treat gently, and let the geocoder widen its search radius. |

## Two independent plausibility tests

`draft/plausibility.py` runs both; either can condemn a visit.

- **Exit test** — reaching the next fix after the visit needs more than `MAX_GROUND_SPEED_KMH`.
- **Containment test** — a fix recorded *during* the visit is implausibly far from its anchor.

The containment test is not redundant: it is the one that catches the reference phantom, because
the mid-Atlantic breadcrumb precedes the visit's own end timestamp and leaves the exit test with a
non-positive interval (P14).
## Enrichment and ranking

See `docs/technical/enrichment.md` for the evidence behind each of these.

| Constant | Value | Rationale |
|---|---|---|
| `GEOCODE_RADIUS_MIN_M` / `MAX_M` | 80 / 400 | Scales with visit duration: a 15 min stop looks 80 m out, a 3 h visit 400 m. Widened further for weakly-placed events. |
| `GEOCODE_CACHE_PRECISION` | 4 | ~11 m grid. Finer would defeat caching; coarser would merge distinct POIs. |
| `FETCH_BATCH` / `OVERPASS_BATCH_SIZE` | 6 | Measured ceiling on the public Overpass instance for nodes-only queries. Larger returns 504. |
| `OVERPASS_TIMEOUT_S` | 60 | The server-side timeout declared in the query, matched by the client. |
| `NOMINATIM_MIN_INTERVAL_S` | 1.0 | Usage policy. Enforced in-process rather than trusted to callers. |
| `TRACK_SAMPLE_POINTS` | 6 | Points sampled along an activity track. Enough to find the summit and the lake; few enough to stay inside one batch. |
| `RANK_W_TYPE` | 1.0 | Tag affinity dominates: a campsite for an overnight, a peak for a hike. |
| `RANK_W_DISTANCE` | 0.7 | Strong but subordinate to type. Tolerance widens when the query point itself is uncertain. |
| `RANK_W_DURATION` | 0.3 | A three-hour stop is not a roadside memorial. |
| `RANK_W_NOTABLE` | 0.35 | A wikidata/heritage tag separates a destination from a plaque. Decisive in dense cities. |
| `RANK_GENERIC_PENALTY` | 0.4 | "Car Park", "Church", "Beach" — correct and useless. |
| `RANK_ADMIN_PENALTY` | 0.8 | "Centre Ward No. 5" is filing, not a place. Large because these are never right. |
| `RANK_REPEAT_PENALTY` | 0.5 | Stops the same monument winning four consecutive city-centre stops. |
| `RANK_REPEAT_WINDOW` | 4 | How many preceding events count as "nearby" for that penalty. |
| `RANK_MIN_CLEAR_MARGIN` | 0.15 | Below this the pick is **contested** — the hook for the E4 LLM tiebreak. |
| `PLACE_CONFIDENCE_CLEAR` / `CONTESTED` | 0.9 / 0.6 | Recorded on the place so the UI can show how sure Trippo is. |
## Track highlights and map geometry

| Constant | Value | Rationale |
|---|---|---|
| `PEAK_MAX_DIST_M` | 250 | A summit is something you stand on. Generous enough for GPS drift and for a tagged point sitting slightly off the cairn; on the reference data Slieve Binnian matched at 4 m and the neighbouring tops at 46–224 m. |
| `WATER_MAX_DIST_M` | 600 | A lake is something you walk beside, and the tagged centre of a lough can be far from its shore. |
| `ROUTE_SIMPLIFY_TOLERANCE_M` | 40 | Coarser than a track profile (8 m): at trip zoom nobody can resolve 8 m of detail, and the overview route is drawn for all 27 days at once. |
| `ROUTE_MAX_POINTS_PER_SEGMENT` | 300 | Render budget per leg. The reference trip assembles 103 segments in ~1,550 points. |
| `TRIP_BBOX_PAD_M` | 400 | Breathing room when fitting. A bbox fitted exactly puts the trailhead against the window edge. |