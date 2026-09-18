# ADR-0010 — Google Places: implemented, disabled, and why

- **Status:** Accepted
- **Date:** 2026-09-18

## Context

The Google on-device Timeline export contains **no place names** — but it does contain
Google's own **`placeId`** for every visit. On the reference trip, 69 of 219 active events
carry one.

That is a fundamentally better signal than anything free:

| Source | Answer at Glendalough (53.012, −6.329) |
|---|---|
| Nominatim | `R757` — a road number |
| Overpass | 15 candidates; ranking picks one |
| **Places, by `placeId`** | the exact place, no search, no radius, no ambiguity |

ADR-0008 said Places was "wired but off by default". It was not wired at all — only the
environment variable name existed. Discovered when the user added a key and nothing
happened.

## Decision

**Implement it, place it first in the cascade, and leave it off unless a key is set.**

- `enrich/places.py` resolves a `placeId` through the Places API v1 with a narrow field
  mask (`displayName,formattedAddress,location,primaryType,types`) — Places bills per
  field, so asking for less costs less.
- It runs **before** Overpass and Nominatim, and **only** for events that already carry a
  `placeId`. Everything else falls through to the free cascade unchanged.
- Google place types are mapped onto the same `key=value` vocabulary the ranker uses, so a
  Places result competes on equal terms rather than bypassing the scoring.
- Results are cached like any other provider, keyed on the id. A trip is paid for once.
- Absent `GOOGLE_PLACES_API_KEY`, `resolver_from_env()` returns `None` and nothing changes.

## Cost, measured

On the reference trip: **69 lookups, roughly $0.35**, cached permanently. Those 69 include
7 events that are currently unnamed and 22 whose name was a close call.

## Consequences

- The best available naming source is one environment variable away.
- It is **not enabled by default**, because a local-first tool should not spend the user's
  money without being asked. The UI reports `placesAvailable` so it can say so plainly.
- The implementation is exercised only by a live smoke test, not the suite: mocking a paid
  API proves nothing about the paid API. It resolved a real `placeId` from the reference
  export correctly on 2026-09-18.
- **When picking this up again:** the obvious next step is resolving `placeId` for the
  *contested* events specifically — the 22 where ranking was a coin toss and an exact
  answer is worth the most. That would be a `--places-contested-only` flag rather than a
  blanket pass, and would cost around $0.11 per trip.
