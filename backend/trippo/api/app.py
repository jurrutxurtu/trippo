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
from pydantic import BaseModel

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

_STATE: dict[str, object] = {"root": None, "trip": None, "session": None}


def load_capsule(root: Path) -> Trip:
    from trippo.capsule.session import CurationSession

    trip = capsule_io.read(root)
    _STATE["root"] = root
    _STATE["trip"] = trip
    _STATE["session"] = CurationSession(trip=trip, root=root)
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
    session = _STATE.get("session")
    if session is not None:
        return session.trip  # type: ignore[attr-defined,no-any-return]
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
        "aiAvailable": bool(os.environ.get("GEMINI_API_KEY")),
    }


@app.get("/api/trip")
def get_trip() -> JSONResponse:
    """The whole capsule. ~2 MB for a 27-day trip -- small enough to send at once,
    and far simpler than paginating something the explorer needs in full anyway."""
    return JSONResponse(_trip().model_dump(mode="json", by_alias=False))


class OpRequest(BaseModel):
    op: str
    payload: dict = {}


def _session():
    s = _STATE.get("session")
    if s is None:
        raise HTTPException(status_code=404, detail="No capsule is loaded.")
    return s


def _session_state(session) -> dict:
    """Everything the client needs after a change: the trip plus what undo can do."""
    return {
        "trip": session.trip.model_dump(mode="json"),
        "canUndo": session.can_undo,
        "canRedo": session.can_redo,
        "dirty": session.dirty,
    }


@app.post("/api/ops")
def apply_op(req: OpRequest) -> JSONResponse:
    """Apply one curation operation.

    Invariants are checked server-side on every call; a violation rolls the whole
    operation back and returns 409, so the client can never drive the capsule into an
    invalid state.
    """
    from trippo.domain import ops as domain_ops
    from trippo.domain.invariants import InvariantError

    session = _session()
    try:
        session.apply(req.op, req.payload)
    except domain_ops.OpError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Bad payload: {exc}") from exc
    return JSONResponse(_session_state(session))


@app.post("/api/undo")
def undo() -> JSONResponse:
    session = _session()
    session.undo()
    return JSONResponse(_session_state(session))


@app.post("/api/redo")
def redo() -> JSONResponse:
    session = _session()
    session.redo()
    return JSONResponse(_session_state(session))


@app.post("/api/save")
def save() -> JSONResponse:
    session = _session()
    session.save()
    return JSONResponse({"saved": True, "dirty": session.dirty})


@app.get("/api/review")
def review() -> JSONResponse:
    """Everything worth checking before calling a trip finished.

    Mostly deterministic -- do not ask a model what Python can compute.
    """
    from trippo.ai.coherence import check_trip

    findings = check_trip(_trip())
    return JSONResponse(
        {
            "findings": [
                {
                    "severity": f.severity.value,
                    "code": f.code,
                    "message": f.message,
                    "dayId": f.day_id,
                    "eventId": f.event_id,
                    "action": f.action,
                }
                for f in findings
            ],
            "blocking": sum(1 for f in findings if f.severity.value == "blocking"),
        }
    )


class SuggestRequest(BaseModel):
    kind: str
    day_id: str | None = None
    text: str | None = None


@app.post("/api/suggest")
def suggest(req: SuggestRequest) -> JSONResponse:
    """Optional AI. Returns 204 when no model is configured, so the UI hides the feature."""
    from trippo.ai import suggest as s
    from trippo.ai.gemini import provider_from_env

    llm = provider_from_env()
    if not llm.available:
        return JSONResponse(status_code=204, content=None)

    trip = _trip()
    result = None
    if req.kind == "day_title" and req.day_id:
        result = s.suggest_day_title(llm, trip, req.day_id)
    elif req.kind == "trip_summary":
        result = s.suggest_trip_summary(llm, trip)
    elif req.kind == "polish_note" and req.text:
        result = s.polish_note(llm, req.text)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown suggestion {req.kind!r}")

    if result is None:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "reason": "No usable suggestion was produced."},
        )
    return JSONResponse(
        {"ok": True, "value": result.value, "alternatives": result.alternatives}
    )


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
