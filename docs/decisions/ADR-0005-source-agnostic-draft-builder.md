# ADR-0005 — The draft builder is source-agnostic

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

The obvious design makes the Google Timeline the backbone and treats photos and GPX as decoration.
Analysis of the reference trip destroyed that assumption:

| Date | Timeline | Photos | GPX | Sole evidence |
|---|---|---|---|---|
| 09-22 | **none** | 42 | none | photos |
| 09-23 | 2 rows, 20:40+ | **none** | Glendalough hike | **GPX** |
| 10-14 | 1 mid-Atlantic breadcrumb | 9 | none | timeline breadcrumbs |

**No single source reconstructs the trip.** Separately, the user requires trips that can be built
with no timeline export at all.

## Decision

Every source is reduced to `NormalizedObservation(t, lat?, lon?, kind, source_id)` before any
reasoning. The draft builder consumes observations and **never asks which source produced them**.

A timeline export is one optional source among four (timeline, GPX, media, manual).

## Consequences

- Photo-only and GPX-only trips work by construction, not as a special case.
- `lat`/`lon` must be **optional** throughout the pipeline: 1,097 of 1,097 reference photos had no
  GPS (pathology P6). Photo-only clustering therefore degrades to time-only, producing day
  structure and event candidates but no coordinates — an honest limitation, surfaced in the UI.
- Inferred geolocation (interpolating a photo's position from breadcrumbs or tracks) is promoted
  from a nice-to-have to core functionality.
- Source-specific quirks must be handled in adapters, never leaked into `draft/`.
