# Capsule format

`SCHEMA_VERSION = "0.4.0"` — defined in `backend/trippo/capsule/version.py`.

A capsule is a **directory-as-document**: portable, diffable, inspectable, git-able, and trivially
uploadable later. No database. See ADR-0003.

## Layout

```
MyTrip.capsule/
  capsule.json               trip · days · events · tracks(meta) · media(meta) · stats · notes
  tracks/<trackId>.gpx       original file, verbatim
  tracks/<trackId>.json      simplified polyline + resampled elevation profile
  media/thumb/<hash>.webp    256 px grid thumbnail
  media/web/<hash>.webp      1600 px derivative  ← what a hosted viewer would serve
  media/index.local.json     hash → absolute original path   [NEVER uploaded or exported]
  reports/ingestion.json     the Ingestion Report
  export/index.html          written by `just export` only
```

### Portability rules (ADR-0001)

1. **`capsule.json` contains no absolute paths.** Media are referenced by content hash; tracks by
   id. Anything machine-specific lives in `media/index.local.json`, which is excluded from export
   and from any future upload.
2. **Web derivatives are materialised at write time**, so a future hosted viewer can serve the
   capsule verbatim without access to originals.
3. **Originals are never copied** by default. An explicit "bundle originals" archival export exists
   for the user who wants one.

## Top-level `capsule.json`

```jsonc
{
  "schemaVersion": "0.1.0",
  "trip": { "id", "title", "subtitle?", "dateRange", "defaultTimezone", "coverMediaId?", "notes?" },
  "sources": [ { "id", "kind", "detectedFormat", "fileHash", "importedAt", "report" } ],
  "days":   [ { "id", "index", "date", "timezone", "excluded", "title?", "note?",
              "eventIds",           // events this day OWNS (local start date falls here)
              "spanningEventIds" }  // multi-day events continuing through this day
          ],
  "events": [ /* see below */ ],
  "tracks": [ /* TrackMeta */ ],
  "media":  [ /* MediaAsset */ ],
  "unassignedMediaIds": [], "unassignedTrackIds": [],
  "stats": { /* TripStats — no elevation, ever */ }
}
```

## Event

```jsonc
{
  "id", "dayId", "type", "status": "active|suppressed", "suppressReason?",
  "start", "end", "timezone", "continuesToNextDay": false,
  "place?": { "name", "lat", "lon", "address?", "googlePlaceId?", "osmId?",
              "source": "osm|nominatim|photon|google|gpx|user|coords", "confidence" },
  "geometry?": { "kind": "point|line", "trackId?", "polyline?" },
  "mediaIds": [], "trackIds": [],
  "provenance": { "derivedFrom": [SourceRef], "rules": ["..."], "confidence": 0.0,
                  "absorbed": [EventRef] },
  "userEdited": false, "title?", "note?",
  "detail": { "kind": "<event type>", ... }
}
```

### `detail` variants

| kind | fields |
|---|---|
| `drive` / `ferry` / `flight` | `distanceM`, `durationS`, `geometryReliability`; ferry adds `operator?`, `fromPort?`, `toPort?`; flight adds `segments[{from,to,flightNo,dep,arr}]`, `layovers[]` |
| `hike` / `walk` / `bike` | `ActivityStats`: `distanceM`, `ascentM`, `descentM`, `maxEleM`, `minEleM`, `movingTimeS`, `elapsedTimeS`, `avgHr?`, `maxHr?` |
| `visit` / `stop` / `overnight` | `durationS`, `category?`, `accommodation?` |
| `unknown` | `gapHours`, `displacementKm`, `candidateTypes[]` |

**`geometryReliability`** ∈ `measured | sparse | assumed`. A crossing reconstructed from two
breadcrumbs is `sparse` and must not render as a confident line.

## Invariants

Checked by `capsule/validate.py` on every read, write and curation operation:

1. Every `mediaId` appears in **exactly one** active event **or** in `unassignedMediaIds`.
2. Same for tracks.
3. Every `event.dayId` resolves; every `day.eventIds` entry resolves; the relation is consistent
   both ways.
4. Day `index` values are contiguous from 1 across non-excluded days.
5. `event.start <= event.end`; all datetimes are timezone-aware.
6. Suppressed events have a `suppressReason`.
7. No absolute filesystem path appears anywhere in `capsule.json`.

## Migrations

Changing any capsule model requires, in the same commit:

1. a bump to `SCHEMA_VERSION`;
2. a migration function registered in `capsule/migrate.py`;
3. an entry in the table below.

`read()` applies migrations in order and rewrites on save. Reading a **newer** capsule than the code
understands is a hard error, never a partial parse.

| From | To | Change |
|---|---|---|
| — | 0.1.0 | Initial format. |
