# The pipeline, visually

What happens between "here are my files" and "here is my trip", where every decision is
made, and what ends up in the capsule.

Numbers throughout are the real Ireland 2023 run: a Google on-device export, 7 Garmin GPX
files, 1,097 photographs and 127 videos.

---

## 1. The whole thing at a glance

```
  SOURCES  (any subset; none is required)
  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │ Timeline JSON    │  │ GPX folder       │  │ Photos / videos  │
  │ 4,731 segments   │  │ 7 tracks         │  │ 1,224 files      │
  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
           │                     │                     │
           ▼                     ▼                     ▼
  ══════════════════════ INGEST ══════════════════════════════════
   sniff format          parse + simplify      EXIF → filename → mtime
   parse coordinates     compute telemetry     hash, dedup, derivatives
           │                     │                     │
           └──────────┬──────────┴──────────┬──────────┘
                      ▼                     ▼
              NormalizedObservation[]   MediaAsset[]
              (t, lat?, lon?, kind, trusted?)
                      │
                      ▼
  ═════════════════ DRAFT (deterministic) ════════════════════════
   1 dedup overlapping visits          →  2 removed
   2 GPX precedence: mask what a track covers
   3 plausibility gate: is this stay physically possible?
   4 build the PositionIndex (measured fixes only)
   5 locate photographs: EXIF → interpolate → admit defeat
   6 events from tracks, visits, moves
   7 absorb phantom stays into the crossing that swallowed them
   8 overnight detection  (AFTER step 3, never before)
   9 unaccounted gaps
  10 attach media, cluster the leftovers
  11 days, then the Golden Rule
                      │
                      ▼
  ═════════════════ ENRICH (network, optional) ═══════════════════
   Places? → Overpass → Nominatim      summits along each track
   rank by event type, cache forever
                      │
                      ▼
  ═════════════════ DERIVE (pure) ════════════════════════════════
   day titles · day stats · bounds · route segments · photo selection
                      │
                      ▼
              ┌───────────────────┐
              │  DRAFT CAPSULE    │  status: draft
              └─────────┬─────────┘
                        ▼
  ═════════════════ CURATION (you) ═══════════════════════════════
   decide · check · polish        →  status: curated
```

---

## 2. Ingest: three adapters, one output

Everything becomes a `NormalizedObservation` before any reasoning happens. The draft
builder never asks which source something came from (ADR-0005).

```
NormalizedObservation
  t                  when                    always timezone-aware
  lat, lon           where                   OPTIONAL — frequently absent
  end_t, end_lat/lon for visits and moves
  kind               visit | move | breadcrumb | media | trackpoint
  trusted_position   was this MEASURED, or did we work it out?
  hints              provider claims — never treated as truth
```

### Timeline — two layers, not one list

Google mixes three shapes in one array, and they **overlap** (ADR-0009):

```
  visit        21:44 ──────────────► 00:21   Dublin
  timelinePath 22:00 ────► 00:00                  ← rigid 2-hour boundaries
  timelinePath        00:00 ────► 02:00
  activity            00:11 ─► 00:17   WALKING 502 m

  LAYER 1  visit + activity   →  candidate events
  LAYER 2  timelinePath       →  positions ONLY, never an event
```

Treating them as peers produces a duplicate leg for every drive.

### Media — the timestamp cascade

```
  DateTimeOriginal + OffsetTimeOriginal  →  exact           1,101 files
  DateTimeOriginal alone                 →  naive local
  PXL_20230928_192141554.jpg             →  from filename     123 files
  filesystem mtime                       →  weak, flagged
```

---

## 3. The decisions, and the numbers behind them

Every one of these is a rule in `config/heuristics.py`, documented in
`heuristics-tunables.md`.

### Is this stay real?

```
  visit at Rosslare Harbour, 8 h 36 m, covers 02:00–05:00 local
        │
        ├─ next fix is 402 km away, reachable only at 781 km/h?     ──► PHANTOM
        └─ a fix 400 km away was recorded DURING the visit?         ──► PHANTOM
                                                                         │
                          absorbed into the crossing that swallowed it ◄─┘
```

Both tests are needed. The exit test alone misses the reference case, because the
mid-Atlantic breadcrumb precedes the visit's own end timestamp.

**This runs before overnight detection.** Reversed, Trippo reports "Overnight stay,
Rosslare Harbour" for a night spent at sea.

### Is this an overnight?

```
  covers local 02:00–05:00                     ──► yes
  ≥ 5 h AND spans dusk→dawn AND crosses midnight ──► yes
```

Local time at the *location*, never the reader's. Result: **23 overnights**.

### Do we know what happened here?

```
  hole between two known positions
        │
        ├─ displacement ≥ 25 km                     ──► UNACCOUNTED
        ├─ ≥ 3 h AND moved ≥ 2 km                   ──► UNACCOUNTED
        └─ otherwise                                ──► an unlogged stay, not a gap
```

Displacement is decisive, not elapsed time: a phone that logs nothing for ten hours while
parked has not hidden a journey. An early version that used *either* condition reported
**31 gaps** where **3** are real.

Gaps separated only by an isolated fix are merged — a lone mid-Atlantic breadcrumb is
evidence *of* a crossing, not an explanation of one.

### Is this worth keeping? — the Golden Rule

```
  keep if  has photos │ has a track │ is an overnight │ pinned
           │ ≥ 20 min │ ≥ 5 km │ resolves to a named POI
                             │
                    otherwise SUPPRESSED, never deleted
```

