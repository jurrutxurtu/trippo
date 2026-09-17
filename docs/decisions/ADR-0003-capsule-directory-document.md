# ADR-0003 — Capsule as a directory-as-document, not a database

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

A trip holds days, events, tracks (megabytes of points) and thousands of media references. Options:
SQLite per trip, a single global SQLite, or a directory of files.

## Decision

A **directory-as-document**: `MyTrip.capsule/` with `capsule.json`, `tracks/`, `media/` and
`reports/`. No database anywhere in the POC.

## Rationale

- Portable, inspectable, diffable, git-able, trivially zipped and shared.
- Matches the mental model: a trip is a thing you can move, copy and back up.
- Uploading later is a file copy, not an export routine (ADR-0001).
- Track points and media derivatives live in separate files, so the hot JSON stays small.

## Consequences

- No cross-trip queries ("every peak above 2,500 m I have climbed"). Accepted; that is a
  `[LATER]` feature and would be served by an index built *over* capsules, not by changing them.
- Concurrent writers are unsafe. Single-user, single-process — fine, and asserted by a lock file.
- Schema evolution needs explicit migrations (`capsule/migrate.py`), which is a feature: the
  format is a contract.

The **geocoding cache is the one exception** and uses SQLite at `~/.trippo/`, because it is
cross-trip infrastructure rather than trip content.
