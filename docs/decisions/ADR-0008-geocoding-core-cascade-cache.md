# ADR-0008 — Geocoding is core, with a cascade and a persistent cache

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

The Google on-device export contains **no place names** — only a `placeId` and coordinates, with
`semanticType: UNKNOWN` for 135 of 145 visits in the reference trip. Without reverse geocoding the
curation screen is a list of latitudes, and the product is unusable.

This reclassifies geocoding from "enrichment" to core functionality.

## Decision

A cascade behind a `Geocoder` port: **Overpass → Photon → Nominatim → optional Google Places**,
with a persistent SQLite cache at `~/.trippo/geocode-cache.sqlite` keyed on
`(round(lat,4), round(lon,4), kind, radius)`.

Overpass is tried first because for a travel app *"what is here"* (peak, castle, beach, car park)
beats a postal address. Google Places is wired but **off by default**; it resolves `placeId`
exactly, and costs money.

When the top two candidates score closely, the **LLM breaks the tie** from the supplied candidate
list. It may choose or compose, never invent; enforced by `ai/validators.py`. With no LLM
configured, deterministic ranking wins at reduced confidence.

## Consequences

- A first pass over ~145 visits takes 2–3 minutes, bounded by Nominatim's 1 req/s. It runs in the
  background with SSE progress; events show coordinate labels until names arrive.
- The cache makes re-runs instant and keeps golden tests offline.
- Public Overpass and Photon instances are best-effort; failures fall through the cascade and are
  reported, never fatal.
- `placeId` is always persisted even when unused, preserving the option of exact resolution later.
