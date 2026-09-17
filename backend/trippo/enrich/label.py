"""Enrichment orchestration -- turning coordinates into names.

Strategy varies by event type, because the right label does too:

    overnight   the campsite or hotel                  point lookup, lodging affinity
    visit/stop  the monument, viewpoint or beach       point lookup
    hike/bike   the SUMMIT, not the car park           sampled along the whole track
    drive       "Dublin -> Wicklow"                    borrowed from neighbouring events
    ferry       "Rosslare -> Bilbao"                   ferry terminals at each end
    unknown     nothing at all                         must stay unlabelled (ADR-0007)

Three guarantees:

* **A user-edited name is never overwritten.** `place.source == USER` is final, including
  across re-runs.
* **Failure is a degradation, not an error.** Providers are public and best-effort; this
  network already blocks Photon outright. A run that names 60 of 95 places and leaves the
  rest for later is normal.
* **Everything is cached**, so re-runs are instant and offline.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from trippo.config.heuristics import (
    FETCH_BATCH,
    GEOCODE_RADIUS_MAX_M,
    GEOCODE_RADIUS_MIN_M,
    PLACE_CONFIDENCE_CLEAR,
    PLACE_CONFIDENCE_CONTESTED,
    RANK_REPEAT_WINDOW,
    TRACK_SAMPLE_POINTS,
)
from trippo.domain.models import (
    ACTIVITY_TYPES,
    TRANSIT_TYPES,
    Event,
    EventType,
    Place,
    PlaceSource,
    Trip,
)
from trippo.domain.summarize import summarize
from trippo.enrich.cache import GeocodeCache, cache_key
from trippo.enrich.rank import RankContext, best
from trippo.ports.geocoder import GeocodeQuery, Geocoder, PlaceCandidate

ProgressFn = Callable[[int, int, str], None]


@dataclass
class EnrichReport:
    events_considered: int = 0
    named: int = 0
    already_named: int = 0
    user_locked: int = 0
    unresolved: int = 0
    contested: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    provider_failures: dict[str, int] = field(default_factory=dict)
    degradations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.named} named, {self.unresolved} unresolved, "
            f"{self.contested} contested, {self.user_locked} user-locked "
            f"(cache {self.cache_hits} hits / {self.cache_misses} misses)"
        )


def enrich_trip(
    trip: Trip,
    geocoders: Iterable[Geocoder],
    cache: GeocodeCache,
    *,
    deep_lookup=None,
    progress: ProgressFn | None = None,
) -> EnrichReport:
    """Name every event that needs and deserves a name. Mutates `trip` in place.

    Runs in two phases, which matters a great deal for speed:

    1. **Resolve** -- collect every query point across every event, deduplicate them,
       serve what the cache already knows, and fetch the remainder in provider-sized
       batches. Six Overpass points per request instead of one turns ~25 minutes of
       sequential round-trips into a couple of minutes.
    2. **Rank** -- purely local, using each event's own type, duration and media.
    """
    report = EnrichReport()
    providers = list(geocoders)

    targets = [e for e in trip.events if _needs_name(e, report)]
    report.events_considered = len(targets)

    plans = [(e, _query_points(e, _radius_for(e))) for e in targets]
    resolved = _resolve_all(
        [q for _, qs in plans for q in qs], providers, cache, deep_lookup, progress
    )

    recent: list[str] = []
    for i, (event, queries) in enumerate(plans, start=1):
        if progress:
            progress(i, len(plans), f"naming {event.type.value}")
        candidates: list[PlaceCandidate] = []
        for q in queries:
            candidates.extend(resolved.get(_point_key(q), []))
        chosen = _apply_name(
            event, candidates, _radius_for(event), report, frozenset(recent)
        )
        if chosen:
            recent.append(chosen.lower())
            del recent[:-RANK_REPEAT_WINDOW]

    # Transit legs read as "A -> B" and borrow from their neighbours, so they must run
    # after every place has been resolved.
    _label_transits(trip)

    # Names have changed, so day titles and subtitles derived from them are now stale.
    for day in trip.days:
        day.title = None
        day.subtitle = None
    summarize(trip)

    report.cache_hits = cache.hits
    report.cache_misses = cache.misses
    for p in providers:
        failures = getattr(p, "failures", 0)
        if failures:
            report.provider_failures[p.name] = failures
    _degradations(report, providers)
    return report


def _point_key(q: GeocodeQuery) -> tuple:
    return (round(q.lat, 5), round(q.lon, 5), round(q.radius_m / 100.0))


def _resolve_all(
    queries: list[GeocodeQuery],
    providers: list[Geocoder],
    cache: GeocodeCache,
    deep_lookup,
    progress: ProgressFn | None,
) -> dict[tuple, list[PlaceCandidate]]:
    """Cache-first, then batched fetch, walking down the provider cascade."""
    unique: dict[tuple, GeocodeQuery] = {}
    for q in queries:
        unique.setdefault(_point_key(q), q)

    out: dict[tuple, list[PlaceCandidate]] = {}
    pending = dict(unique)

    for provider in providers:
        if not pending:
            break

        # Serve from cache first. An empty cached result is meaningful -- it means this
        # provider has already been asked and had nothing, so fall through rather than
        # ask again.
        still_missing: dict[tuple, GeocodeQuery] = {}
        for key, q in pending.items():
            cached = cache.get(cache_key(q.lat, q.lon, q.radius_m, provider.name))
            if cached is None:
                still_missing[key] = q
            elif cached:
                out[key] = cached
        pending = {k: v for k, v in pending.items() if k not in out}

        keys = list(still_missing)
        for start in range(0, len(keys), FETCH_BATCH):
            chunk_keys = keys[start : start + FETCH_BATCH]
            chunk = [still_missing[k] for k in chunk_keys]
            if progress:
                progress(
                    min(start + FETCH_BATCH, len(keys)),
                    len(keys),
                    f"{provider.name} lookup",
                )
            try:
                found = provider.lookup(chunk)
            except Exception:
                found = {}
            for j, key in enumerate(chunk_keys):
                q = still_missing[key]
                cands = found.get(j, [])
                if not cands and deep_lookup is not None and provider.name == "overpass":
                    cands = deep_lookup(q)
                cache.put(cache_key(q.lat, q.lon, q.radius_m, provider.name), provider.name, cands)
                if cands:
                    out[key] = cands

        pending = {k: v for k, v in pending.items() if k not in out}

    return out



# --------------------------------------------------------------------------- selection


def _needs_name(event: Event, report: EnrichReport) -> bool:
    if event.type is EventType.UNKNOWN:
        return False  # an unaccounted gap must never acquire a location (ADR-0007)
    if event.type in TRANSIT_TYPES:
        return False  # handled by _label_transits
    if event.place is None or event.place.lat is None:
        return False  # nothing to look up

    if event.place.source is PlaceSource.USER:
        report.user_locked += 1
        return False
    if event.place.source in (PlaceSource.OSM, PlaceSource.NOMINATIM, PlaceSource.GOOGLE):
        report.already_named += 1
        return False
    if event.place.source is PlaceSource.GPX and event.place.name:
        report.already_named += 1  # <trk><name> beats anything a geocoder will say
        return False
    return True


def _radius_for(event: Event) -> float:
    """Wider search for longer stays and for weakly-placed events.

    An event located from interpolated photos may be hundreds of metres out; querying it
    at 80 m returns nothing, or something wrong.
    """
    minutes = event.duration_s / 60.0
    base = GEOCODE_RADIUS_MIN_M + min(minutes, 180.0) / 180.0 * (
        GEOCODE_RADIUS_MAX_M - GEOCODE_RADIUS_MIN_M
    )
    confidence = event.place.confidence if event.place else 1.0
    return min(base * (2.0 - max(confidence, 0.1)), GEOCODE_RADIUS_MAX_M * 2.5)


# --------------------------------------------------------------------------- naming


def _apply_name(
    event: Event,
    candidates: list[PlaceCandidate],
    radius: float,
    report: EnrichReport,
    used_names: frozenset[str] = frozenset(),
) -> str | None:
    """Choose and apply a name. Returns the chosen name, or None."""
    if not candidates:
        report.unresolved += 1
        return None

    ctx = RankContext(
        event_type=event.type,
        duration_s=event.duration_s,
        media_count=len(event.media_ids),
        position_confidence=event.place.confidence if event.place else 1.0,
        search_radius_m=radius,
        used_names=used_names,
    )
    winner, clear = best(candidates, ctx)
    if winner is None:
        report.unresolved += 1
        return None

    c = winner.candidate
    event.place = Place(
        name=c.name,
        lat=event.place.lat if event.place else c.lat,
        lon=event.place.lon if event.place else c.lon,
        address=c.address,
        google_place_id=event.place.google_place_id if event.place else None,
        osm_id=c.osm_id,
        category=c.kind,
        source=c.source,
        confidence=PLACE_CONFIDENCE_CLEAR if clear else PLACE_CONFIDENCE_CONTESTED,
    )
    if not event.title:
        event.title = c.name
    event.provenance.rules.append(
        f"named from {c.source.value}: {'; '.join(winner.reasons[:3])}"
    )
    report.named += 1
    if not clear:
        report.contested += 1
    return c.name


def _query_points(event: Event, radius: float) -> list[GeocodeQuery]:
    """Where to look.

    A hike is not its trailhead. Sampling along the track finds the summit, the lake and
    the pass it actually crossed -- far better evidence than the start coordinate, and it
    is why `natural=peak` scores highest for activities.
    """
    assert event.place is not None and event.place.lat is not None
    base = GeocodeQuery(
        lat=event.place.lat,
        lon=event.place.lon,  # type: ignore[arg-type]
        radius_m=radius,
        label=event.title or event.type.value,
    )
    if event.type not in ACTIVITY_TYPES:
        return [base]

    line = event.geometry.polyline if event.geometry else None
    if not line or len(line) < 3:
        return [base]

    step = max(1, len(line) // TRACK_SAMPLE_POINTS)
    sampled = line[::step][:TRACK_SAMPLE_POINTS]
    return [base] + [
        GeocodeQuery(lat=lat, lon=lon, radius_m=radius, label=base.label)
        for lat, lon in sampled
    ]


# --------------------------------------------------------------------------- transits


def _label_transits(trip: Trip) -> None:
    """Give drives, ferries and flights an "A -> B" label from their neighbours.

    A journey has no place of its own; it has two ends. Reading "Dublin -> Wicklow" is
    far more useful than naming the stretch of road it happened to be measured on.
    """
    ordered = sorted(trip.events, key=lambda e: e.start)
    for i, e in enumerate(ordered):
        if e.type not in TRANSIT_TYPES:
            continue
        if e.place and e.place.source is PlaceSource.USER:
            continue
        origin = _nearest_named(ordered, i, step=-1)
        destination = _nearest_named(ordered, i, step=1)
        if not (origin or destination):
            continue
        label = f"{origin or '?'} \u2192 {destination or '?'}"
        if not e.title:
            e.title = label
        e.provenance.rules.append("labelled from neighbouring places")


def _nearest_named(ordered: list[Event], start: int, step: int) -> str | None:
    i = start + step
    while 0 <= i < len(ordered):
        e = ordered[i]
        if (
            e.type not in TRANSIT_TYPES
            and e.type is not EventType.UNKNOWN
            and e.place
            and e.place.name
            and e.place.source is not PlaceSource.COORDS
        ):
            return e.place.name
        i += step
    return None


# --------------------------------------------------------------------------- reporting


def _degradations(report: EnrichReport, providers: list[Geocoder]) -> None:
    for name, count in report.provider_failures.items():
        report.degradations.append(
            f"{name}: {count} request(s) failed or were rejected. Affected places keep "
            "their coordinate labels and can be retried later."
        )
    if report.unresolved:
        report.degradations.append(
            f"{report.unresolved} place(s) could not be named from any provider. They "
            "remain editable by hand."
        )
