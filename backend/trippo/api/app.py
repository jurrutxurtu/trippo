"""Local HTTP API. Thin: validate, delegate, serialise.

Serves one capsule at a time to the SPA on the adjacent Vite port. No auth, no database,
no sessions -- this is a single-user process on localhost (ADR-0001).

Media are served as static files straight from the capsule's derivative folders, so the
browser never sees an original and never holds 8 GB in memory.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trippo.capsule import io as capsule_io
from trippo.domain.models import Trip

# Windows has no registry entry for WebP, so `mimetypes` guesses None and StaticFiles
# serves every derivative as application/octet-stream. Browsers mostly sniff their way
# through it, but caches and <img> decoding hints do not.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")

app = FastAPI(title="Trippo", version="0.3.0")

# The SPA runs on Vite's dev server during development; same-origin in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATE: dict[str, object] = {"root": None, "trip": None}


def load_capsule(root: Path) -> Trip:
    trip = capsule_io.read(root)
    _STATE["root"] = root
    _STATE["trip"] = trip
    _mount_media(root)
    return trip


def _mount_media(root: Path) -> None:
    """Expose the capsule's derivative folders, and nothing else."""
    for name in ("media", "tracks"):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        route = f"/{name}"
        # Re-mounting on reload is fine; drop any previous mount for the same path.
        app.routes[:] = [
            r for r in app.routes if getattr(r, "path", None) != route
        ]
        app.mount(route, StaticFiles(directory=str(folder)), name=name)


def _trip() -> Trip:
    trip = _STATE.get("trip")
    if trip is None:
        raise HTTPException(status_code=404, detail="No capsule is loaded.")
    return trip  # type: ignore[return-value]


@app.get("/api/health")
def health() -> dict:
    root = _STATE.get("root")
    return {
        "status": "ok",
        "capsule": str(root) if root else None,
        "mapTilerKey": os.environ.get("MAPTILER_KEY", ""),
    }


@app.get("/api/trip")
def get_trip() -> JSONResponse:
    """The whole capsule. ~2 MB for a 27-day trip -- small enough to send at once,
    and far simpler than paginating something the explorer needs in full anyway."""
    return JSONResponse(_trip().model_dump(mode="json", by_alias=False))


@app.get("/api/tracks/{track_id}")
def get_track(track_id: str) -> FileResponse:
    """Simplified geometry and the resampled elevation profile, loaded on demand.

    Kept out of /api/trip because a single track is ~2 MB of points and only matters once
    the user opens that activity.
    """
    trip = _trip()
    track = trip.track_by_id(track_id)
    if track is None or not track.simplified_ref:
        raise HTTPException(status_code=404, detail=f"Unknown track {track_id}")
    root = _STATE["root"]
    path = Path(str(root)) / track.simplified_ref
    if not path.exists():
        raise HTTPException(status_code=404, detail="Track geometry was not written.")
    return FileResponse(path, media_type="application/json")
