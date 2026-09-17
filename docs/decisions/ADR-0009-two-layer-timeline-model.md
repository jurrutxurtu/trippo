# ADR-0009 — Two-layer model for Google Timeline segments

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

`semanticSegments` in the on-device export is not a partition of time. Inspection of the reference
export found three distinct segment shapes in one array — 1,775 `timelinePath`, 1,586 `visit`,
1,370 `activity` — and they **overlap**:

```
visit          21:44 → 00:21   (Dublin)
timelinePath   22:00 → 00:00   ← rigid 2-hour boundaries, overlaps the visit
timelinePath   00:00 → 02:00
activity       00:11 → 00:17   WALKING, 502 m
```

Treating these as peers produces a duplicate leg for every drive and a duplicate stop for every
visit. Separately, `visit` entries nest via `hierarchyLevel`, so the same time range can appear
twice at different coordinates (pathology P4).

## Decision

Model the export as **two layers**:

- **Layer 1 — semantic.** `visit` and `activity` become *candidate events*. Deduplicated by
  overlapping time range, keeping the most specific `hierarchyLevel`.
- **Layer 2 — breadcrumbs.** `timelinePath` feeds the `PositionIndex` **only**. It never creates an
  event.

## Consequences

- No duplicate legs.
- Layer 2 remains essential: the only evidence that the return ferry crossed the Atlantic is a
  single `timelinePath` point at 48.716, −5.272. It supplies geometry for crossings and positions
  for photos that have no GPS.
- `startTimeTimezoneUtcOffsetMinutes` on Layer 1 gives exact local time with no `timezonefinder`
  lookup, and an offset change between consecutive segments is used as an international-crossing
  signal (pathology P10).
- Google's `distanceMeters` and activity `type` are **hints only**; geometry and distance are always
  recomputed (pathology P2).
