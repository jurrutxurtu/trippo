# Testing Trippo end to end

A walkthrough of the whole process on real data, and what to look at while you do it.

## 0. Keys

Put them in `backend/.env` (gitignored, loaded automatically by every command):

```ini
MAPTILER_KEY=...          # optional -- without it the map falls back to OSM raster
GEMINI_API_KEY=...        # optional -- without it AI suggestions are hidden entirely
GOOGLE_PLACES_API_KEY=    # optional, off by default, PAID -- see ADR-0010
```

Every command prints what it found:

```
[env]      maptiler on · gemini off · google_places off
```

An environment variable always beats the file, so `GEMINI_API_KEY=x just serve ...` works
for a one-off.

## 1. Build a capsule

There is **no UI for creating a trip yet** — that is CLI-only. Every source is optional; a
folder of photographs is enough.

```bash
cd backend
.venv/Scripts/python.exe -m trippo.cli build \
  --timeline  "C:/.../Timeline_2023.json" \
  --gpx       "C:/.../ireland_gpx_activities" \
  --media     "C:/.../Ireland" \
  --from 2023-09-20 --to 2023-10-16 \
  --title "Ireland 2023" \
  --enrich --derivatives \
  --out "C:/.../Ireland.capsule"
```

`--enrich` resolves place names and summits (needs network; cached afterwards).
`--derivatives` writes thumbnails and web-sized copies (slow the first time, ~7 minutes for
1,100 photographs; instant after that).

### What to look at in the output

| Line | What it tells you |
|---|---|
| `format=on_device records=4731 in-window=2325` | the timeline was recognised and filtered |
| `0 of 1224 media files contain GPS` | a real degradation, stated plainly |
| `phantom stops absorbed` | Google's mid-ocean "visit" was caught, not turned into a hotel |
| `unaccounted gaps` | holes Trippo refuses to guess at — should be 3, not 31 |
| `146 named, 19 unresolved` | geocoding; unresolved is honest, not a failure |
| `Slieve Binnian 745.9 m` | summits found along the tracks |
| `[thumbs] ... 0 failed` | derivatives |

## 2. Review before you open it

```bash
just review ./Ireland.capsule
```

Prints what is worth fixing, worst first. `!` blocks, `~` is worth a look, `-` is
informational. On the reference trip: 3 blocking (the real gaps), 4 warnings.

## 3. Explore and curate

```bash
just serve ./Ireland.capsule     # terminal 1
just web                         # terminal 2 -> http://localhost:5173
```

Timeline on the left, map on the right, one shared selection.

### Reading

1. **Trip scope.** Whole route, day markers, clustered photographs. Ferries and gaps are
   dashed — that is deliberate, and means "we do not know the route".
2. **Click a day.** The map fits it; that day's legs light up, the rest fade to context.
3. **Click an activity** (rows with `12.0 km +645 m view →`). The map fits the track, marks
   the summits, and the elevation profile appears. Hover the chart: a marker runs along the
   route. One shared cursor, not two.
4. **Click any photograph** for the full-size viewer; arrow keys move, `Esc` closes.
5. `Esc` also walks back up: activity → day → trip.

### Editing

Press **Edit** in the toolbar.

- **Resolve a gap** — Day 2 has the 39-hour hole. Click *It was a ferry*. The 59
  photographs stay attached, and the event keeps its time range.
- **Rename** anything. It turns green: *"Your name — place lookup will not overwrite it."*
- **Change a type**, add a note, hide or delete an event. Deleting returns its photographs
  to the pool; it never destroys one.
- **Undo / redo** (`Ctrl+Z`, `Ctrl+Shift+Z`). Every operation is validated server-side; an
  invalid one is rejected and changes nothing.
- **Save** writes back to the capsule directory.
- **Review tab** (trip scope) lists everything outstanding; clicking a finding jumps to it.

## 4. Export

```bash
just export ./Ireland.capsule ./Ireland-share
```

A self-contained `index.html` plus `media/`. Opens from disk with no server. Originals
never travel — only the derivatives.

---

## What to be sceptical about

These are the places the system is most likely to be wrong, and worth checking against your
own memory of the trip:

1. **Contested place names** — 54 of them. The geocoder had two close candidates and picked
   one. Dense city centres (Belfast) are the weakest case; OSM there is mostly war
   memorials, so that is what you get.
2. **`36 places still labelled by coordinates`** — Overpass and Nominatim found nothing.
   Honest, but they need naming by hand.
3. **Double overnights** on Days 5 and 19 — one of each is probably a long daytime stop.
4. **Photo positions.** All 1,097 have `location_source: inferred`, because the export
   stripped GPS. They are interpolated from the timeline and tracks; 79 are unlocatable and
   correctly have no pin.
5. **Day 4's hike owns zero photographs.** Correct — 23 September has none at all.
6. **Drive geometry is sparse.** Road legs come from 2-hourly breadcrumbs, so they cut
   corners. Only GPX tracks are precise.

## If an import seems to stop

The progress stream is for liveness only; it is never the source of truth. The client polls
`GET /api/jobs/{id}` to the end regardless, so a dropped connection no longer looks like a
failure. If you do see "The import stopped", the message under it is the real reason from
the server, and the stage list shows how far it got.

Long silences during **Place names** are normal: one Overpass batch can stall for a minute,
and public mirrors throttle. The stream sends a heartbeat every ten seconds so the
connection stays open through it.

To check on a job by hand:

`powershell
Invoke-RestMethod http://127.0.0.1:8787/api/jobs/<jobId>
`

## Known gaps

- The review panel is a flat list; it should group by day.
- Edit mode expands every event inline rather than only the selected one.
- No drag-and-drop between the photo pool and events; selection plus a button instead.
- Google Places is implemented but off � see ADR-0010 for the cost and how to enable it.
