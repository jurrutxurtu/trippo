# Architecture

## C4 L1 — context

```
┌─────────────┐   files    ┌──────────────────────┐   HTTP/SSE   ┌──────────────┐
│ User's disk │───────────▶│  Trippo backend      │◀────────────▶│ Trippo SPA   │
│ photos·gpx  │            │  (FastAPI, local)    │              │ (React, :5173)│
│ timeline    │            └──────────┬───────────┘              └──────────────┘
└─────────────┘                       │
                                      ├──▶ Overpass / Photon / Nominatim  (geocoding)
                                      ├──▶ Google Places        (optional, API key)
                                      ├──▶ Gemini               (optional, API key)
                                      └──▶ MyTrip.capsule/      (the portable artifact)
```

Everything runs on `localhost`. No auth, no database, no cloud storage. See ADR-0001.

## C4 L2 — backend containers

```
api/        FastAPI routers, SSE progress. Thin: validate, delegate, serialise.
domain/     PURE. Trip·Day·Event·Track·MediaAsset, invariants, stats. No I/O.
ingest/     timeline/ (sniffer + 3 adapters) · gpx/ · media/
observe/    NormalizedObservation, PositionIndex (interpolation, nearest fix)
draft/      cluster · dedup · plausibility · overnight · transport · gaps
            · gpx_precedence · prune · builder (orchestrator)
enrich/     geocoder cascade + persistent cache · sun times
ai/         LlmProvider port · GeminiProvider · prompts · output validators
capsule/    read · write · validate · migrate · export_html
ports/      Storage · Geocoder · Llm   (protocols)
config/     heuristics.py — every tunable constant, nowhere else
```

### The layering rule

```
api  →  draft · ingest · enrich · ai · capsule  →  domain
```

`domain/` imports nothing from the outer layers and performs no I/O. This is what makes the draft
pipeline unit-testable without fixtures on disk, and what will let the same code run server-side if
the hosted viewer ever materialises.

Enforced by `tests/unit/test_layering.py`, which walks the AST of `domain/` and fails on forbidden
imports.

## The central abstraction: `NormalizedObservation`

Every source is reduced to a stream of observations before any reasoning happens:

```python
NormalizedObservation(
    t: datetime,            # timezone-aware, always
    lat: float | None,      # None is legal and common (a photo with no GPS)
    lon: float | None,
    kind: ObservationKind,  # visit | move | breadcrumb | media | trackpoint
    source_id: str,
    ...
)
```

This is why the draft builder is **source-agnostic**: it never asks "was there a timeline?". It
asks "what do I know about 09:00–17:00 on this day?". Three sources, each of which is the *sole*
evidence for at least one day of the reference trip, proved this design necessary rather than
elegant. See `ingestion.md`.

## Two-layer timeline model

Google's export mixes two incompatible things in one array:

- **Layer 1 (semantic)** — `visit` and `activity` segments. These become *candidate events*.
- **Layer 2 (breadcrumbs)** — `timelinePath` segments on rigid 2-hour boundaries that **overlap**
  layer 1. These feed the `PositionIndex` **only** and never create events.

Treating them as peers produces duplicate legs for every drive. ADR-0009.

## Ports and adapters

| Port | POC adapter | Future |
|---|---|---|
| `Storage` | `LocalFsStorage` | `S3Storage` |
| `Geocoder` | `CascadeGeocoder` (Overpass→Photon→Nominatim→Places) | — |
| `Llm` | `GeminiProvider`, `NullProvider` | any |

`LocalFsStorage` is the only module allowed to resolve absolute paths. `capsule.json` never
contains one. ADR-0001.

## Frontend

React + TypeScript + Vite. Zustand + Immer for the draft, Zundo for undo/redo (tracks excluded from
the temporal slice — they are megabytes). TanStack Query for server state, TanStack Virtual for the
media grid. MapLibre GL + supercluster for maps, uPlot for elevation. shadcn/ui + Tailwind.

Derived values (stats, per-day totals) are **selectors**, never stored state.

## Data flow for a curation edit

```
UI action → command → zustand/immer patch → optimistic render
                    → POST /trips/{id}/ops  → domain.apply_op() → invariants.check()
                    → 200 + authoritative diff  (or 409 + rollback)
```

Invariants are checked server-side on every operation. The most important one: **every media item
is owned by exactly one active event or by the unassigned pool — never both, never neither.**

## Media and asset serving

Capsules store media derivatives under `media/thumb/` (256px WebP) and `media/web/` (1600px WebP), plus track geometries under `tracks/`.

- The backend serves these via static endpoints:
  - `/media/{subpath}`: serves from the active capsule, with fallback to any capsule in the workspace (so covers resolve even if no capsule is currently open).
  - `/api/capsules/{id}/media/{subpath}`: deterministically serves derivative media for a specific capsule (used by the Library).
  - `/tracks/{subpath}`: serves track GeoJSON/elevation geometries.
- Paths are validated with `is_relative_to` to prevent path traversal.
- Routes are registered before the SPA catch-all route to prevent shadowing.

