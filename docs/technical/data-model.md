<!-- GENERATED FILE -- DO NOT EDIT BY HAND.
     Regenerate with `just gen-docs`. Source of truth: backend/trippo/domain/models.py -->

# Data model (generated)

Capsule schema version **0.5.0**.

This document is generated from the Pydantic models in `backend/trippo/domain/models.py`.
For the prose contract -- layout on disk, portability rules, invariants and migrations --
see [`capsule-format.md`](capsule-format.md).


## Entities

| Model | Fields | Description |
| --- | --- | --- |
| `AbsorbedRef` | 4 | A segment this event swallowed -- a phantom visit (P1) or a duplicate (P4). |
| `ActivityDetail` | 4 |  |
| `ActivityStats` | 10 | Telemetry. Lives ONLY on track-bearing activity events -- never on a trip. |
| `BBox` | 4 | Geographic bounds, for fitting a map. (min_lat, min_lon, max_lat, max_lon). |
| `DateRange` | 2 |  |
| `Day` | 13 |  |
| `DayCoverage` | 4 |  |
| `DayStats` | 7 | Per-day figures for the timeline heading. |
| `Event` | 22 |  |
| `FerryDetail` | 7 |  |
| `FlightDetail` | 6 |  |
| `FlightSegment` | 5 |  |
| `Geometry` | 4 |  |
| `IngestionReport` | 11 | Surfaced to the user BEFORE the draft. Degradations are never silent. |
| `MediaAsset` | 22 |  |
| `Place` | 9 |  |
| `PlaceDetail` | 4 |  |
| `Provenance` | 5 |  |
| `RouteSegment` | 5 | One drawable leg of the overall route. |
| `Source` | 7 |  |
| `SourceRef` | 2 |  |
| `TrackHighlight` | 8 | A named feature the route passed: a summit, a pass, a lake. |
| `TrackMeta` | 13 |  |
| `TrackStats` | 10 |  |
| `TransitDetail` | 5 |  |
| `TripStats` | 15 | Trip-level statistics. NO ELEVATION -- telemetry belongs to activities. |
| `UnknownDetail` | 6 | An unaccounted gap. States facts only -- never a classification. ADR-0007. |

## Enumerations

- **EventStatus**: `active`, `suppressed`
- **EventType**: `drive`, `stop`, `visit`, `overnight`, `hike`, `walk`, `bike`, `flight`, `ferry`, `unknown`
- **GeometryReliability**: `measured`, `sparse`, `assumed`
- **LocationSource**: `exif`, `inferred`, `user`, `none`
- **MediaKind**: `photo`, `video`
- **MediaVariant**: `MP`, `NIGHT`, `PANO`
- **PlaceSource**: `osm`, `nominatim`, `photon`, `google`, `gpx`, `user`, `coords`
- **SourceKind**: `timeline`, `gpx`, `media`, `manual`
- **TimeSource**: `exif`, `exif_no_offset`, `filename`, `mtime`, `user`
- **TripStatus**: `draft`, `curated`

## Fields

### AbsorbedRef

A segment this event swallowed -- a phantom visit (P1) or a duplicate (P4).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `ref` | `string` | yes |  |
| `reason` | `string` | yes |  |
| `start` | `string` \| `null` | no |  |
| `end` | `string` \| `null` | no |  |

### ActivityDetail

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | no |  |
| `stats` | `ActivityStats` | no |  |
| `activity_type_hint` | `string` \| `null` | no |  |
| `highlights` | array of `TrackHighlight` | no |  |

### ActivityStats

Telemetry. Lives ONLY on track-bearing activity events -- never on a trip.

Ascent and descent use ELEVATION_THRESHOLD_M; without it GPS noise reports
+1,400 m on a flat ride.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `distance_m` | `number` | no |  |
| `ascent_m` | `number` | no |  |
| `descent_m` | `number` | no |  |
| `max_ele_m` | `number` \| `null` | no |  |
| `min_ele_m` | `number` \| `null` | no |  |
| `moving_time_s` | `number` | no |  |
| `elapsed_time_s` | `number` | no |  |
| `avg_hr` | `number` \| `null` | no |  |
| `max_hr` | `number` \| `null` | no |  |
| `elevation_threshold_m` | `number` | no |  |

### BBox

Geographic bounds, for fitting a map. (min_lat, min_lon, max_lat, max_lon).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `min_lat` | `number` | yes |  |
| `min_lon` | `number` | yes |  |
| `max_lat` | `number` | yes |  |
| `max_lon` | `number` | yes |  |

### DateRange

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `start` | `string` | yes |  |
| `end` | `string` | yes |  |

### Day

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `string` | yes |  |
| `index` | `integer` | yes |  |
| `date` | `string` | yes |  |
| `timezone` | `string` | no |  |
| `excluded` | `boolean` | no |  |
| `title` | `string` \| `null` | no |  |
| `subtitle` | `string` \| `null` | no |  |
| `user_title` | `boolean` | no |  |
| `note` | `string` \| `null` | no |  |
| `event_ids` | array of `string` | no |  |
| `spanning_event_ids` | array of `string` | no |  |
| `bbox` | `BBox` \| `null` | no |  |
| `stats` | `DayStats` | no |  |

