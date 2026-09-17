"""Persistent geocode cache. ADR-0003 (the one sanctioned SQLite in the product).

Cross-trip infrastructure rather than trip content, so it lives at `~/.trippo/` and not
inside a capsule.

Entries never expire: place names are stable, and the public providers this depends on
are rate-limited and occasionally blocked. Re-running enrichment must be instant and
offline, which is also what keeps the golden tests network-free.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from trippo.config.heuristics import GEOCODE_CACHE_PRECISION
from trippo.domain.models import PlaceSource
from trippo.ports.geocoder import PlaceCandidate

DEFAULT_CACHE_DIR = Path.home() / ".trippo"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS geocode (
    key        TEXT PRIMARY KEY,
    provider   TEXT NOT NULL,
    candidates TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


#: Bump when PlaceCandidate gains a field providers must re-supply. Old entries are then
#: simply never read again, which is cheaper and safer than migrating them.
CACHE_SCHEMA = 2


def cache_key(lat: float, lon: float, radius_m: float, provider: str) -> str:
    """~11 m grid at 4 dp. Radius is bucketed so a 380 m and a 400 m query share a hit."""
    p = GEOCODE_CACHE_PRECISION
    bucket = round(radius_m / 100.0) * 100
    return f"v{CACHE_SCHEMA}:{provider}:{round(lat, p)}:{round(lon, p)}:{bucket}"


class GeocodeCache:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path = DEFAULT_CACHE_DIR / "geocode-cache.sqlite"
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = Path(path)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> list[PlaceCandidate] | None:
        row = self._conn.execute(
            "SELECT candidates FROM geocode WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return [_from_dict(d) for d in json.loads(row[0])]

    def put(self, key: str, provider: str, candidates: list[PlaceCandidate]) -> None:
        payload = json.dumps([_to_dict(c) for c in candidates], ensure_ascii=False)
        self._conn.execute(
            "INSERT OR REPLACE INTO geocode (key, provider, candidates) VALUES (?, ?, ?)",
            (key, provider, payload),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> GeocodeCache:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _to_dict(c: PlaceCandidate) -> dict:
    d = asdict(c)
    d["source"] = c.source.value
    d.pop("raw", None)  # provider payloads are large and never read back
    return d


def _from_dict(d: dict) -> PlaceCandidate:
    d = dict(d)
    d["source"] = PlaceSource(d.get("source", "osm"))
    d.setdefault("raw", {})
    return PlaceCandidate(**d)
