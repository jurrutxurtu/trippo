# UX flows

Desktop-first, ≥1280 px. The capsule *viewer* is responsive; the studio is not.

## The seven steps

```
1 LIBRARY     → every trip in the workspace; drafts are marked
2 NEW TRIP    → name; dates proposed from photo EXIF; native folder pickers
3 IMPORT      → live stage-by-stage progress over SSE
4 REPORT      → coverage matrix + degradations, before anything is asserted
5 CURATE      ◄── the phase: agree the itinerary, one decision at a time
6 CAPSULE     → the explorer; editing stays available, export from here
```

## Step 3 — the Ingestion Report

Shown **before** the draft, because it frames everything after it.

- Per-day coverage strip: timeline ▮ / photos ▮ / GPX ▮ / blind ▯
- Degradations in plain language, prioritising the actionable:
  *"0 of 1,097 photos contain GPS. Your Google Photos export may have stripped location data —
  re-exporting with location enabled would substantially improve results."*
  *"ffmpeg not found: 127 videos imported without poster frames."*
- Files skipped, with reasons.

This turns "why does day 2 look empty?" into "day 2 has no timeline data, and here is why".

## Step 4 — curation

```
┌──────────┬────────────────────────────────┬──────────────────────┐
│ DAY RAIL │   EVENT TIMELINE               │  MAP                 │
│          │                                │                      │
│ D1 ▮▮▯   │  ┌──────────────────────────┐  │   [MapLibre]         │
│ D2 ▯▮▯ ⚠ │  │ 10:26  Hike · Glendalough│  │                      │
│ D3 ▮▯▮   │  │ 12.4 km · +680 m · 3h34m │  ├──────────────────────┤
│ …        │  │ [12 photos]              │  │  ELEVATION           │
│          │  └──────────────────────────┘  │  (only if the        │
│ exclude  │  ┌──────────────────────────┐  │   selected event     │
│ ☐ day    │  │ ⚠ UNACCOUNTED · 47 h     │  │   has a track)       │
│          │  │ Bilbao → Dublin, 1,600 km│  │                      │
│          │  │ [Ferry] [Flight] [Drive] │  │                      │
│          │  └──────────────────────────┘  │                      │
├──────────┴────────────────────────────────┴──────────────────────┤
│ UNASSIGNED POOL  42 photos · 0 tracks      [Find nearby photos…] │
└───────────────────────────────────────────────────────────────────┘
```

Rules that make it pleasant:

- **Keyboard first.** `j`/`k` navigate, `1`–`9` set type, `x` suppress, `p` pool, `⌘Z` undo.
  Curating 50 events with a mouse is a chore; with keys it is two minutes.
- **Every destructive action shows an undo toast.** No confirmation dialogs.
- **Confidence and provenance on demand** — "why is this here?" expands to
  *"6 h 23 m stationary, 22:10–06:40 local, overnight rule"*.
- **Suppressed events are collapsed, not hidden**: "8 minor stops hidden — show".
- **Unaccounted gaps are prominent and actionable**, never quiet.
- The right panel is a **component registry keyed by event type**: a flight renders an airport-pair
  card, a visit renders place + photos, a hike renders track + profile. A city trip never shows an
  empty elevation chart.

## Step 5 — the curation phase

**Ingestion produces a draft, not a trip.** A capsule exists the moment the import
finishes, but until someone has been through it, it is a machine's guess. The whole claim
of the product is that the human decides, so that has to be a real step with a beginning
and an end — not a toggle hidden inside the reading view.

A trip is therefore `draft` until it is agreed, and the library marks it so.

### The agenda

`/api/curation/agenda` turns the coherence checks into an ordered queue. Three kinds, and
the distinction is the point:

| Kind | Meaning | Blocks finishing |
|---|---|---|
| **decide** | Only you know this. An unaccounted gap is a question, not a defect. | **yes** |
| **check** | Probably wrong, cheap to confirm. Two overnights, photos in the pool. | no |
| **polish** | Entirely optional. Day titles, contested place names. | no |

Presented **one at a time**, hardest first. A list of forty problems is a chore; a queue of
forty decisions with the next one in front of you is a task. Every item carries the
photographs involved, so a decision is made looking at the evidence.

A gap always offers the suggested conversions *and* every other plausible one — a
suggestion that turns out to be wrong must never be a dead end — plus "leave it
unexplained", which is a legitimate answer.

### Finishing

**Finish curating** records that a human went through it. It locks nothing: every
operation stays available afterwards, and the trip can be reopened. It is undoable like
any other operation.

## Step 6 — the capsule explorer

**Not a scrolling article.** The first prototype was an editorial page — photographs, stats, a
decorative map — and it was the wrong product. A finished trip is something you *explore*.

```
┌──────────────────────────────┬────────────────────────────────────────┐
│ TIMELINE                     │ MAP                                    │
│                              │                                        │
│ ▸ Day 5  Dublin              │   scope: TRIP                          │
│ ▾ Day 6  Mourne Mountains    │   whole route, day markers,            │
│    07:31 drive  → Rath       │   clustered photo pins                 │
│    11:44 hike   Slieve Donard│                                        │
│          12.0 km · +645 m    │   scope: DAY                           │
│    15:48 visit  Carrick Cafe │   fits Day.bbox; that day's legs lit,  │
│    20:07 stay   Hawthorn     │   the rest faded to context            │
│ ▸ Day 7  Belfast             │                                        │
│                              │   scope: ACTIVITY                      │
│ ─────────────────────────────│   fits the track; trailhead and summit │
│ ELEVATION (activity only)    │   marked, photos placed along it       │
│  ╱╲__╱╲  Slieve Donard 850 m │                                        │
└──────────────────────────────┴────────────────────────────────────────┘
```

### Three scopes, one state machine

`trip → day → activity`. Selection drives the map; clicking the map drives selection. Zooming
out one level is always available and always obvious.

| Scope | Map shows | Timeline shows |
|---|---|---|
| `trip` | whole route, ferry legs dashed, day markers, clustered photo pins | all days collapsed, stats header |
| `day` | fits `Day.bbox`; that day's legs lit, the rest faded | that day expanded, events listed |
| `activity` | fits the track; trailhead, summit, photos along the route | the activity detail panel |

### Activity detail

Opens when an event with a track is selected. Elevation profile (uPlot) with the cursor **synced
bidirectionally** to the map: hovering the chart moves a marker along the route, hovering the route
moves the chart cursor. Both read one shared index into the resampled profile — a single source of
truth rather than two hover handlers that drift apart.

Shows distance, ascent above the stated threshold, max elevation, moving time, heart rate where the
GPX carries it, **summits and passes crossed** (from OSM along the track), and the photographs taken
during it, positioned at the point on the track where each was shot.

### Map pins

Photos (clustered), named places, overnight stays, and unaccounted gaps — the last drawn as a dashed
line labelled "route unknown", never as a confident route.

### Export

A self-contained `index.html` embedding this explorer, plus `media/`. Video is referenced but
excluded in the POC.

## Future UX candidates **[LATER]**

Inferred-geotag write-back to EXIF · peak/POI naming from OSM along tracks · weather and golden-hour
backfill · "places I would return to" flags · campervan overnight-spot log · year-in-review across
capsules · Strava/Garmin Connect activity picker.