### DayCoverage

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `date` | `string` | yes |  |
| `timeline_records` | `integer` | no |  |
| `media_count` | `integer` | no |  |
| `track_count` | `integer` | no |  |

### DayStats

Per-day figures for the timeline heading.

Elevation appears here only when the day actually contained an activity, keeping the
scoping rule intact: a city day shows distance and photographs, nothing about climbing.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `event_count` | `integer` | no |  |
| `photo_count` | `integer` | no |  |
| `video_count` | `integer` | no |  |
| `distance_by_mode_m` | `object` | no |  |
| `ascent_m` | `number` \| `null` | no |  |
| `has_activity` | `boolean` | no |  |
| `unaccounted_hours` | `number` | no |  |

### Event

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `string` | yes |  |
| `day_id` | `string` \| `null` | no |  |
| `type` | `EventType` | yes |  |
| `status` | `EventStatus` | no |  |
| `suppress_reason` | `string` \| `null` | no |  |
| `start` | `string` | yes |  |
| `end` | `string` | yes |  |
| `timezone` | `string` | no |  |
| `utc_offset_minutes` | `integer` \| `null` | no |  |
| `continues_to_next_day` | `boolean` | no |  |
| `place` | `Place` \| `null` | no |  |
| `geometry` | `Geometry` \| `null` | no |  |
| `media_ids` | array of `string` | no |  |
| `selected_media_ids` | array of `string` | no |  |
| `user_selected_media` | `boolean` | no |  |
| `track_ids` | array of `string` | no |  |
| `provenance` | `Provenance` | no |  |
| `user_edited` | `boolean` | no |  |
| `user_pinned` | `boolean` | no |  |
| `title` | `string` \| `null` | no |  |
| `note` | `string` \| `null` | no |  |
| `detail` | `any` | yes |  |

### FerryDetail

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | no |  |
| `distance_m` | `number` | no |  |
| `duration_s` | `number` | no |  |
| `geometry_reliability` | `GeometryReliability` | no |  |
| `operator` | `string` \| `null` | no |  |
| `from_port` | `string` \| `null` | no |  |
| `to_port` | `string` \| `null` | no |  |

### FlightDetail

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | no |  |
| `distance_m` | `number` | no |  |
| `duration_s` | `number` | no |  |
| `geometry_reliability` | `GeometryReliability` | no |  |
| `segments` | array of `FlightSegment` | no |  |
| `layovers` | array of `string` | no |  |

### FlightSegment

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `from_iata` | `string` \| `null` | no |  |
| `to_iata` | `string` \| `null` | no |  |
| `flight_no` | `string` \| `null` | no |  |
| `dep` | `string` \| `null` | no |  |
| `arr` | `string` \| `null` | no |  |

### Geometry

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | yes |  |
| `track_id` | `string` \| `null` | no |  |
| `polyline` | array of array of `any` \| `null` | no |  |
| `reliability` | `GeometryReliability` | no |  |

### IngestionReport

Surfaced to the user BEFORE the draft. Degradations are never silent.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `source_id` | `string` | yes |  |
| `kind` | `SourceKind` | yes |  |
| `detected_format` | `string` | no |  |
| `confidence` | `number` | no |  |
| `files_seen` | `integer` | no |  |
| `files_parsed` | `integer` | no |  |
| `records_total` | `integer` | no |  |
| `records_in_window` | `integer` | no |  |
| `skipped` | array of `object` | no |  |
| `degradations` | array of `string` | no |  |
| `notes` | array of `string` | no |  |

### MediaAsset

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `string` | yes |  |
| `hash` | `string` | yes |  |
| `kind` | `MediaKind` | yes |  |
| `filename` | `string` | yes |  |
| `normalized_filename` | `string` | yes |  |
| `captured_at` | `string` \| `null` | no |  |
| `timezone` | `string` | no |  |
| `time_source` | `TimeSource` | no |  |
| `lat` | `number` \| `null` | no |  |
| `lon` | `number` \| `null` | no |  |
| `location_source` | `LocationSource` | no |  |
| `width` | `integer` \| `null` | no |  |
| `height` | `integer` \| `null` | no |  |
| `orientation` | `integer` \| `null` | no |  |
| `device_id` | `string` \| `null` | no |  |
| `variant` | `MediaVariant` \| `null` | no |  |
| `duration_s` | `number` \| `null` | no |  |
| `thumb_ref` | `string` \| `null` | no |  |
| `web_ref` | `string` \| `null` | no |  |
| `poster_ref` | `string` \| `null` | no |  |
| `excluded_from_export` | `boolean` | no |  |
| `size_bytes` | `integer` | no |  |

