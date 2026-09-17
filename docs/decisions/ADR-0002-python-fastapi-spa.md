# ADR-0002 — Python + FastAPI backend, browser SPA frontend

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

Three deployment shapes were considered:

| | Pure browser PWA | Tauri desktop | Local backend + browser |
|---|---|---|---|
| 8 GB media | OPFS/memory ceilings | native | native |
| HEIC / RAW | painful WASM | native | native |
| Large JSON | worker streaming | trivial | trivial |
| POC velocity | medium | slow (Rust) | **fastest** |
| Distribution | zero install | installer | dev-friendly |

Backend language was a second choice: Python (geo/EXIF/data ecosystem) vs Node (one language,
shared Zod schemas).

## Decision

**Local Python backend on `localhost`, plus a browser SPA.** Python 3.12, FastAPI, Pydantic v2,
managed with `uv`.

## Rationale

- Real threads and native libraries for EXIF, image decoding and geometry — no browser ceilings.
- The Python geospatial ecosystem is materially better: `gpxpy`, `Pillow`/`pillow-heif`, `shapely`,
  `timezonefinder`.
- The frontend is a plain SPA talking HTTP, so it can later be hosted inside Tauri as a sidecar, or
  served by a hosted backend, without frontend changes.
- Pydantic v2 generates JSON Schema, which generates both the TypeScript types and
  `docs/technical/data-model.md` — one source of truth, so the schema-sharing advantage of Node
  largely evaporates.

## Consequences

- Two languages and two toolchains.
- Type safety across the boundary depends on schema generation being run — enforced by the
  schema-drift check in `just check`.
- `ffmpeg` and `exiftool` are optional external binaries; absence degrades gracefully (`AGENTS.md`
  §5).
