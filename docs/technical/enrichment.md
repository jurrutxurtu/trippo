# Enrichment

## Why this is core, not a nice-to-have

The Google on-device export contains **no place names**. A visit looks like this, in full:

```json
"visit": { "topCandidate": { "placeId": "ChIJG5s6Ge1OTg0RMoxMs6PEeZg",
                             "semanticType": "UNKNOWN",
                             "placeLocation": { "latLng": "43.2366903°, -2.8853877°" } } }
```

In the reference trip, **135 of 145 visits** had `semanticType: UNKNOWN`, and only **7 of 219
events** had any name at all — all of them from `<trk><name>` in GPX files. Without reverse
geocoding the curation screen is a list of latitudes, and you cannot curate what you cannot read.

## The finding that determines the design

Measured live at Glendalough, `53.012, -6.329`:

| Provider | Answer |
|---|---|
| **Nominatim** | `R757` — a regional road number |
| **Overpass** | `Glendalough` · `Glendalough Round Tower` · `Saint Kevin's Church` · `Glendalough Visitor Centre` · `Lower Lake` · `The Deer Stone` |

A geocoder answers *"what is the address here?"*. A travel app needs *"what is this place?"*. For a
trailhead, a beach or a viewpoint the address is worthless — and those are exactly the stops worth
remembering. Hence Overpass first.

## Cascade

| Step | Provider | Role | Observed behaviour |
|---|---|---|---|
| 1 | **Overpass** | named POIs — what is actually here | works; heavy queries time out (see batching) |
| 2 | **Nominatim** | address + admin hierarchy; fallback label | works; 1 req/s enforced in-process |
| 3 | **Google Places** | exact `placeId` resolution | wired, **off by default**, needs a key `[LATER]` |

**Photon is not in the cascade.** It returned `403 Forbidden` from the development machine, which is
a useful reminder that these are public best-effort services. Everything here is built to degrade.

## Batching, and why it is not optional

Measured against the public Overpass instance:

| Query shape | Result |
|---|---|
| 6 points, nodes only | ✅ 200 · 9.3 s · 120 features |
| 6 points, nodes + ways | ❌ 504 |
| 3 points, nodes + ways | ❌ 504 |
| 1 point, nodes + ways | ✅ 200 |

So enrichment runs in **two phases**: resolve, then rank.

1. **Resolve** — collect every query point across every event, deduplicate them, serve what the
   cache knows, fetch the remainder in batches of `FETCH_BATCH`. A point that comes back empty gets
   one deeper single-point retry *including* `way` elements, which carry lakes, large sites and many
   churches.
2. **Rank** — purely local.

An early version called the provider once per point. On the reference trip that is 165 sequential
round-trips, roughly 25 minutes. Batched, a cold run is about a minute; a warm one is instant.

## Query strategy by event type

The right label depends on what kind of event it is.

| Event | Strategy |
|---|---|
| `overnight` | point lookup, lodging affinity (`tourism=camp_site\|hotel`) |
| `visit` / `stop` | point lookup, monument and viewpoint affinity |
| `hike` / `bike` | **sampled along the whole track** (`TRACK_SAMPLE_POINTS`) — a hike is not its trailhead, and `natural=peak` scores highest |
| `drive` / `ferry` / `flight` | no lookup: labelled `A → B` from the nearest named neighbours |
| `unknown` | **nothing.** A gap must never acquire a location (ADR-0007) |

Search radius scales with visit duration **and with the confidence of the query point itself**. An
event located from interpolated photos may be hundreds of metres out; querying it at 80 m returns
nothing, or something wrong.

## Ranking

Fetching candidates is easy; choosing between them is the work. Glendalough returns 15 named
features and distance alone picks the wrong one.

```
score = RANK_W_TYPE     · affinity of the OSM tag class to THIS event type
      + RANK_W_DISTANCE · proximity, tolerance widened by position uncertainty
      + RANK_W_DURATION · does the stay length fit this class of place?
      + RANK_W_NOTABLE  · wikidata / wikipedia / heritage tag present
      - RANK_GENERIC_PENALTY   "Car Park", "Church", "Beach"
      - RANK_ADMIN_PENALTY     "Centre Ward No. 5", "Kenmare Municipal District"
      - RANK_REPEAT_PENALTY    already used by a neighbouring event
```

Rules learned from the reference trip, each with a test:

- **Roads are rejected outright** (`REJECT_KEYS`). This is the `R757` problem; without it,
  Nominatim's road names leak into the itinerary.
- **`place=*` is split by subtype.** A village is a real answer; a `locality` or an electoral ward is
  administrative noise. Note this must *replace* the generic `place` affinity, not `min()` with it,
  or a nearby locality beats a slightly further village.
- **Interpretation boards are demoted.** `tourism=information` scores negative: Titanic Quarter alone
  returns a dozen signboards that otherwise out-compete the thing they describe.
- **Notability breaks ties in cities.** A `wikidata` or `heritage` tag reliably separates a real
  destination from a blue plaque, and it is already in the data.
- **Duration rules out implausible venues.** A three-hour stop is not a visit to a roadside memorial.
- **Repetition is penalised.** In a dense centre the same monument otherwise wins four consecutive
  stops, which tells the reader nothing and looks broken.

When the top two candidates are within `RANK_MIN_CLEAR_MARGIN`, the result is marked **contested**
(`PLACE_CONFIDENCE_CONTESTED`). That is the hook for the LLM tiebreak in E4; until then the
deterministic winner is taken at lower confidence.

## Caching

SQLite at `~/.trippo/geocode-cache.sqlite`, keyed on
`(schema, provider, lat@4dp, lon@4dp, radius_bucket)` — roughly an 11 m grid, with radii bucketed to
100 m so a 380 m and a 400 m query share a hit.

- Entries **never expire**: place names are stable, and the providers are rate-limited.
- An **empty result is cached too**. It means "this provider has already been asked and had
  nothing", so the cascade falls through instead of re-asking on every run.
- `CACHE_SCHEMA` is bumped when `PlaceCandidate` gains a field providers must re-supply. Old entries
  are then simply never read again — cheaper and safer than migrating them.
- Cross-trip infrastructure, so it lives outside the capsule (ADR-0003).

`--offline` resolves from the cache alone and touches no network. Tests use fake providers and never
reach the internet.

## Guarantees

1. **A user-edited name is never overwritten.** `place.source == USER` is final, including across
   re-runs. This is checked before anything else.
2. **A GPX track name wins.** `<trk><name>` is what the user called it; no geocoder improves on it.
3. **Failure is a degradation, not an error.** A run that names 146 of 165 places and leaves the rest
   for later is the normal case. Every failure is counted and surfaced.
4. **Unresolved beats wrong.** Rejecting roads moved 15 events from a bad name to an honest
   coordinate label. That is an improvement.

## Results on the reference trip

```
146 named, 19 unresolved, 58 contested, 0 user-locked   (286 cache hits on a warm run)
0 roads, 0 administrative units in the output
by provider: 120 Overpass, 1 Nominatim
```

## Other enrichment

- **Sun times** — computed locally from lat/lon/date. No network. `[LATER]`
- **Weather** — Open-Meteo historical, free, no key. `[LATER]`
