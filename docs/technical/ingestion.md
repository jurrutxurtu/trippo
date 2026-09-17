# Ingestion

## Format sniffing

| Source | Detection | Adapter |
|---|---|---|
| Timeline, on-device (2024+) | top-level `semanticSegments` | `ingest/timeline/on_device.py` |
| Timeline, legacy semantic | top-level `timelineObjects` | `ingest/timeline/semantic_lh.py` |
| Timeline, raw records | top-level `locations` | `ingest/timeline/records.py` |
| GPX | XML root `gpx` | `ingest/gpx/parse.py` |
| Media | extension + magic bytes | `ingest/media/scan.py` |

Unknown files are reported in the Ingestion Report with a reason. Never silently skipped.

## Coordinate parsing

The on-device format stores coordinates as **degree-suffixed strings**, not numbers:

```json
"latLng": "43.248688°, -2.8871506°"
```

`parse_lat_lng()` strips everything that is not `[0-9.,-]`. Note the degree sign may arrive
mojibaked depending on the encoding of the export; the parser is deliberately tolerant.

## Media timestamps — the cascade

In priority order, recording the winner in `MediaAsset.time_source`:

1. `DateTimeOriginal` + `OffsetTimeOriginal` → exact instant. **`exif`**
2. `DateTimeOriginal` without offset → naive local time, resolved against the day's inferred
   timezone. **`exif_no_offset`**
3. Filename pattern, e.g. Pixel `PXL_YYYYMMDD_HHMMSSmmm`. **`filename`**
4. Filesystem mtime. **`mtime`** (weak; flagged in the report)

Filenames are normalised before hashing: the Google Photos export prefix `original_<uuid>_` and the
`~N` duplicate suffix are stripped. Variants `.MP` (motion photo), `.NIGHT`, `.PANO` are recorded as
`MediaAsset.variant` and used as hero-selection signals. Motion photos are treated as plain JPEG.

## Inferred geolocation — P0, not a bonus

Photos frequently have **no GPS at all** (see below). When `MediaAsset.lat` is absent, position is
interpolated from the `PositionIndex` (timeline breadcrumbs and GPX trackpoints) at the photo's
timestamp, and `location_source` is set to `inferred`. If no source covers that instant,
`location_source` is `none` and the photo remains locatable only by the user.

---

## Known real-world pathologies

> Every item below was observed in the reference dataset (Ireland, Sept–Oct 2023: 25 days, a
> Bilbao↔Rosslare ferry, 7 Garmin tracks, 1,097 photos, 127 videos). The golden fixture asserts the
> correct handling of each. **Do not weaken these assertions.**

### P1 — Phantom stationary visits

Google emitted a `visit` of **8 h 36 min anchored at Rosslare Harbour** while the phone was
actually mid-Irish-Sea. It spans local 02:00–05:00, so a naive overnight rule reports
*"Overnight stay, Rosslare Harbour"*. This is exactly the failure the product exists to prevent.

**Mitigation — plausibility gate** (`draft/plausibility.py`), applied *before* overnight detection:
a visit implying more than `MAX_GROUND_SPEED_KMH` to reach the next known fix was not stationary.
It is absorbed into the adjacent transit event as a phantom anchor.

### P2 — Untrustworthy activity telemetry

The same crossing was labelled `IN_FERRY` with `distanceMeters: 24191` (24 km for a ~900 km
crossing) and an end point that loops back toward the departure port. Google's `type` and
`distanceMeters` are treated as **hints**. Geometry and distance are always recomputed.

### P3 — Total data voids

`2023-09-22` contains **zero timeline segments**; `2023-09-23` has two, both after 20:40. The
outbound ferry and the following morning are invisible. Silently stitching a drive across the hole
would be a hallucination by omission.

**Mitigation — `UnaccountedGap`** (`draft/gaps.py`): a hole exceeding `GAP_MIN_HOURS` or
`GAP_MIN_KM` with no observations becomes a visible `unknown` event awaiting user input. Media
inside the hole attach to it.

### P4 — Duplicate visits at identical timestamps

`10-15 07:20→08:45` appeared **twice**, at different coordinates. This is Google's `hierarchyLevel`
nesting (a venue inside a district). `draft/dedup.py` groups by overlapping time range, keeps the
most specific level, and retains the rest as `provenance.absorbed`.

