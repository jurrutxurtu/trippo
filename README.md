# Trippo

**Local-first travel memory studio.** Turns Google Timeline exports, GPX tracks and folders of
photos into a curated, portable trip capsule — without hallucinating.

> Status: **M0–M4 (backend ingestion + fusion)**. No UI yet.

## Why

Feeding raw location history and gigabytes of photos to an LLM fails: context overflows, days
repeat, traffic jams become destinations, real hikes lose their elevation. Trippo does the
structuring **deterministically**, shows you the result, lets you correct it, and only then adds a
light touch of AI.

**Zero hallucination.** When the data cannot explain a 47-hour hole, Trippo says
*"47 hours unaccounted, Bilbao → Dublin, 1,600 km"* and asks. It never invents a route.

## Quick start

```bash
just setup                      # venv + dependencies (Python 3.12 via uv)
just check                      # ruff, mypy, tests, golden snapshots, schema drift

# Build a draft itinerary from any subset of sources
python -m trippo.cli build \
  --timeline  path/to/Timeline_2023.json \
  --gpx       path/to/tracks/ \
  --media     path/to/photos/ \
  --from 2023-09-20 --to 2023-10-16 \
  --out       ./Ireland.capsule
```

Every source is optional. A trip can be built from photos alone.

### Explore it

`ash
# terminal 1 -- serve the capsule
export MAPTILER_KEY=...          # optional; falls back to OSM raster without it
just serve ./Ireland.capsule

# terminal 2 -- the studio
just web                          # http://localhost:5173
`

Timeline on the left, map on the right. Clicking a day fits the map to it; opening an
activity fits the track, marks the summits and draws the elevation profile, whose cursor
is shared with the map. Esc walks back up.

## Documentation

| | |
|---|---|
| **Working here (agents included)** | [`AGENTS.md`](AGENTS.md) |
| Why it exists | [`docs/product/vision.md`](docs/product/vision.md) |
| What it does | [`docs/product/functional-spec.md`](docs/product/functional-spec.md) |
| How it is built | [`docs/technical/architecture.md`](docs/technical/architecture.md) |
| What a capsule is | [`docs/technical/capsule-format.md`](docs/technical/capsule-format.md) |
| **What breaks on real data** | [`docs/technical/ingestion.md`](docs/technical/ingestion.md) |
| Why a constant is what it is | [`docs/technical/heuristics-tunables.md`](docs/technical/heuristics-tunables.md) |
| Why a choice was made | [`docs/decisions/`](docs/decisions/) |

## Layout

```
backend/trippo/   api · domain · ingest · observe · draft · enrich · ai · capsule · ports · config
frontend/         React + MapLibre studio            (M5+)
docs/             product · technical · decisions
fixtures/golden/  redacted real-trip fixtures + expected-output snapshots
```

## Licence

Personal project. Not for redistribution.
