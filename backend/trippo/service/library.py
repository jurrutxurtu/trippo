"""The capsule library: where trips live, and how they are made.

A workspace is a plain directory of `*.capsule` folders. No index, no database -- the
capsules *are* the library, so moving or deleting one in Explorer does the obvious thing
(ADR-0003).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUFFIX = ".capsule"


def workspace() -> Path:
    """Where new trips are written. Override with `TRIPPO_WORKSPACE`."""
    root = os.environ.get("TRIPPO_WORKSPACE")
    path = Path(root) if root else Path.home() / "TravelStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class CapsuleSummary:
    id: str
    title: str
    path: str
    start: str | None
    end: str | None
    day_count: int
    photo_count: int
    unaccounted_count: int
    cover: str | None
    modified: str
    status: str = "draft"

    @property
    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "start": self.start,
            "end": self.end,
            "dayCount": self.day_count,
            "photoCount": self.photo_count,
            "unaccountedCount": self.unaccounted_count,
            "cover": self.cover,
            "modified": self.modified,
            "status": self.status,
        }


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60] or "trip"


def unique_path(title: str, root: Path | None = None) -> Path:
    """A free directory for a new capsule. Never overwrites an existing trip."""
    base = root or workspace()
    stem = slugify(title)
    candidate = base / f"{stem}{SUFFIX}"
    n = 2
    while candidate.exists():
        candidate = base / f"{stem}-{n}{SUFFIX}"
        n += 1
    return candidate


def list_capsules(root: Path | None = None) -> list[CapsuleSummary]:
    """Summarise every capsule in the workspace.

    Reads `capsule.json` directly rather than going through the model, so a capsule
    written by a newer version -- or a half-finished one -- still appears in the list
    instead of breaking the page.
    """
    base = root or workspace()
    out: list[CapsuleSummary] = []
    for path in sorted(base.glob(f"*{SUFFIX}")):
        manifest = path / "capsule.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue

        media = data.get("media", [])
        cover = next(
            (m.get("thumb_ref") for m in media if m.get("thumb_ref")),
            None,
        )
        rng = data.get("date_range") or {}
        stats = data.get("stats") or {}
        out.append(
            CapsuleSummary(
                id=path.name,
                title=data.get("title") or path.stem,
                path=str(path),
                start=rng.get("start"),
                end=rng.get("end"),
                day_count=stats.get("day_count", 0),
                photo_count=stats.get("photo_count", 0),
                unaccounted_count=stats.get("unaccounted_count", 0),
                cover=cover,
                modified=datetime.fromtimestamp(manifest.stat().st_mtime).isoformat(
                    timespec="seconds"
                ),
                status=data.get("status", "draft"),
            )
        )
    out.sort(key=lambda c: c.modified, reverse=True)
    return out


def resolve(capsule_id: str, root: Path | None = None) -> Path:
    """Map an id back to a path, refusing anything that escapes the workspace."""
    base = (root or workspace()).resolve()
    path = (base / capsule_id).resolve()
    if not str(path).startswith(str(base)):
        raise ValueError("Capsule id escapes the workspace")
    if not (path / "capsule.json").is_file():
        raise FileNotFoundError(f"No capsule at {capsule_id}")
    return path


def delete(capsule_id: str, root: Path | None = None) -> None:
    """Remove a capsule. Originals are untouched -- only derivatives ever lived here."""
    shutil.rmtree(resolve(capsule_id, root))
