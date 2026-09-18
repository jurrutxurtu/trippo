/**
 * Capsule types, mirroring `backend/trippo/domain/models.py` (schema 0.2.0).
 *
 * Hand-written for now. Once the shape settles these should be generated from
 * `docs/technical/capsule.schema.json` so they cannot drift -- the same discipline the
 * backend already applies to `data-model.md`.
 */

export type EventType =
  | "drive"
  | "stop"
  | "visit"
  | "overnight"
  | "hike"
  | "walk"
  | "bike"
  | "flight"
  | "ferry"
  | "unknown";

export const ACTIVITY_TYPES: ReadonlySet<EventType> = new Set([
  "hike",
  "walk",
  "bike",
]);
export const TRANSIT_TYPES: ReadonlySet<EventType> = new Set([
  "drive",
  "flight",
  "ferry",
]);

export type EventStatus = "active" | "suppressed";
export type GeometryReliability = "measured" | "sparse" | "assumed";
export type PlaceSource =
  | "osm"
  | "nominatim"
  | "photon"
  | "google"
  | "gpx"
  | "user"
  | "coords";
export type LocationSource = "exif" | "inferred" | "user" | "none";

export interface BBox {
  min_lat: number;
  min_lon: number;
  max_lat: number;
  max_lon: number;
}

export interface Place {
  name: string;
  lat: number | null;
  lon: number | null;
  address: string | null;
  category: string | null;
  source: PlaceSource;
  confidence: number;
}

/** A summit, pass or lake the route passed. Ordered by `offset_m` along the track. */
export interface TrackHighlight {
  name: string;
  kind: string;
  lat: number;
  lon: number;
  ele_m: number | null;
  offset_m: number;
  distance_from_track_m: number;
}

export interface ActivityStats {
  distance_m: number;
  ascent_m: number;
  descent_m: number;
  max_ele_m: number | null;
  min_ele_m: number | null;
  moving_time_s: number;
  elapsed_time_s: number;
  avg_hr: number | null;
  max_hr: number | null;
  elevation_threshold_m: number;
}

export type EventDetail =
  | { kind: "transit"; distance_m: number; duration_s: number; mode_hint: string | null }
  | { kind: "ferry"; distance_m: number; duration_s: number }
  | { kind: "flight"; distance_m: number; duration_s: number }
  | { kind: "activity"; stats: ActivityStats; highlights: TrackHighlight[] }
  | { kind: "place"; duration_s: number; category: string | null }
  | {
      kind: "unknown";
      gap_hours: number;
      displacement_km: number;
      candidate_types: EventType[];
    };

export interface Provenance {
  rules: string[];
  confidence: number;
}

export interface TripEvent {
  id: string;
  day_id: string | null;
  type: EventType;
  status: EventStatus;
  start: string;
  end: string;
  utc_offset_minutes: number | null;
  continues_to_next_day: boolean;
  place: Place | null;
  geometry: {
    kind: "point" | "line";
    track_id: string | null;
    polyline: [number, number][] | null;
    reliability: GeometryReliability;
  } | null;
  /** Every media item owned by this event. */
  media_ids: string[];
  /** The small, well-spread subset that represents it. The rest are one click away. */
  selected_media_ids: string[];
  user_selected_media: boolean;
  track_ids: string[];
  provenance: Provenance;
  title: string | null;
  note: string | null;
  detail: EventDetail;
}

export interface DayStats {
  event_count: number;
  photo_count: number;
  video_count: number;
  distance_by_mode_m: Record<string, number>;
  /** Present only when the day contained a track-bearing activity. */
  ascent_m: number | null;
  has_activity: boolean;
  unaccounted_hours: number;
}

export interface Day {
  id: string;
  index: number;
  date: string;
  excluded: boolean;
  title: string | null;
  subtitle: string | null;
  note: string | null;
  event_ids: string[];
  /** Multi-day events owned by an earlier day that continue through this one. */
  spanning_event_ids: string[];
  bbox: BBox | null;
  stats: DayStats;
}

export interface TrackMeta {
  id: string;
  name: string;
  activity_type: string | null;
  start: string;
  end: string;
  bbox: [number, number, number, number] | null;
  stats: ActivityStats;
  point_count: number;
  simplified_ref: string | null;
}

export interface MediaAsset {
  id: string;
  hash: string;
  kind: "photo" | "video";
  filename: string;
  captured_at: string | null;
  lat: number | null;
  lon: number | null;
  location_source: LocationSource;
  width: number | null;
  height: number | null;
  thumb_ref: string | null;
  web_ref: string | null;
}

export interface RouteSegment {
  event_id: string;
  day_index: number;
  kind: EventType;
  reliability: GeometryReliability;
  points: [number, number][];
}

export interface TripStats {
  day_count: number;
  event_count: number;
  place_count: number;
  overnight_count: number;
  photo_count: number;
  video_count: number;
  track_count: number;
  distance_by_mode_m: Record<string, number>;
  unaccounted_hours: number;
  unaccounted_count: number;
  days_blind: number;
}

export interface Trip {
  schema_version: string;
  id: string;
  title: string;
  subtitle: string | null;
  date_range: { start: string; end: string };
  days: Day[];
  events: TripEvent[];
  tracks: TrackMeta[];
  media: MediaAsset[];
  bbox: BBox | null;
  route: RouteSegment[];
  stats: TripStats;
}

/** Resampled elevation profile, served from `/api/tracks/{id}`. */
export interface TrackGeometry {
  simplified: [number, number][];
  profile: { d: number; ele: number; lat: number; lon: number; t: number }[];
}

/** A coherence finding from /api/review. Mostly computed, not generated. */
export interface Finding {
  severity: "blocking" | "warning" | "info";
  code: string;
  message: string;
  dayId: string | null;
  eventId: string | null;
  action: string | null;
}

/** Event types a user may choose. unknown is never chosen, only resolved away. */
export const EDITABLE_TYPES: EventType[] = [
  "visit",
  "stop",
  "overnight",
  "hike",
  "walk",
  "bike",
  "drive",
  "ferry",
  "flight",
];