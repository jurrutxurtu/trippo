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


def _v010_to_v020(payload: dict[str, Any]) -> dict[str, Any]:
    """0.1.0 -> 0.2.0: map support.

    Adds `Day.bbox`, `Day.stats`, `Trip.bbox`, `Trip.route` and
    `ActivityDetail.highlights`. All are derived, so the migration only needs to leave the
    document valid -- `domain.summarize.summarize()` refills them on the next build, and
    `highlights` stays empty until enrichment runs again.
    """
    for day in payload.get("days", []):
        day.setdefault("bbox", None)
        day.setdefault("stats", {})
    for event in payload.get("events", []):
        detail = event.get("detail") or {}
        if detail.get("kind") == "activity":
            detail.setdefault("highlights", [])
    payload.setdefault("bbox", None)
    payload.setdefault("route", [])
    return payload


def _v020_to_v030(payload: dict[str, Any]) -> dict[str, Any]:
    """0.2.0 -> 0.3.0: photo selection.

    Adds Event.selected_media_ids and Event.user_selected_media. Derived, so an empty
    list is valid and domain.photos.select() refills it on the next build. A user's own
    curation is preserved because the flag defaults to False only for capsules that never
    had one.
    """
    for event in payload.get("events", []):
        event.setdefault("selected_media_ids", [])
        event.setdefault("user_selected_media", False)
    return payload


def _v030_to_v040(payload: dict[str, Any]) -> dict[str, Any]:
    """0.3.0 -> 0.4.0: Day.user_title.

    Existing titles were all generated, so False is the correct default: they will be
    refreshed from the events on the next derivation, which is what we want.
    """
    for day in payload.get("days", []):
        day.setdefault("user_title", False)
    return payload


def _v040_to_v050(payload: dict[str, Any]) -> dict[str, Any]:
    """0.4.0 -> 0.5.0: the trip lifecycle.

    Adds Trip.status and Trip.curated_at. Existing capsules become drafts, which is
    the honest default: nobody has walked through them and agreed the itinerary.
    """
    payload.setdefault("status", "draft")
    payload.setdefault("curated_at", None)
    return payload


def _v050_to_v060(payload: dict[str, Any]) -> dict[str, Any]:
    """0.5.0 -> 0.6.0: Event.summary.

    A model-written one-liner, kept separate from 
ote so the user's own words are never
    overwritten by a suggestion.
    """
    for event in payload.get("events", []):
        event.setdefault("summary", None)
    return payload


#: version -> (next_version, migration). Applied in order on read.
MIGRATIONS: dict[str, tuple[str, Migration]] = {
    "0.5.0": ("0.6.0", _v050_to_v060),
    "0.1.0": ("0.2.0", _v010_to_v020),
    "0.2.0": ("0.3.0", _v020_to_v030),
    "0.3.0": ("0.4.0", _v030_to_v040),
    "0.4.0": ("0.5.0", _v040_to_v050),

}


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
