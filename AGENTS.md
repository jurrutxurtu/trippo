# AGENTS.md — Trippo

> **Read this first. Then read `docs/technical/architecture.md` and every non-superseded ADR in
> `docs/decisions/` before you plan any change.**

## 1. What Trippo is

A **local-first travel memory studio**. It ingests raw Google Maps Timeline exports, GPX tracks and
local photo/video folders; cleans and fuses them deterministically; guides the user through an
interactive **curation** phase; and emits a portable **trip capsule** (maps, day-by-day itinerary,
organised media, light narrative suggestions).

**The defining constraint: zero hallucination.** If the data does not support a claim, the app says
"unaccounted" and asks the user. It never invents a place, a route or a day.

### Hard non-goals (do not add without a new ADR)

- No authentication, no users table, no multi-tenancy, no server-side database.
- No cloud upload of original media.
- No long AI-generated prose. AI output is ~1 line per day plus suggestions.
- No auto trip detection across history.

## 2. Architecture in one picture

```
Timeline? · GPX* · Photos/Videos* · Manual        (every source optional)
        ↓ ingest/  sniffers + adapters
  NormalizedObservation[]  ── PositionIndex  (L2 breadcrumbs)
        ↓ draft/   cluster → dedup → plausibility → overnight
                   → transport → gaps → gpx precedence → prune
        ↓ enrich/  Overpass → Photon → Nominatim → [Google Places]   (cached)
        ↓ HUMAN CURATION  (frontend)
        ↓ ai/      optional, low-volume suggestions
  capsule/  →  MyTrip.capsule/   save · reopen · export HTML
```

### Layering rule (enforced by review, and by `tests/unit/test_layering.py`)

```
api  →  draft · ingest · enrich · ai · capsule  →  domain
```

- `domain/` is **pure**: no I/O, no `pathlib`, no `httpx`, no `open()`. Dataclasses/Pydantic models
  and pure functions only.
- All filesystem access goes through the `Storage` port (`ports/storage.py`). Never use `pathlib`
  outside `ingest/`, `capsule/` and the adapters that implement a port.
- All network access goes through a port (`Geocoder`, `Llm`). Never call `httpx` from `draft/`.

## 3. Workflow rules — mandatory

1. **Conventional commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
2. **Update docs in the same commit as the code.** If a change genuinely needs no doc update, put
   `docs: n/a` in the commit body. Silence is not acceptable.
3. **Any non-obvious technical choice gets an ADR** in `docs/decisions/`. ADRs are **immutable** —
   never edit a decided ADR; write a new one and set `Superseded-by:` on the old one.
4. **Never hand-edit `docs/technical/data-model.md`.** It is generated. Run `just gen-docs`.
5. **All heuristic constants live in `backend/trippo/config/heuristics.py`** and are documented in
   `docs/technical/heuristics-tunables.md`. No magic numbers anywhere else.
6. **Capsule model change ⇒** bump `SCHEMA_VERSION`, add a migration in `capsule/migrate.py`, and
   add an entry to `docs/technical/capsule-format.md`.
7. **Run `just check` before declaring work done.** It runs ruff, mypy, unit tests, golden snapshot
   tests and the schema-drift check.

## 4. Golden fixtures

`fixtures/golden/ireland-2023/` holds a redacted slice of a real trip plus a **snapshot of the
expected draft itinerary**. Any change to ingestion or heuristics will produce a snapshot diff.

- A diff is a **bug** unless you can explain it. Explain it in the commit body.
- To accept an intended behaviour change: `just snapshot-update`, then describe the diff in the
  commit and, if the behaviour is user-visible, in `docs/technical/heuristics-tunables.md`.

The Ireland 2023 fixture encodes hard-won truths about real data. Do not weaken its assertions to
make a test pass. See `docs/technical/ingestion.md` §"Known real-world pathologies".

## 5. Degraded operation is a feature, not an edge case

The app must work when things are missing. Never hard-fail ingestion.

| Missing | Behaviour |
|---|---|
| `ffmpeg` | No video posters. Report it. Continue. |
| `exiftool` | Pillow-only EXIF. Report it. Continue. |
| Photo GPS | Infer position from timeline/GPX; else `locationSource='none'`. |
| Timeline | Build from photos + GPX alone. |
| Network | Events keep coordinate-based labels; geocoding retried later. |
| LLM API key | All AI features hidden. App fully usable. |

Every degradation must appear in the **Ingestion Report**, never silently.

## 6. Commands

```bash
just setup            # create venv, install deps
just dev              # backend + frontend
just check            # ruff + mypy + pytest + golden + schema-drift
just gen-docs         # regenerate data-model.md + capsule.schema.json
just snapshot-update  # accept golden snapshot changes (explain in commit!)
```

## 7. Where to start reading

| Question | File |
|---|---|
| Why does this exist? | `docs/product/vision.md` |
| What is done, what is next? | `docs/product/roadmap.md` |
| How do I run the whole thing? | `docs/product/testing-walkthrough.md` |
| What must it do? | `docs/product/functional-spec.md` |
| How is it built? | `docs/technical/architecture.md` |
| What is a capsule? | `docs/technical/capsule-format.md` |
| Why is this number 130? | `docs/technical/heuristics-tunables.md` |
| Why was X chosen? | `docs/decisions/` |
| What breaks on real data? | `docs/technical/ingestion.md` |
