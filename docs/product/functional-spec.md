# Functional specification

Status legend: **[POC]** built in M0–M8 · **[LATER]** designed for, not built.

## 1. Sources

| Source | Required | Formats |
|---|---|---|
| Google Timeline | no | on-device `semanticSegments` **[POC]**; legacy `timelineObjects`, `Records.json` **[POC, degraded]** |
| GPS tracks | no | GPX 1.0/1.1 incl. Garmin `TrackPointExtension` **[POC]**; FIT, Strava/Garmin OAuth **[LATER]** |
| Media | no | JPEG/PNG/HEIC **[POC]**; MP4/MOV metadata + poster **[POC]**; RAW **[LATER]** |
| Manual | — | user-created trips, days and events **[POC]** |

At least one source is required. **Any subset must work.**

## 2. Canonical event types

`drive` · `stop` · `visit` · `overnight` · `hike` · `walk` · `bike` · `flight` · `ferry` ·
`unknown` (unaccounted gap)

Every event carries: id, day, time range, timezone, status (`active`/`suppressed`), place,
geometry, media ids, track ids, provenance, user note, and a **type-specific `detail`** object.
Changing an event's type replaces `detail` and preserves id, time, media and tracks.

## 3. Ingestion **[POC]**

- Format sniffing per file; unknown files reported, never silently dropped.
- Date-window filtering; the trip window may be proposed from media EXIF.
- **Ingestion Report**: per-source format + confidence, per-day coverage matrix
  (timeline/photos/GPX/blind), counts of skipped files with reasons, and active degradations
  (e.g. "0 of 1,097 photos contain GPS — your export may have stripped location data").

## 4. Draft building **[POC]**

Deterministic pipeline, in order: cluster → dedup → plausibility gate → overnight → transport
classification → gap detection → GPX precedence → prune.

**Golden Rule.** An event is kept if it has media, or a track, or is an overnight, or is
user-pinned, or lasts ≥ 20 min, or spans ≥ 5 km, or resolves to a named POI. Everything else is
`suppressed` with a reason and remains visible behind a "N hidden" toggle. **Nothing is deleted.**

## 5. Enrichment **[POC]**

Google's on-device export contains **no place names**, so reverse geocoding is core, not optional.
Cascade: Overpass (named POI) → Photon → Nominatim → optional Google Places (API key). Results are
cached persistently. See `docs/technical/enrichment.md`.

## 6. Curation **[M5]**

- Day rail with per-day **coverage strip**, exclude-day toggle, automatic renumbering.
- Event list: reorder, change type, add, delete, suppress/unsuppress, edit title/note.
- Flight and ferry detail forms (airports, flight code, layovers; ports, operator).
- Media: move between events, multi-select, **"Find nearby photos"** (±15 min … ±2 h).
- **Unassigned pool** for media and tracks. Deleting an event or excluding a day returns its
  media and tracks here — never deletes them.
- Undo/redo across all curation operations.
- Keyboard-first: `j`/`k` navigate, `1`–`9` set type, `x` suppress, `p` photo pool.

## 7. Maps **[M6]**

Interactive trip and day views. Coarse drives and high-resolution tracks styled distinctly, with
trailhead markers and clustered media pins. Street style **[POC]**; hybrid satellite with labels
**[LATER]**. Elevation profile, synced bidirectionally with the map cursor, **rendered only for
activity events that have a track with elevation**.

## 8. AI **[M7]**

Optional. Disabled entirely without an API key. Day titles and one-line subtitles (3 options), trip
title and 2–3 sentence summary, place-label disambiguation, note polish, photo captions (opt-in),
and coherence checks (mostly deterministic). **No long-form narrative.**

## 9. Capsule and export **[M8]**

Directory-as-document, versioned and migratable. Round-trips losslessly. Export as self-contained
HTML plus a `media/` folder; video is referenced but excluded from export in the POC.

## 10. Statistics — scoping rule

**Trip stats** carry no elevation: days, countries, places, overnight stays, media counts, distance
by transport mode, coverage summary.
**Activity stats** live on track-bearing events only: distance, ascent, descent, max/min elevation,
moving time, average/max heart rate.