### Place

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | `string` | yes |  |
| `lat` | `number` \| `null` | no |  |
| `lon` | `number` \| `null` | no |  |
| `address` | `string` \| `null` | no |  |
| `google_place_id` | `string` \| `null` | no |  |
| `osm_id` | `string` \| `null` | no |  |
| `category` | `string` \| `null` | no |  |
| `source` | `PlaceSource` | no |  |
| `confidence` | `number` | no |  |

### PlaceDetail

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | no |  |
| `duration_s` | `number` | no |  |
| `category` | `string` \| `null` | no |  |
| `accommodation` | `string` \| `null` | no |  |

### Provenance

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `derived_from` | array of `SourceRef` | no |  |
| `rules` | array of `string` | no |  |
| `confidence` | `number` | no |  |
| `absorbed` | array of `AbsorbedRef` | no |  |
| `superseded_by` | `string` \| `null` | no |  |

### RouteSegment

One drawable leg of the overall route.

Segmented rather than a single polyline so the map can style each leg by what it was:
a measured GPX trail is a solid line, a ferry reconstructed from two breadcrumbs is
dashed and labelled approximate, and an unaccounted gap is dashed with no claim at all.
Merging them would assert a confidence the data does not support (ADR-0007).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `event_id` | `string` | yes |  |
| `day_index` | `integer` | yes |  |
| `kind` | `string` | yes |  |
| `reliability` | `GeometryReliability` | no |  |
| `points` | array of array of `any` | no |  |

### Source

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `string` | yes |  |
| `kind` | `SourceKind` | yes |  |
| `detected_format` | `string` | no |  |
| `file_hash` | `string` \| `null` | no |  |
| `display_name` | `string` | no |  |
| `imported_at` | `string` | yes |  |
| `report` | `IngestionReport` \| `null` | no |  |

### SourceRef

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `source_id` | `string` | yes |  |
| `ref` | `string` \| `null` | no |  |

### TrackHighlight

A named feature the route passed: a summit, a pass, a lake.

"Slieve Donard, 850 m, 5.6 km in" is the single most useful sentence about a hike, and
neither the GPX nor the timeline contains it -- it comes from OSM along the track.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | `string` | yes |  |
| `kind` | `string` | yes |  |
| `lat` | `number` | yes |  |
| `lon` | `number` | yes |  |
| `ele_m` | `number` \| `null` | no |  |
| `offset_m` | `number` | no |  |
| `distance_from_track_m` | `number` | no |  |
| `osm_id` | `string` \| `null` | no |  |

### TrackMeta

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `string` | yes |  |
| `source_id` | `string` | yes |  |
| `name` | `string` | yes |  |
| `activity_type` | `string` \| `null` | no |  |
| `start` | `string` | yes |  |
| `end` | `string` | yes |  |
| `timezone` | `string` | no |  |
| `bbox` | array of `any` \| `null` | no |  |
| `stats` | `TrackStats` | no |  |
| `point_count` | `integer` | no |  |
| `simplified_ref` | `string` \| `null` | no |  |
| `original_ref` | `string` \| `null` | no |  |
| `mergeable_with` | array of `string` | no |  |

### TrackStats

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `distance_m` | `number` | no |  |
| `ascent_m` | `number` | no |  |
| `descent_m` | `number` | no |  |
| `max_ele_m` | `number` \| `null` | no |  |
| `min_ele_m` | `number` \| `null` | no |  |
| `moving_time_s` | `number` | no |  |
| `elapsed_time_s` | `number` | no |  |
| `avg_hr` | `number` \| `null` | no |  |
| `max_hr` | `number` \| `null` | no |  |
| `elevation_threshold_m` | `number` | no |  |

### TransitDetail

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | no |  |
| `distance_m` | `number` | no |  |
| `duration_s` | `number` | no |  |
| `geometry_reliability` | `GeometryReliability` | no |  |
| `mode_hint` | `string` \| `null` | no |  |

### TripStats

Trip-level statistics. NO ELEVATION -- telemetry belongs to activities.

A city break must produce a meaningful stats block; an alpine trip must not push
elevation up to trip level. See functional-spec section 10.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `day_count` | `integer` | no |  |
| `excluded_day_count` | `integer` | no |  |
| `event_count` | `integer` | no |  |
| `suppressed_event_count` | `integer` | no |  |
| `place_count` | `integer` | no |  |
| `overnight_count` | `integer` | no |  |
| `photo_count` | `integer` | no |  |
| `video_count` | `integer` | no |  |
| `track_count` | `integer` | no |  |
| `distance_by_mode_m` | `object` | no |  |
| `countries` | array of `string` | no |  |
| `unaccounted_hours` | `number` | no |  |
| `unaccounted_count` | `integer` | no |  |
| `days_blind` | `integer` | no |  |
| `coverage` | array of `DayCoverage` | no |  |

### UnknownDetail

An unaccounted gap. States facts only -- never a classification. ADR-0007.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `string` | no |  |
| `gap_hours` | `number` | no |  |
| `displacement_km` | `number` | no |  |
| `from_place` | `Place` \| `null` | no |  |
| `to_place` | `Place` \| `null` | no |  |
| `candidate_types` | array of `EventType` | no |  |
