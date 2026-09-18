"""Enrichment: cache, ranking and orchestration.

Entirely offline. Providers are faked, because the real ones are public, rate-limited and
-- as this machine demonstrates -- sometimes blocked outright. Tests must never depend on
them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trippo.domain.models import DateRange as DR
from trippo.domain.models import (
    Event,
    EventType,
    Geometry,
    Place,
    PlaceDetail,
    PlaceSource,
    Provenance,
    TransitDetail,
    Trip,
    UnknownDetail,
)
from trippo.enrich.cache import GeocodeCache, cache_key
from trippo.enrich.label import _radius_for, enrich_trip
from trippo.enrich.rank import RankContext, best, rank
from trippo.ports.geocoder import GeocodeQuery, PlaceCandidate

T0 = datetime(2023, 9, 23, 10, 0, tzinfo=UTC)


def _c(name: str, kind: str, dist: float, source=PlaceSource.OSM) -> PlaceCandidate:
    return PlaceCandidate(
        name=name, kind=kind, distance_m=dist, lat=53.0, lon=-6.3, source=source
    )


def _event(
    etype: EventType,
    minutes: float = 60,
    lat: float | None = 53.012,
    confidence: float = 0.0,
    source: PlaceSource = PlaceSource.COORDS,
) -> Event:
    detail = UnknownDetail() if etype is EventType.UNKNOWN else PlaceDetail()
    return Event(
        id=f"e_{etype.value}",
        type=etype,
        start=T0,
        end=T0 + timedelta(minutes=minutes),
        place=None
        if lat is None
        else Place(
            name="53.0120, -6.3290",
            lat=lat,
            lon=-6.329,
            source=source,
            confidence=confidence,
        ),
        detail=detail,
    )


def _trip(events: list[Event]) -> Trip:
    return Trip(
        id="t",
        title="t",
        date_range=DR(start=T0.date(), end=T0.date()),
        created_at=T0,
        updated_at=T0,
        events=events,
    )


class FakeGeocoder:
    """Returns a fixed candidate list for every query, and counts batches."""

    def __init__(self, name: str, candidates: list[PlaceCandidate]) -> None:
        self.name = name
        self._candidates = candidates
        self.failures = 0
        self.calls = 0
        self.batch_sizes: list[int] = []

    def lookup(self, queries):
        self.calls += 1
        self.batch_sizes.append(len(queries))
        return {i: list(self._candidates) for i in range(len(queries))}


class DeadGeocoder:
    def __init__(self, name: str = "dead") -> None:
        self.name = name
        self.failures = 0

    def lookup(self, queries):
        self.failures += len(queries)
        raise ConnectionError("provider is blocked")


@pytest.fixture
def cache(tmp_path):
    with GeocodeCache(tmp_path / "c.sqlite") as c:
        yield c


# --------------------------------------------------------------------------- cache


def test_cache_round_trips_candidates(cache):
    key = cache_key(53.012, -6.329, 300, "overpass")
    assert cache.get(key) is None
    cache.put(key, "overpass", [_c("Glendalough", "tourism=attraction", 40)])
    got = cache.get(key)
    assert got is not None
    assert got[0].name == "Glendalough"
    assert got[0].source is PlaceSource.OSM


def test_cache_key_buckets_nearby_points_and_radii():
    a = cache_key(53.01200, -6.32900, 380, "overpass")
    b = cache_key(53.012001, -6.329001, 400, "overpass")
    assert a == b, "an ~11 m grid and bucketed radius should share a cache entry"
    assert a != cache_key(53.012, -6.329, 380, "nominatim")


def test_an_empty_cached_result_is_remembered(cache):
    """Otherwise every run re-asks a provider that has already said 'nothing here'."""
    key = cache_key(53.012, -6.329, 300, "overpass")
    cache.put(key, "overpass", [])
    assert cache.get(key) == []


# --------------------------------------------------------------------------- mirrors


def test_a_failing_mirror_is_demoted_for_the_rest_of_the_run():
    """One sick mirror must not be re-tried first on every batch.

    Measured on 2026-09-18: overpass-api.de answered in 22 s while kumi.systems took 4.7 s.
    Trying the slow one first, for every batch, is what made a Morocco import crawl.
    """
    import httpx

    from trippo.enrich.overpass import OverpassGeocoder

    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        if "bad" in str(request.url):
            raise httpx.ConnectTimeout("dead", request=request)
        return httpx.Response(200, json={"elements": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    geo = OverpassGeocoder(
        client=client, endpoints=["https://bad/api", "https://good/api"]
    )
    q = GeocodeQuery(lat=31.06, lon=-7.91, radius_m=300)

    geo.lookup([q])
    geo.lookup([q])

    # First pass tries the dead mirror once; the second must not.
    assert attempts[0].startswith("https://bad")
    assert all(a.startswith("https://good") for a in attempts[1:]), attempts


def test_the_last_healthy_mirror_is_never_demoted():
    """Something has to be tried, even when everything is unwell."""
    import httpx

    from trippo.enrich.overpass import OverpassGeocoder

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectTimeout("dead", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    geo = OverpassGeocoder(client=client, endpoints=["https://a/api", "https://b/api"])
    q = GeocodeQuery(lat=31.06, lon=-7.91, radius_m=300)

    geo.lookup([q])
    geo.lookup([q])
    assert calls["n"] >= 3, "must keep trying rather than give up entirely"


# --------------------------------------------------------------------------- ranking


def test_the_glendalough_case():
    """The motivating example: 15 real candidates, one right answer.

    Observed live from Overpass at 53.012, -6.329.
    """
    candidates = [
        _c("Glendalough Hotel", "tourism=hotel", 120),
        _c("Glendalough", "tourism=attraction", 210),
        _c("Saint Kevin's Cross", "historic=high_cross", 150),
        _c("Lower Lake", "natural=water", 400),
        _c("Glendalough Visitor Centre", "tourism=museum", 260),
    ]
    winner, _clear = best(
        candidates, RankContext(EventType.VISIT, duration_s=45 * 60, search_radius_m=500)
    )
    assert winner is not None
    assert "Glendalough" in winner.candidate.name
    assert winner.candidate.kind != "tourism=hotel", "a hotel is not a daytime visit"


def test_roads_are_never_a_place():
    """Plain reverse geocoding answers 'R757' for Glendalough. It must not survive."""
    ranked = rank(
        [_c("R757", "highway=secondary", 5, PlaceSource.NOMINATIM)],
        RankContext(EventType.VISIT),
    )
    assert ranked == []


def test_administrative_units_are_demoted():
    winner, _ = best(
        [
            _c("Centre Ward No. 5", "historic=memorial", 30),
            _c("Jameson Distillery Midleton", "tourism=attraction", 180),
        ],
        RankContext(EventType.VISIT, duration_s=90 * 60, search_radius_m=400),
    )
    assert winner is not None
    assert winner.candidate.name == "Jameson Distillery Midleton"


def test_an_overnight_prefers_somewhere_to_sleep():
    winner, _ = best(
        [
            _c("Saint Kevin's Church", "historic=church", 30),
            _c("Glendalough Camping", "tourism=camp_site", 250),
        ],
        RankContext(EventType.OVERNIGHT, duration_s=9 * 3600, search_radius_m=400),
    )
    assert winner is not None
    assert winner.candidate.kind == "tourism=camp_site"


def test_a_hike_prefers_the_summit_over_the_car_park():
    winner, _ = best(
        [
            _c("Oldtown Carpark", "amenity=parking", 20),
            _c("Slieve Donard", "natural=peak", 900),
        ],
        RankContext(EventType.HIKE, duration_s=4 * 3600, search_radius_m=1000),
    )
    assert winner is not None
    assert winner.candidate.name == "Slieve Donard"


def test_duration_rules_out_an_implausible_venue():
    """A three-hour stop is not a visit to a roadside memorial."""
    winner, _ = best(
        [
            _c("Some Memorial", "historic=memorial", 20),
            _c("City Museum", "tourism=museum", 200),
        ],
        RankContext(EventType.VISIT, duration_s=3 * 3600, search_radius_m=400),
    )
    assert winner is not None
    assert winner.candidate.name == "City Museum"


def test_vague_place_subtypes_lose_to_real_ones():
    winner, _ = best(
        [_c("Rath", "place=locality", 50), _c("Newcastle", "place=village", 300)],
        RankContext(EventType.VISIT, search_radius_m=500),
    )
    assert winner is not None
    assert winner.candidate.name == "Newcastle"


def test_interpretation_boards_are_not_destinations():
    """Titanic Quarter returns a dozen 	ourism=information signboards.

    Unchecked, they out-compete the thing they describe.
    """
    winner, _ = best(
        [
            _c("Hamilton Dock Caisson", "tourism=information", 20),
            _c("SS Nomadic", "tourism=attraction", 180),
        ],
        RankContext(EventType.VISIT, duration_s=60 * 60, search_radius_m=400),
    )
    assert winner is not None
    assert winner.candidate.name == "SS Nomadic"


def test_a_notable_place_outranks_an_anonymous_plaque():
    """wikidata/heritage tags are a free, strong significance signal."""
    plaque = _c("Dr William Drennan", "historic=memorial", 30)
    landmark = _c("Titanic Belfast", "tourism=attraction", 260)
    landmark.notable = True
    winner, _ = best(
        [plaque, landmark],
        RankContext(EventType.VISIT, duration_s=90 * 60, search_radius_m=400),
    )
    assert winner is not None
    assert winner.candidate.name == "Titanic Belfast"


def test_a_name_already_used_nearby_is_demoted():
    """In a dense city one monument otherwise wins four consecutive stops."""
    ctx = RankContext(
        EventType.VISIT,
        duration_s=30 * 60,
        search_radius_m=400,
        used_names=frozenset({"northern ireland war memorial"}),
    )
    winner, _ = best(
        [
            _c("Northern Ireland War Memorial", "historic=memorial", 40),
            _c("Titanic Memorial", "historic=memorial", 150),
        ],
        ctx,
    )
    assert winner is not None
    assert winner.candidate.name == "Titanic Memorial"


def test_a_close_call_is_reported_as_contested():
    _winner, clear = best(
        [_c("Museum A", "tourism=museum", 100), _c("Museum B", "tourism=museum", 105)],
        RankContext(EventType.VISIT, duration_s=60 * 60, search_radius_m=400),
    )
    assert not clear, "near-identical candidates must be flagged for a tiebreak"


# --------------------------------------------------------------------------- radius


def test_search_radius_widens_for_weakly_placed_events():
    """An event located from interpolated photos may be hundreds of metres out."""
    strong = _event(EventType.VISIT, confidence=1.0)
    weak = _event(EventType.VISIT, confidence=0.3)
    assert _radius_for(weak) > _radius_for(strong)


def test_search_radius_widens_for_longer_stays():
    assert _radius_for(_event(EventType.VISIT, minutes=180)) > _radius_for(
        _event(EventType.VISIT, minutes=10)
    )


# --------------------------------------------------------------------------- orchestration


def test_events_are_named_and_marked_with_their_source(cache):
    trip = _trip([_event(EventType.VISIT)])
    provider = FakeGeocoder("overpass", [_c("Glendalough", "tourism=attraction", 50)])
    report = enrich_trip(trip, [provider], cache)

    assert report.named == 1
    place = trip.events[0].place
    assert place is not None
    assert place.name == "Glendalough"
    assert place.source is PlaceSource.OSM
    assert place.category == "tourism=attraction"


def test_a_user_edited_name_is_never_overwritten(cache):
    """Including across re-runs. Losing a hand-typed name would be unforgivable."""
    ev = _event(EventType.VISIT, source=PlaceSource.USER)
    ev.place.name = "Our campsite by the lake"  # type: ignore[union-attr]
    trip = _trip([ev])

    report = enrich_trip(
        trip, [FakeGeocoder("overpass", [_c("Glendalough Hotel", "tourism=hotel", 10)])], cache
    )

    assert trip.events[0].place.name == "Our campsite by the lake"  # type: ignore[union-attr]
    assert report.user_locked == 1
    assert report.named == 0


def test_a_gpx_track_name_beats_a_geocoder(cache):
    """<trk><name> is what the user called it. No OSM lookup improves on that."""
    ev = _event(EventType.HIKE, source=PlaceSource.GPX)
    ev.place.name = "County Wicklow Hiking"  # type: ignore[union-attr]
    trip = _trip([ev])

    enrich_trip(trip, [FakeGeocoder("overpass", [_c("Lower Lake", "natural=water", 10)])], cache)
    assert trip.events[0].place.name == "County Wicklow Hiking"  # type: ignore[union-attr]


def test_an_unaccounted_gap_is_never_given_a_place(cache):
    """A gap is the absence of knowledge. Naming it would be the core sin. ADR-0007."""
    gap = _event(EventType.UNKNOWN, lat=None)
    trip = _trip([gap])
    report = enrich_trip(
        trip, [FakeGeocoder("overpass", [_c("Rosslare Harbour", "amenity=ferry_terminal", 5)])],
        cache,
    )
    assert trip.events[0].place is None
    assert report.named == 0


def test_transits_are_labelled_from_their_neighbours(cache):
    origin = _event(EventType.VISIT)
    origin.id = "a"
    drive = Event(
        id="b",
        type=EventType.DRIVE,
        start=T0 + timedelta(hours=2),
        end=T0 + timedelta(hours=3),
        geometry=Geometry(kind="line"),
        provenance=Provenance(),
        detail=TransitDetail(),
    )
    dest = _event(EventType.VISIT)
    dest.id = "c"
    dest.start = T0 + timedelta(hours=4)
    dest.end = T0 + timedelta(hours=5)

    trip = _trip([origin, drive, dest])
    names = iter(
        [
            [_c("Dublin", "place=city", 50)],
            [_c("Glendalough", "tourism=attraction", 50)],
        ]
    )

    class Sequential:
        name = "overpass"
        failures = 0

        def lookup(self, queries):
            return {i: next(names, []) for i in range(len(queries))}

    enrich_trip(trip, [Sequential()], cache)
    assert drive.title is not None
    assert "\u2192" in drive.title, f"expected an A -> B label, got {drive.title!r}"


def test_queries_are_batched_not_sent_one_by_one(cache):
    """165 sequential Overpass round-trips is ~25 minutes. Batching is not optional."""
    trip = _trip([_event(EventType.VISIT) for _ in range(12)])
    for i, e in enumerate(trip.events):
        e.id = f"e{i}"
        e.place.lat = 53.0 + i * 0.05  # type: ignore[union-attr]

    provider = FakeGeocoder("overpass", [_c("Somewhere", "tourism=attraction", 50)])
    enrich_trip(trip, [provider], cache)

    assert provider.calls < 12, f"expected batching, got {provider.calls} calls"
    assert max(provider.batch_sizes) > 1


def test_a_dead_provider_degrades_instead_of_raising(cache):
    """Public providers fail. This machine already has Photon returning 403."""
    trip = _trip([_event(EventType.VISIT)])
    report = enrich_trip(trip, [DeadGeocoder()], cache)

    assert report.unresolved == 1
    assert report.named == 0
    assert trip.events[0].place.source is PlaceSource.COORDS  # type: ignore[union-attr]


def test_the_cascade_falls_through_to_the_next_provider(cache):
    trip = _trip([_event(EventType.VISIT)])
    empty = FakeGeocoder("overpass", [])
    backup = FakeGeocoder(
        "nominatim", [_c("Brockagh", "place=village", 300, PlaceSource.NOMINATIM)]
    )

    enrich_trip(trip, [empty, backup], cache)
    assert trip.events[0].place.source is PlaceSource.NOMINATIM  # type: ignore[union-attr]


def test_a_second_run_is_served_entirely_from_cache(cache):
    trip = _trip([_event(EventType.VISIT)])
    provider = FakeGeocoder("overpass", [_c("Glendalough", "tourism=attraction", 50)])
    enrich_trip(trip, [provider], cache)
    first_calls = provider.calls

    again = _trip([_event(EventType.VISIT)])
    enrich_trip(again, [provider], cache)

    assert provider.calls == first_calls, "a re-run must not touch the network"
    assert again.events[0].place.name == "Glendalough"  # type: ignore[union-attr]


def test_activity_events_are_sampled_along_their_track(cache):
    """A hike is not its trailhead -- the summit is usually a kilometre in."""
    hike = _event(EventType.HIKE, minutes=240)
    hike.geometry = Geometry(
        kind="line", polyline=[(53.0 + i * 0.002, -6.3) for i in range(60)]
    )
    trip = _trip([hike])

    provider = FakeGeocoder("overpass", [_c("Slieve Donard", "natural=peak", 100)])
    enrich_trip(trip, [provider], cache)

    assert sum(provider.batch_sizes) > 1, "only the start point was queried"
    assert trip.events[0].place.name == "Slieve Donard"  # type: ignore[union-attr]
