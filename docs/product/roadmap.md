# Roadmap

Status as of the M4 + enrichment + derivatives work. Supersedes the milestone list in the
original plan; the **capsule view was redesigned** after the first prototype (see
`ux-flows.md` §"Capsule explorer") and that reordered everything after M4.

## Done

| | | Evidence |
|---|---|---|
| **M0** | Repo, docs, ADR-0001..0009, capsule schema, golden fixtures | `just check` |
| **M1** | Media ingest: EXIF/filename/mtime cascade, dedup, video metadata, coverage report | 1,224 files in 19 s |
| **M1b** | Derivatives: 256 px + 1600 px WebP | 2,194 files, 0 failures |
| **M2** | Source-agnostic draft builder, clustering, photo-only path | ADR-0005 |
| **M3** | Two-layer timeline adapter, dedup, plausibility gate, gaps | 3 real gaps from 31 false |
| **M4** | GPX absolute precedence, activity telemetry, mergeable tracks | ADR-0004 |
| **E1/E2** | Geocoding cascade, cache, event-type-aware ranking | 146 named, 0 roads |

86 tests. The backend can turn three raw sources into a named, curated-ready capsule.

## The redesign that reordered the rest

The first capsule prototype was an editorial scrolling page: photographs, stats, a
decorative map. Wrong product. A finished trip needs to be **explored**, not read:

> A timeline on the left going day by day with meaningful events, and a map on the right
> showing the overall view — and when you focus on a day, or especially on a hiking
> activity, the map zooms and gives more detail. Pins for photos, places and stops. For an
> activity, a detailed view with the elevation profile and the summit reached.

Consequences:

1. **The map is load-bearing for both screens.** Curation and the capsule need the same
   component — tracks, pins, clustering, fit-to-bounds. It must be built once, early, not
   twice late.
2. **There are three zoom scopes**, and they are a real state machine: `trip → day →
   activity`. Selection drives the map; the map drives selection.
3. **Activities need a first-class detail view**, not a panel: profile synced to the map
   cursor, summits crossed, ascent, where it happened.
4. **Backend gaps surfaced** that the static page had hidden (below).

## Backend gaps this exposed

Small, but blocking the map. Best done before the frontend needs them.

| Gap | Why it matters |
|---|---|
| No `Day.bbox`, no `Trip.bbox` | Cannot fit the map to a day or to the whole trip |
| No summits/POI along tracks | "Summit summited" is an explicit requirement; `enrich/peaks.py` was designed in E3 and never built |
| No day titles | The timeline needs headings; 0 of 27 days have one |
| Drive geometry is sparse | 100 of 219 events carry geometry; road legs come only from 2-hourly breadcrumbs |
| No trip-level route | The overall view needs an assembled, simplified polyline |

## Remaining milestones

| | Scope | Why here |
|---|---|---|
| **M5** | **Backend for the map.** `Day.bbox`/`Trip.bbox`, `enrich/peaks.py` (summits, passes, lakes along a track), day titles from the dominant event, assembled trip route. Schema bump + migration. | Cheap, testable without a UI, and everything after it depends on it |
| **M6** | **Frontend foundation.** Vite + React + TS + Tailwind v4, Zustand + Zundo, capsule loading over HTTP, routing, the design system as real components | Nothing can be built without it |
| **M7** | **Map core (MapLibre).** Tile style, track vs drive styling, clustered photo pins, the `trip → day → activity` scope machine, fit-to-bounds. **Shared by M8 and M9.** | ADR-0006 |
| **M8** | **Capsule explorer.** Two-pane: timeline left, map right, bidirectional selection sync. Day sections with real events, not just photographs | The thing that was wrong |
| **M9** | **Activity detail.** Elevation profile on uPlot, cursor synced to the map both ways, summits and telemetry, photos placed along the track | The requirement the old design ignored entirely |
| **M10** | **Curation workspace.** Four columns, real operations, undo/redo, keyboard-first | Prototyped; now needs the map from M7 |
| **M11** | **AI suggestions.** Day titles, trip summary, place-label tiebreak for the 58 contested names, coherence checks | Small, and better once titles exist |
| **M12** | **Export.** Self-contained HTML embedding the M8 explorer | Needs the explorer to exist first |

**Curation moved after the explorer** (M10, was M5). Reason: the explorer is read-only and
therefore the cheapest way to validate the map, the scope machine and the data model. Doing
curation first would mean building editing on top of an unvalidated map.

## Deferred, deliberately

Hybrid satellite tiles · self-hosted PMTiles · Strava/Garmin OAuth · video posters via
ffmpeg · weather and golden-hour backfill · RAW · auto trip detection · Google Places
resolution · LLM photo captions.
