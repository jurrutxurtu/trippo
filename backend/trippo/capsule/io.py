"""Capsule read/write. ADR-0003 -- directory-as-document, no database.

`capsule.json` must never contain an absolute path; machine-specific paths live in
`media/index.local.json`, which is excluded from export and from any future upload
(ADR-0001). The invariant checker enforces this on every write.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trippo.capsule.migrate import migrate
from trippo.domain.invariants import check
from trippo.domain.models import SCHEMA_VERSION, IngestionReport, Trip
from trippo.ports.storage import LocalFsStorage, Storage

CAPSULE_JSON = "capsule.json"
LOCAL_INDEX = "media/index.local.json"
REPORTS = "reports/ingestion.json"


def _dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def write(
    trip: Trip,
    root: Path,
    *,
    local_paths: dict[str, str] | None = None,
    reports: list[IngestionReport] | None = None,
    validate: bool = True,
) -> Path:
    if validate:
        check(trip)

    storage: Storage = LocalFsStorage(root)
    trip.updated_at = datetime.now(UTC)
    trip.schema_version = SCHEMA_VERSION

    storage.write_text(CAPSULE_JSON, _dumps(trip.model_dump(mode="json")))

    if local_paths:
        # Deliberately a separate file: it is the one machine-specific artifact, and it
        # must be trivially droppable when a capsule is shared or uploaded.
        storage.write_text(
            LOCAL_INDEX,
            _dumps(
                {
                    "_comment": (
                        "Machine-specific absolute paths to original media. NEVER upload "
                        "or export this file. See ADR-0001."
                    ),
                    "paths": local_paths,
                }
            ),
        )

    if reports:
        storage.write_text(REPORTS, _dumps([r.model_dump(mode="json") for r in reports]))

    return Path(root) / CAPSULE_JSON


def read(root: Path, *, validate: bool = True) -> Trip:
    storage: Storage = LocalFsStorage(root)
    payload = json.loads(storage.read_text(CAPSULE_JSON))
    payload = migrate(payload)
    trip = Trip.model_validate(payload)
    if validate:
        check(trip)
    return trip


def read_local_paths(root: Path) -> dict[str, str]:
    storage: Storage = LocalFsStorage(root)
    if not storage.exists(LOCAL_INDEX):
        return {}
    return json.loads(storage.read_text(LOCAL_INDEX)).get("paths", {})