**70 suppressed** on Ireland, all recoverable behind "show hidden".

### Where was this photograph taken?

```
  EXIF GPS                     ──► measured        0 files   ← export stripped it
  interpolate from the index   ──► inferred    1,145 files
  nothing covers that instant  ──► none            79 files
```

Only **measured** positions feed the index. An inferred position must never become
evidence for the next inference — that compounds error and manufactures a route.
Geotagged photographs *do* contribute: one located shot places the burst around it.

---

## 4. Enrichment: coordinates into names

The on-device export contains **no place names at all** — only a `placeId` and
coordinates, `semanticType: UNKNOWN` for 135 of 145 visits. Without this step the
curation screen is a list of latitudes.

```
  event needs a name
        │
        ├─ has a Google placeId AND a key?  ──► Places, exact id lookup   [off by default]
        │
        ├─ Overpass  "what is actually here?"      ──► 15 candidates
        │     batched 6 points per request; mirrors fastest-first
        │
        └─ Nominatim "what is the address?"        ──► "R757"
              1 req/s, enforced in-process
                        │
                        ▼
              ╔═══════════════════════╗
              ║  RANK by event type   ║
              ╚═══════════════════════╝
   overnight  →  campsite, hotel          hike  →  natural=peak
   visit      →  monument, museum         stop  →  viewpoint, beach
   drive      →  no lookup: "A → B" from neighbours
   unknown    →  nothing. A gap never gets a location.

   + notability (wikidata/heritage)   − generic names   − admin units
   + duration fit                     − roads, rejected outright
                                      − repeats of a neighbour
```

Result on Ireland: **120 from OSM, 1 Nominatim, 7 from `<trk><name>`, 36 still
coordinates**. Zero roads, zero electoral wards.

Then, for each activity track, one Overpass query over its bounding box finds the summits,
passes and lakes it passed — filtered by distance to the *line*, not the box. **Slieve
Binnian, 745.9 m, 4 m off track**, while the GPX independently recorded 741 m max.

---

## 5. What is in a capsule

```
MyTrip.capsule/
├── capsule.json          the whole itinerary — ~2 MB for 27 days
├── tracks/
│   ├── <id>.gpx          the original file, verbatim
│   └── <id>.json         simplified polyline + resampled elevation profile
├── media/
│   ├── thumb/<hash>.webp   256 px      9 MB for 1,097 photographs
│   ├── web/<hash>.webp    1600 px    307 MB   ← what a hosted viewer would serve
│   └── index.local.json    hash → absolute original path   [NEVER shared]
└── reports/ingestion.json
```

**Originals are never copied.** 3.4 GB in, 316 MB out.

### Inside `capsule.json`

```
Trip
 ├ title, subtitle, dateRange, status (draft|curated), curatedAt
 ├ bbox                     opening view for the map
 ├ route[]                  ONE SEGMENT PER LEG, each with its own
 │                          kind and reliability so a guessed ferry
 │                          can never render like a measured trail
 ├ stats                    days, distance by mode, places, photos,
 │                          unaccounted hours, per-day coverage
 │                          — NO elevation: that belongs to activities
 ├ sources[]                what was read, and the ingestion report
 │
 ├ days[]
 │   ├ index, date, excluded
 │   ├ title, subtitle, userTitle   generated titles follow the events;
 │   │                              a hand-written one never moves
 │   ├ bbox                         fit the map to this day
 │   ├ stats                        ascent_m ONLY if the day had an activity
 │   ├ eventIds[]                   events this day owns
 │   └ spanningEventIds[]           multi-day events passing through
 │
 ├ events[]
 │   ├ type, status, suppressReason
 │   ├ start, end, timezone, utcOffset, continuesToNextDay
 │   ├ place        name, coords, source, confidence, category, placeId
 │   ├ geometry     point | line, trackId, polyline, reliability
 │   ├ mediaIds[]           everything it owns
 │   ├ selectedMediaIds[]   the few that represent it
 │   ├ provenance   derivedFrom, rules[], confidence, absorbed[]
 │   │              ← "why is this here?" is answerable from the data
 │   └ detail       one of:
 │        transit    distance, duration, reliability, modeHint
 │        ferry      + operator, ports
 │        flight     + segments[], layovers
 │        activity   stats (distance, ascent, descent, max/min ele,
 │                   moving time, HR) + highlights[] (summits crossed)
 │        place      duration, category, accommodation
 │        unknown    gapHours, displacementKm, candidateTypes[]
 │
 ├ tracks[]     name, activityType, bbox, stats, pointCount, refs
 ├ media[]      hash, kind, capturedAt, timeSource, lat/lon,
 │              locationSource, device, variant, thumb/web refs
 ├ unassignedMediaIds[]     the pool — nothing is ever lost
 └ unassignedTrackIds[]
```

### The invariant that holds it together

> Every media item appears in **exactly one** active event, **or** in the unassigned pool.
> Never both. Never neither.

Checked on every read, every write and every curation operation. It is why deleting an
event can never delete a photograph.

---

## Where to read more

| | |
|---|---|
| Why a constant is what it is | [`heuristics-tunables.md`](heuristics-tunables.md) |
| What breaks on real data | [`ingestion.md`](ingestion.md) |
| The naming cascade in detail | [`enrichment.md`](enrichment.md) |
| Field-by-field schema | [`data-model.md`](data-model.md) *(generated)* |
| The capsule as a contract | [`capsule-format.md`](capsule-format.md) |
