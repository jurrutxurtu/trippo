# ADR-0004 — GPX has absolute precedence over timeline data

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

A hike can exist twice: as a coarse Google `activitySegment` and as a 3,000-point Garmin GPX. Naive
merging renders two overlapping legs and double-counts distance.

An earlier design scored temporal IoU and *asked the user* which to keep when the match was
ambiguous. The user's instruction was unambiguous: the GPX is always more precise and always wins.

## Decision

**For any time interval covered by a GPX track, the track is the geometry and the telemetry.**

- Overlapping timeline segments are **masked**: retained in `sources` with
  `provenance.superseded`, excluded from rendering and from all statistics.
- A track overlapping a timeline segment by ≥ `GPX_ABSORB_OVERLAP` (50%) is absorbed into that
  event; otherwise it becomes a standalone activity event.
- Title comes from `<trk><name>`, activity type from `<trk><type>`.
- Day assignment uses the **local date of the track's start**.

Manual attach and detach in curation remain available and override everything.

## Consequences

- Removes an entire confidence-negotiation UI and roughly 300 lines of scoring logic.
- A GPX with a wrong clock will mask correct timeline data. Mitigated by manual detach; a
  per-track time-shift control is `[LATER]`.
- Track identity derives from `<trk><name>` plus a start-time hash, never the filename, because
  exported filenames are inconsistent (pathology P8).
