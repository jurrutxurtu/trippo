"""Capsule migrations. AGENTS.md section 3.6.

Any change to the capsule models requires, in the same commit:
  1. a SCHEMA_VERSION bump in domain/models.py
  2. a migration registered here
  3. an entry in docs/technical/capsule-format.md

Reading a capsule NEWER than this code understands is a hard error, never a partial parse:
silently dropping unknown fields would corrupt the user's data on the next save.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from trippo.domain.models import SCHEMA_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]

#: version -> (next_version, migration). Applied in order on read.
MIGRATIONS: dict[str, tuple[str, Migration]] = {}


def _parse(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def migrate(payload: dict[str, Any]) -> dict[str, Any]:
    version = str(payload.get("schema_version") or payload.get("schemaVersion") or "0.0.0")

    if _parse(version) > _parse(SCHEMA_VERSION):
        raise ValueError(
            f"This capsule was written by a newer version of Trippo "
            f"(schema {version}, this build understands {SCHEMA_VERSION}). "
            "Upgrade Trippo rather than risk losing data."
        )

    while version != SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            if _parse(version) < _parse(SCHEMA_VERSION):
                # No registered path: accept and let Pydantic defaults fill the gaps.
                payload["schema_version"] = SCHEMA_VERSION
                return payload
            break
        next_version, fn = step
        payload = fn(payload)
        payload["schema_version"] = next_version
        version = next_version

    return payload
