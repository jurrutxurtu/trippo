# Vision

## The problem

Three kinds of travel data, none of which combine well:

1. **Passive location history** — Google Maps Timeline exports. Coarse, noisy, no place names.
2. **Active GPS tracks** — GPX from Garmin/Strava/Wikiloc. Precise, rich, but disconnected islands.
3. **Photos and videos** — thousands of files, gigabytes, timestamps of varying reliability.

Feeding any of this raw to an LLM fails: context overflows, days repeat, traffic jams become
destinations, and real mountain hikes lose their elevation.

## The insight

**The expensive, error-prone work is structuring the data — and that work is deterministic.**
Clustering, stop detection, timezone resolution, track fusion, photo matching: all of it is
arithmetic, not judgement. Do it in code, show the result to the human, let them correct it, and
only *then* let a language model add a light touch of prose.

Curation is not a checkpoint bolted onto an AI pipeline. Curation **is** the product.

## What Trippo is

A local-first desktop-grade web app that:

- ingests any subset of {timeline, GPX, photos, manual entry} — none is mandatory;
- produces a clean, named, day-by-day draft itinerary;
- hands the user an interactive curation workspace with maps, media and full undo;
- emits a portable, self-contained **trip capsule** that can be reopened, exported or (one day)
  hosted.

## Principles

1. **Zero hallucination.** Unexplainable data becomes a visible "unaccounted" card, never a guess.
2. **Nothing is ever lost.** Deleting an event returns its media and tracks to a pool. Pruned stops
   are suppressed, not deleted.
3. **Degraded input is normal input.** Missing GPS, missing days, absent tooling — all expected.
4. **The human decides.** The machine proposes with visible confidence and provenance.
5. **Local by default.** Gigabytes of originals never leave the machine.
6. **Scoped detail.** A city break shows no elevation charts. Telemetry belongs to activities, not
   to trips.

## Non-goals

No social features, no auth, no cloud sync, no auto trip detection, no long AI prose, no
server-side database. See `AGENTS.md` §1.

## Success test

The Ireland 2023 trip — 25 days, a blind ferry crossing, a photo-less hiking day, 1,097 photos with
no GPS, a phantom 8-hour "visit" that happened mid-ocean — reconstructs correctly and honestly,
with every gap visible rather than papered over.
