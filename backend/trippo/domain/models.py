"""Trippo domain model -- the capsule schema.

PURE. No I/O, no pathlib, no httpx. See AGENTS.md section 2 (layering rule).

This module is the single source of truth for the capsule format. `docs/technical/data-model.md`
and `capsule.schema.json` are GENERATED from it -- never hand-edited. Any change here requires a
SCHEMA_VERSION bump, a migration and a `capsule-format.md` entry (AGENTS.md section 3.6).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.3.0"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, ser_json_timedelta="float")


# ============================================================================ enums


class EventType(StrEnum):
    DRIVE = "drive"
    STOP = "stop"
    VISIT = "visit"
    OVERNIGHT = "overnight"
    HIKE = "hike"
    WALK = "walk"
    BIKE = "bike"
    FLIGHT = "flight"
    FERRY = "ferry"
    UNKNOWN = "unknown"  # unaccounted gap -- ADR-0007


#: Event types whose detail carries activity telemetry (elevation, ascent, HR).
ACTIVITY_TYPES = frozenset({EventType.HIKE, EventType.WALK, EventType.BIKE})
#: Event types that represent movement between two places.
TRANSIT_TYPES = frozenset({EventType.DRIVE, EventType.FLIGHT, EventType.FERRY})


class EventStatus(StrEnum):
    ACTIVE = "active"
    SUPPRESSED = "suppressed"


class SourceKind(StrEnum):
    TIMELINE = "timeline"
    GPX = "gpx"
    MEDIA = "media"
    MANUAL = "manual"


class PlaceSource(StrEnum):
    OSM = "osm"
    NOMINATIM = "nominatim"
    PHOTON = "photon"
    GOOGLE = "google"
    GPX = "gpx"
    USER = "user"
    COORDS = "coords"  # unresolved: label is the coordinate pair itself


class TimeSource(StrEnum):
    EXIF = "exif"  # DateTimeOriginal + OffsetTimeOriginal -- exact
    EXIF_NO_OFFSET = "exif_no_offset"  # naive local, resolved against day timezone
    FILENAME = "filename"  # e.g. PXL_YYYYMMDD_HHMMSSmmm
    MTIME = "mtime"  # weak; flagged in the ingestion report
    USER = "user"


class LocationSource(StrEnum):
    EXIF = "exif"
    INFERRED = "inferred"  # interpolated from breadcrumbs or tracks
    USER = "user"
    NONE = "none"  # genuinely unlocatable -- see pathology P6


class GeometryReliability(StrEnum):
    MEASURED = "measured"  # dense trackpoints
    SPARSE = "sparse"  # a handful of breadcrumbs across a long leg
    ASSUMED = "assumed"  # endpoints only; must never render as a confident line


class MediaKind(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"


class MediaVariant(StrEnum):
    MOTION_PHOTO = "MP"
    NIGHT = "NIGHT"
    PANO = "PANO"


# ============================================================================ shared


class Place(_Base):
    name: str
    lat: float | None = None
    lon: float | None = None
    address: str | None = None
    google_place_id: str | None = None
    osm_id: str | None = None
    category: str | None = None
    source: PlaceSource = PlaceSource.COORDS
    confidence: float = 0.0


class BBox(_Base):
    """Geographic bounds, for fitting a map. (min_lat, min_lon, max_lat, max_lon)."""

    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    @classmethod
    def of(cls, box: tuple[float, float, float, float]) -> BBox:
        return cls(min_lat=box[0], min_lon=box[1], max_lat=box[2], max_lon=box[3])

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.min_lat, self.min_lon, self.max_lat, self.max_lon)


class TrackHighlight(_Base):
    """A named feature the route passed: a summit, a pass, a lake.

    "Slieve Donard, 850 m, 5.6 km in" is the single most useful sentence about a hike, and
    neither the GPX nor the timeline contains it -- it comes from OSM along the track.
    """

    name: str
    kind: str  # natural=peak, natural=saddle, mountain_pass=yes, natural=water
    lat: float
    lon: float
    #: Elevation in metres. From the OSM `ele` tag where present, else the track's own
    #: altitude at the nearest point.
    ele_m: float | None = None
    #: Distance along the track at which it was passed, for ordering and chart markers.
    offset_m: float = 0.0
    #: How far off the line it sits. A summit is metres away; a lake may be hundreds.
    distance_from_track_m: float = 0.0
    osm_id: str | None = None


class Geometry(_Base):
    kind: Literal["point", "line"]
    track_id: str | None = None
    #: Sparse fallback polyline as [[lat, lon], ...]; absent when `track_id` is set.
    polyline: list[tuple[float, float]] | None = None
    reliability: GeometryReliability = GeometryReliability.MEASURED


class SourceRef(_Base):
    source_id: str
    ref: str | None = None


class AbsorbedRef(_Base):
    """A segment this event swallowed -- a phantom visit (P1) or a duplicate (P4)."""

    ref: str
    reason: str
    start: datetime | None = None
    end: datetime | None = None


class Provenance(_Base):
    derived_from: list[SourceRef] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    absorbed: list[AbsorbedRef] = Field(default_factory=list)
    superseded_by: str | None = None  # set when GPX masks a timeline segment (ADR-0004)


# ============================================================================ event details


class _Detail(_Base):
    pass


class TransitDetail(_Detail):
    kind: Literal["transit"] = "transit"
    distance_m: float = 0.0
    duration_s: float = 0.0
    geometry_reliability: GeometryReliability = GeometryReliability.MEASURED
    mode_hint: str | None = None  # raw provider label, e.g. IN_PASSENGER_VEHICLE. A hint only.


class FerryDetail(_Detail):
    kind: Literal["ferry"] = "ferry"
    distance_m: float = 0.0
    duration_s: float = 0.0
    geometry_reliability: GeometryReliability = GeometryReliability.SPARSE
    operator: str | None = None
    from_port: str | None = None
    to_port: str | None = None


class FlightSegment(_Base):
    from_iata: str | None = None
    to_iata: str | None = None
    flight_no: str | None = None
    dep: datetime | None = None
    arr: datetime | None = None


class FlightDetail(_Detail):
    kind: Literal["flight"] = "flight"
    distance_m: float = 0.0
    duration_s: float = 0.0
    geometry_reliability: GeometryReliability = GeometryReliability.ASSUMED
    segments: list[FlightSegment] = Field(default_factory=list)
    layovers: list[str] = Field(default_factory=list)


class ActivityStats(_Base):
    """Telemetry. Lives ONLY on track-bearing activity events -- never on a trip.

    Ascent and descent use ELEVATION_THRESHOLD_M; without it GPS noise reports
    +1,400 m on a flat ride.
    """

    distance_m: float = 0.0
    ascent_m: float = 0.0
    descent_m: float = 0.0
    max_ele_m: float | None = None
    min_ele_m: float | None = None
    moving_time_s: float = 0.0
    elapsed_time_s: float = 0.0
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_threshold_m: float = 0.0  # stated so the UI can disclose it


class ActivityDetail(_Detail):
    kind: Literal["activity"] = "activity"
    stats: ActivityStats = Field(default_factory=ActivityStats)
    activity_type_hint: str | None = None  # from <trk><type>
    #: Summits, passes and lakes the route passed, ordered along the track.
    highlights: list[TrackHighlight] = Field(default_factory=list)


class PlaceDetail(_Detail):
    kind: Literal["place"] = "place"
    duration_s: float = 0.0
    category: str | None = None
    accommodation: str | None = None


class UnknownDetail(_Detail):
    """An unaccounted gap. States facts only -- never a classification. ADR-0007."""

    kind: Literal["unknown"] = "unknown"
    gap_hours: float = 0.0
    displacement_km: float = 0.0
    from_place: Place | None = None
    to_place: Place | None = None
    candidate_types: list[EventType] = Field(default_factory=list)


EventDetail = Annotated[
    TransitDetail | FerryDetail | FlightDetail | ActivityDetail | PlaceDetail | UnknownDetail,
    Field(discriminator="kind"),
]

#: Which detail class each event type uses. Changing an event's type swaps the detail
#: while preserving id, time range, media and tracks.
DETAIL_FOR_TYPE: dict[EventType, type[_Detail]] = {
    EventType.DRIVE: TransitDetail,
    EventType.FERRY: FerryDetail,
    EventType.FLIGHT: FlightDetail,
    EventType.HIKE: ActivityDetail,
    EventType.WALK: ActivityDetail,
    EventType.BIKE: ActivityDetail,
    EventType.STOP: PlaceDetail,
    EventType.VISIT: PlaceDetail,
    EventType.OVERNIGHT: PlaceDetail,
    EventType.UNKNOWN: UnknownDetail,
}


# ============================================================================ entities


class Event(_Base):
    id: str
    day_id: str | None = None
    type: EventType
    status: EventStatus = EventStatus.ACTIVE
    suppress_reason: str | None = None
    start: datetime
    end: datetime
    timezone: str = "UTC"
    utc_offset_minutes: int | None = None
    continues_to_next_day: bool = False  # pathology P5
    place: Place | None = None
    geometry: Geometry | None = None
    #: Every media item owned by this event. The Golden Rule applies: nothing is lost.
    media_ids: list[str] = Field(default_factory=list)
    #: The small, well-spread subset that represents the event. A three-hour hike can own
    #: 87 photographs; showing all of them in a timeline row helps nobody. The rest stay
    #: owned and one click away.
    selected_media_ids: list[str] = Field(default_factory=list)
    #: Set once the user curates the selection by hand, after which it is never recomputed.
    user_selected_media: bool = False
    track_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    user_edited: bool = False
    user_pinned: bool = False
    title: str | None = None
    note: str | None = None
    detail: EventDetail

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def is_activity(self) -> bool:
        return self.type in ACTIVITY_TYPES


class DayStats(_Base):
    """Per-day figures for the timeline heading.

    Elevation appears here only when the day actually contained an activity, keeping the
    scoping rule intact: a city day shows distance and photographs, nothing about climbing.
    """

    event_count: int = 0
    photo_count: int = 0
    video_count: int = 0
    distance_by_mode_m: dict[str, float] = Field(default_factory=dict)
    ascent_m: float | None = None
    has_activity: bool = False
    unaccounted_hours: float = 0.0


class Day(_Base):
    id: str
    index: int  # 1-based, contiguous across non-excluded days
    date: date
    timezone: str = "UTC"
    excluded: bool = False
    title: str | None = None
    subtitle: str | None = None
    note: str | None = None
    #: Events *owned* by this day (their local start date falls here).
    event_ids: list[str] = Field(default_factory=list)
    #: Events owned by an earlier day that continue through this one -- a ferry crossing,
    #: an overnight, a multi-day gap. Rendered read-only so the day is not misreported as
    #: empty. Ownership stays with the start day, so media are never double-counted.
    spanning_event_ids: list[str] = Field(default_factory=list)
    #: Bounds of everything that happened this day, for fitting the map.
    bbox: BBox | None = None
    stats: DayStats = Field(default_factory=DayStats)


class TrackStats(ActivityStats):
    pass


class TrackMeta(_Base):
    id: str
    source_id: str
    name: str
    activity_type: str | None = None
    start: datetime
    end: datetime
    timezone: str = "UTC"
    bbox: tuple[float, float, float, float] | None = None
    stats: TrackStats = Field(default_factory=TrackStats)
    point_count: int = 0
    simplified_ref: str | None = None  # tracks/<id>.json
    original_ref: str | None = None  # tracks/<id>.gpx
    mergeable_with: list[str] = Field(default_factory=list)  # pathology P9


class MediaAsset(_Base):
    id: str
    hash: str
    kind: MediaKind
    filename: str
    normalized_filename: str
    captured_at: datetime | None = None
    timezone: str = "UTC"
    time_source: TimeSource = TimeSource.MTIME
    lat: float | None = None
    lon: float | None = None
    location_source: LocationSource = LocationSource.NONE
    width: int | None = None
    height: int | None = None
    orientation: int | None = None
    device_id: str | None = None
    variant: MediaVariant | None = None
    duration_s: float | None = None
    thumb_ref: str | None = None
    web_ref: str | None = None
    poster_ref: str | None = None
    excluded_from_export: bool = False
    size_bytes: int = 0


class IngestionReport(_Base):
    """Surfaced to the user BEFORE the draft. Degradations are never silent."""

    source_id: str
    kind: SourceKind
    detected_format: str = "unknown"
    confidence: float = 0.0
    files_seen: int = 0
    files_parsed: int = 0
    records_total: int = 0
    records_in_window: int = 0
    skipped: list[dict[str, str]] = Field(default_factory=list)
    degradations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Source(_Base):
    id: str
    kind: SourceKind
    detected_format: str = "unknown"
    file_hash: str | None = None
    display_name: str = ""
    imported_at: datetime
    report: IngestionReport | None = None


class DayCoverage(_Base):
    date: date
    timeline_records: int = 0
    media_count: int = 0
    track_count: int = 0

    @property
    def blind(self) -> bool:
        return self.timeline_records == 0 and self.media_count == 0 and self.track_count == 0


class TripStats(_Base):
    """Trip-level statistics. NO ELEVATION -- telemetry belongs to activities.

    A city break must produce a meaningful stats block; an alpine trip must not push
    elevation up to trip level. See functional-spec section 10.
    """

    day_count: int = 0
    excluded_day_count: int = 0
    event_count: int = 0
    suppressed_event_count: int = 0
    place_count: int = 0
    overnight_count: int = 0
    photo_count: int = 0
    video_count: int = 0
    track_count: int = 0
    distance_by_mode_m: dict[str, float] = Field(default_factory=dict)
    countries: list[str] = Field(default_factory=list)
    unaccounted_hours: float = 0.0
    unaccounted_count: int = 0
    days_blind: int = 0
    coverage: list[DayCoverage] = Field(default_factory=list)

    @property
    def total_distance_m(self) -> float:
        return sum(self.distance_by_mode_m.values())


class RouteSegment(_Base):
    """One drawable leg of the overall route.

    Segmented rather than a single polyline so the map can style each leg by what it was:
    a measured GPX trail is a solid line, a ferry reconstructed from two breadcrumbs is
    dashed and labelled approximate, and an unaccounted gap is dashed with no claim at all.
    Merging them would assert a confidence the data does not support (ADR-0007).
    """

    event_id: str
    day_index: int
    kind: str  # the EventType value
    reliability: GeometryReliability = GeometryReliability.MEASURED
    points: list[tuple[float, float]] = Field(default_factory=list)


class DateRange(_Base):
    start: date
    end: date


class Trip(_Base):
    """The capsule root. Serialised to `capsule.json`.

    Invariant, checked on every read, write and curation operation: every media id appears
    in exactly one active event OR in `unassigned_media_ids` -- never both, never neither.
    """

    schema_version: str = SCHEMA_VERSION
    id: str
    title: str
    subtitle: str | None = None
    date_range: DateRange
    default_timezone: str = "UTC"
    cover_media_id: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    sources: list[Source] = Field(default_factory=list)
    days: list[Day] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    tracks: list[TrackMeta] = Field(default_factory=list)
    media: list[MediaAsset] = Field(default_factory=list)

    unassigned_media_ids: list[str] = Field(default_factory=list)
    unassigned_track_ids: list[str] = Field(default_factory=list)

    #: Bounds of the whole trip, for the map's opening view.
    bbox: BBox | None = None
    #: Drawable legs of the overall route, simplified for rendering and styled by mode.
    route: list[RouteSegment] = Field(default_factory=list)

    stats: TripStats = Field(default_factory=TripStats)

    # ---------------------------------------------------------------- lookups
    def event_by_id(self, eid: str) -> Event | None:
        return next((e for e in self.events if e.id == eid), None)

    def day_by_id(self, did: str) -> Day | None:
        return next((d for d in self.days if d.id == did), None)

    def media_by_id(self, mid: str) -> MediaAsset | None:
        return next((m for m in self.media if m.id == mid), None)

    def track_by_id(self, tid: str) -> TrackMeta | None:
        return next((t for t in self.tracks if t.id == tid), None)

    @property
    def active_events(self) -> list[Event]:
        return [e for e in self.events if e.status is EventStatus.ACTIVE]
