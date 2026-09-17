# ADR-0007 — Unaccounted gaps are surfaced, never guessed

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

The reference trip contains a **47-hour hole**: the last Spanish fix on 09-21 evening, then nothing
until a GPX track starts at Glendalough on 09-23 10:26. A ferry crossing and a drive happened in
between, and no source records either.

Two options were considered:

- **(a)** Emit an explicit "unknown" card awaiting user input.
- **(b)** Emit a low-confidence guess — *"probably a ferry: 1,600 km, sea route, timezone change"* —
  rendered greyed-out and clearly marked.

Option (b) is nicer UX. The user chose (a), for zero hallucination.

## Decision

When consecutive known positions are separated by more than `GAP_MIN_HOURS` (3 h) **or**
`GAP_MIN_KM` (100 km) with no observations in between, emit a first-class event with
`type = 'unknown'`.

- It is rendered prominently, not quietly.
- It states the facts only: elapsed time, endpoints, displacement.
- It offers one-click conversion to ferry, flight or drive.
- Media falling inside the gap attach to it automatically, with `location_source = 'none'` when no
  position can be inferred.
- The pipeline **never** stitches a drive across a void.

`detail.candidateTypes` may list plausible types for the conversion buttons, but the event is not
classified and no distance or route is asserted.

## Consequences

- Days covered only by a gap look sparse until the user acts. This is correct: the data *is* sparse,
  and pretending otherwise is the failure mode the product exists to prevent.
- Related: reconstructed crossings carry `geometryReliability ∈ {measured, sparse, assumed}` so a
  route drawn from two breadcrumbs never renders as a confident line.
