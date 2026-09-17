# ADR-0001 — Local-first, with the capsule as the product boundary

- **Status:** Accepted
- **Date:** 2026-09-17

## Context

Trippo processes 8+ GB of personal media per trip. The long-term ambition is a hosted product where
finished trips are shared or viewed online. Building multi-tenant infrastructure now would sink the
POC; ignoring the ambition entirely would force a rewrite.

Local-first tools and SaaS want opposite things: filesystem paths vs object keys, no auth vs auth,
single-user mutable state vs tenant-isolated transactions.

## Decision

Build **local-only**. Add **no** SaaS scaffolding: no auth, no users, no database, no sync.

Adopt exactly three constraints as insurance, and nothing more:

1. **A `Storage` port.** All I/O goes through it; `LocalFsStorage` is the only implementation. No
   `pathlib` in `domain/`.
2. **`capsule.json` contains no absolute paths.** Media are referenced by content hash. Anything
   machine-specific lives in `media/index.local.json`, excluded from export and from any upload.
3. **Web derivatives (1600 px WebP) are materialised at capsule-write time**, so a hosted viewer
   could serve a capsule verbatim without ever seeing the originals.

The **capsule is the API contract** between the local studio and any future hosted product. The
hosted product's first version would be a *viewer*, not a re-implementation of ingestion.

## Consequences

- The POC stays small; the migration path is a new `Storage` adapter rather than a rewrite.
- Derivative generation costs time and disk at write, before there is any hosted product. Accepted:
  retrofitting it into an established capsule format would be far worse.
- A future agent must not add authentication, a database or multi-tenancy under the banner of
  "preparing for SaaS". That requires a new ADR superseding this one.