### P5 — Visits spanning multiple calendar days

A single visit ran `10-15 08:45 → 10-16 18:39` (34 h). Assigned to its **start** day with
`continues_to_next_day = True`. Overnights spanning midnight are the normal case, not an error.

### P6 — Photos with no GPS whatsoever

**0 of 1,097 photos** carried a GPS IFD (`0x8825`), while `OffsetTimeOriginal` was present
throughout. Location services were off, or — more likely — the Google Photos export stripped
location. Consequences:

- Photo-only clustering degrades to **time-only**; it yields day structure and event candidates but
  no coordinates and no place names.
- Inferred geolocation becomes the only way most photos acquire a position.
- The Ingestion Report must surface this explicitly, because it is user-actionable: re-exporting
  with location enabled transforms the result.

### P7 — Each source is the sole evidence for some day

| Date | Timeline | Photos | GPX | Only evidence |
|---|---|---|---|---|
| 09-22 | none | 42 | none | **photos** (time only) |
| 09-23 | 2 rows, evening | none | Glendalough hike | **GPX** |
| 10-14 | 1 mid-Atlantic breadcrumb | 9 | none | **timeline L2** |

No single source reconstructs this trip. This is why the draft builder is source-agnostic.

### P8 — Track filenames are not identifiers

Six files were named `activity_<garminId>.gpx`; one was `Activity1.gpx`. Track identity is derived
from `<trk><name>` plus a hash of the start time, never from the filename.

### P9 — Adjacent tracks are one outing

Two Kerry tracks on 10-08 ran `18:02–19:16` and `19:17–20:10` — a single walk split by a pause.
When the gap is under `TRACK_MERGE_GAP_MIN`, the app offers to merge; it never merges silently.

### P10 — Timezone offset changes mark crossings

`startTimeTimezoneUtcOffsetMinutes` flipped `+120 ↔ +60` exactly at each crossing. This is a free,
reliable international-crossing signal and is used as an input to transport classification.

### P11 — Segments overlap, so gaps must be found in *merged* coverage

A 13-hour overnight visit coexists with 2-hourly `timelinePath` breadcrumbs inside it (ADR-0009).
Comparing consecutive observations pairwise reports the space between two breadcrumbs as a gap even
though the enclosing visit covers it. The first implementation produced **31 gaps** on the reference
trip; only 3 are real.

**Mitigation:** `draft/gaps.py` merges coverage intervals before looking for holes.

### P12 — A hole with no displacement is not unaccounted travel

A phone that logs nothing for ten hours while parked outside a campsite has not hidden a journey.
Displacement, not elapsed time, is the decisive signal — `GAP_MIN_KM`, with `GAP_STATIONARY_KM` as
the floor below which a hole is treated as an unlogged stay rather than a gap.

### P13 — An isolated fix must not fragment a crossing

The return ferry produced one `timelinePath` point mid-Atlantic. That single fix split the crossing
into two adjacent `unknown` cards. A lone breadcrumb during a 19-hour void is evidence *of* the
crossing, not an explanation of it; `GAP_ISOLATED_FIX_HOURS` merges across it.

### P14 — The exit test alone does not catch phantom stays

The Rosslare phantom (P1) escaped a plausibility gate that only checked the next fix *after* the
visit: the mid-Atlantic breadcrumb precedes the visit's own end timestamp, leaving a non-positive
exit interval. A second, independent **containment test** — a fix recorded *during* the visit,
implausibly far from its anchor — is what actually catches it.

Before this fix, the reference trip passed the "no overnight at Rosslare" assertion **by luck**: the
visit began at local 02:25, just missing the 02:00 core-night window.

### P15 — Threshold filtering alone does not tame elevation noise

A bare threshold still accumulates when the noise amplitude exceeds it: alternating ±2.5 m samples
produce 5 m swings, and with a 4 m threshold a flat ride reports hundreds of metres of climbing.
`accumulate_elevation()` therefore **smooths first** (`ELEVATION_SMOOTH_WINDOW`) and thresholds
second. Either stage alone is insufficient.

### P16 — Google Photos exports strip GPS

All 1,097 reference photos carried `DateTimeOriginal` **and** `OffsetTimeOriginal` — but no GPS IFD
at all. This is user-actionable, so the Ingestion Report says so explicitly rather than quietly
degrading.
