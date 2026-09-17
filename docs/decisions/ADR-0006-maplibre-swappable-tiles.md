# ADR-0006 — MapLibre GL with swappable tile styles

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

Requirements: a Google-Maps-like street map, a hybrid satellite view with readable labels,
high-resolution GPX polylines, thousands of photo pins, and **no costly map API billing**.

## Decision

**MapLibre GL JS.** Tile sources are configuration, not code, behind a `MapStyle` registry.

POC: MapTiler or Stadia free tier for the street style (fastest to a working map).
`[LATER]`: self-hosted **Protomaps PMTiles** regional extracts — a single file, zero per-request
cost, works offline and unlocks fully offline capsules.

Hybrid satellite `[LATER]`: Esri World Imagery raster underneath a MapLibre vector style with all
fills suppressed and only labels, boundaries and faint road casings retained. That layering is what
produces a genuine Google-Hybrid look while remaining free and restylable.

## Rationale

- Vector tiles allow restyling labels and roads — required for the hybrid view; Leaflet cannot do
  this without a plugin stack.
- GPU rendering handles 10k+ point polylines and clustered pins that would stall Leaflet's DOM
  markers.
- `raster-dem` gives terrain and hillshade for alpine trips at no extra cost.
- PMTiles keeps the door open to genuinely zero-cost hosting and offline exports.

## Consequences

- A steeper API than Leaflet, and style JSON to maintain.
- A MapTiler key is needed for the POC; it is read from `.env` and never committed.
- Photo pins must use a GeoJSON `symbol` layer with `supercluster`, never DOM markers.
