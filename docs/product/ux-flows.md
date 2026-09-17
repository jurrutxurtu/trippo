# UX flows

Desktop-first, ≥1280 px. The capsule *viewer* is responsive; the studio is not.

## The seven steps

```
1 NEW TRIP    → name; dates proposed from media EXIF, editable
2 DROP FILES  → Timeline? · GPX folder? · Photo folder(s)?   (any subset)
                live progress: "1,097 photos · 127 videos · 7 tracks · 433 segments"
3 REPORT      → coverage matrix + degradations, before anything is asserted
4 CURATE      ◄── the heart of the app
5 REVIEW      → stats, hero photos, tone, notes
6 SUGGEST     → optional AI titles and flags
7 CAPSULE     → read view, export
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

## Step 7 — the capsule explorer

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
