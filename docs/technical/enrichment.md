# Enrichment

## Why this is P0, not a nice-to-have

The Google on-device export contains **no place names**. A visit looks like this, in full:

```json
"visit": { "topCandidate": { "placeId": "ChIJG5s6Ge1OTg0RMoxMs6PEeZg",
                             "semanticType": "UNKNOWN",
                             "placeLocation": { "latLng": "43.2366903°, -2.8853877°" } } }
```

In the reference trip, **135 of 145 visits** had `semanticType: UNKNOWN`. Without reverse geocoding
the curation screen is a list of latitudes. Geocoding is therefore core functionality with a
persistent cache, not an optional enrichment pass.

## Cascade

Tried in order; the first acceptable result wins.

| Step | Provider | Why | Limits |
|---|---|---|---|
| 1 | **Overpass** (OSM) | Returns *what is actually there* — a peak, castle, beach, car park, pub. For travel, "Slieve Donard car park" beats "Bloody Bridge Rd". | Public instances throttle; batch and cache. |
| 2 | **Photon** (Komoot) | Fast structured reverse geocoding, no hard rate limit. | Best-effort service. |
| 3 | **Nominatim** | Authoritative fallback. | **1 req/s**, mandatory `User-Agent`. |
| 4 | **Google Places** | Resolves the `placeId` exactly. Wired, **off by default**. | Paid. Needs `GOOGLE_PLACES_API_KEY`. |

Search radius scales with visit duration: a 15-minute stop looks 80 m out, a 3-hour visit 400 m.

## Ranking

Candidates are scored on: POI class relevance to travel (natural/tourism/historic rank above
retail), distance from the centroid, name specificity, whether the visit duration fits the venue
type, and time of day. The best score wins outright when it is clear.

**When the top two candidates are close, the LLM breaks the tie** — given the candidate list,
duration, time of day and nearby photo count. This is the single highest-value use of the model in
the product: it turns coordinates into names. If no LLM is configured, the deterministic ranking
wins and confidence is lowered.

The model may only **choose or compose from the supplied candidates**. It may not invent a name.
Enforced by `ai/validators.py`.

## Caching

SQLite at `~/.trippo/geocode-cache.sqlite`, keyed on `(round(lat,4), round(lon,4), kind, radius)` —
roughly an 11 m grid. Entries never expire; place names are stable.

A first pass over ~145 visits takes 2–3 minutes, dominated by the Nominatim rate limit. It runs in
the background with SSE progress, and the app is fully usable meanwhile — events simply display
coordinate labels until their name arrives.

## Failure behaviour

Network failure is **not** an error. Events keep a `coords` place source
(`"43.237, -2.885"`), the Ingestion Report records the degradation, and the user can retry
enrichment at any time. See `AGENTS.md` §5.

## Other enrichment

- **Sun times** — computed locally from lat/lon/date. No network. Used by overnight detection and
  displayed as golden-hour context.
- **Weather** — Open-Meteo historical, free, no key. **[LATER]**
