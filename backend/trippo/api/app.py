"""Local HTTP API. Thin: validate, delegate, serialise.

Serves the capsule library and one open capsule to the SPA. No auth, no database, no
sessions -- this is a single-user process on localhost (ADR-0001).

Media are served as static files straight from the capsule's derivative folders, so the
browser never sees an original and never holds 8 GB in memory.
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import shutil
import zipfile
from datetime import date as _date
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trippo.capsule import io as capsule_io
from trippo.domain.models import Trip
from trippo.ports.llm import Llm

# Windows has no registry entry for WebP, so `mimetypes` guesses None and StaticFiles
# serves every derivative as application/octet-stream. Browsers mostly sniff their way
# through it, but caches and <img> decoding hints do not.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")

app = FastAPI(title="Trippo", version="0.4.0")

cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8787",
    "http://127.0.0.1:8787",
]
if extra := os.environ.get("TRIPPO_CORS_ORIGINS"):
    cors_origins.extend([o.strip() for o in extra.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATE: dict[str, object] = {"root": None, "session": None}


def load_capsule(root: Path) -> Trip:
    from trippo.capsule.session import CurationSession

    trip = capsule_io.read(root)
    _STATE["root"] = root
    _STATE["session"] = CurationSession(trip=trip, root=root)
    _mount_media(root)
    return trip


def _mount_media(root: Path) -> None:
    """Expose the capsule's derivative folders, and nothing else."""
    for name in ("media", "tracks"):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        route = f"/{name}"
        # Opening a different capsule replaces the mount rather than stacking one.
        app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != route]
        app.mount(route, StaticFiles(directory=str(folder)), name=name)


def _session():
    s = _STATE.get("session")
    if s is None:
        raise HTTPException(status_code=404, detail="No capsule is open.")
    return s


def _trip() -> Trip:
    return _session().trip  # type: ignore[no-any-return]


def _session_state(session) -> dict:
    """Everything the client needs after a change: the trip plus what undo can do."""
    return {
        "trip": session.trip.model_dump(mode="json"),
        "canUndo": session.can_undo,
        "canRedo": session.can_redo,
        "dirty": session.dirty,
    }


# ============================================================================ health


@lru_cache(maxsize=1)
def _llm() -> Llm:
    """One provider chain per process.

    Deliberately cached: the chain demotes a provider that has failed, and rebuilding it
    on every request would throw that away and re-try the dead one forever.
    """
    from trippo.ai.provider import provider_from_env

    return provider_from_env()

@app.get("/api/health")
def health() -> dict:
    root = _STATE.get("root")
    return {
        "status": "ok",
        "capsule": str(root) if root else None,
        "capsuleOpen": _STATE.get("session") is not None,
        "mapTilerKey": os.environ.get("MAPTILER_KEY", ""),
        "aiAvailable": _llm().available,
        "aiProvider": _llm().name,
        "placesAvailable": bool(os.environ.get("GOOGLE_PLACES_API_KEY")),
    }


# ============================================================================ library


@app.get("/api/capsules")
def list_capsules() -> JSONResponse:
    from trippo.service import library

    return JSONResponse(
        {
            "workspace": str(library.workspace()),
            "capsules": [c.as_dict for c in library.list_capsules()],
        }
    )


@app.post("/api/capsules/{capsule_id}/open")
def open_capsule(capsule_id: str) -> JSONResponse:
    from trippo.service import library

    try:
        root = library.resolve(capsule_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    trip = load_capsule(root)
    return JSONResponse({"opened": capsule_id, "title": trip.title})


@app.delete("/api/capsules/{capsule_id}")
def delete_capsule(capsule_id: str) -> JSONResponse:
    from trippo.service import library

    try:
        library.delete(capsule_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse({"deleted": capsule_id})


@app.post("/api/capsules/upload")
async def upload_capsule(file: UploadFile = File(...)) -> JSONResponse:
    """Import a .capsule directory packaged as a .zip archive into the workspace."""
    from trippo.service import library

    if not file.filename or not file.filename.endswith((".zip", ".capsule")):
        raise HTTPException(
            status_code=400, detail="Only .zip archives containing a capsule are supported"
        )

    content = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            members = z.namelist()
            manifest = next(
                (m for m in members if m == "capsule.json" or m.endswith("/capsule.json")), None
            )
            if not manifest:
                raise HTTPException(
                    status_code=400, detail="Archive does not contain a valid capsule.json"
                )

            target_name = file.filename.removesuffix(".zip")
            if not target_name.endswith(".capsule"):
                target_name += ".capsule"
            target_dir = library.workspace() / target_name
            target_dir.mkdir(parents=True, exist_ok=True)

            prefix = manifest.removesuffix("capsule.json")
            for member in members:
                if member.endswith("/"):
                    continue
                rel_path = member[len(prefix) :] if member.startswith(prefix) else member
                dest = target_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as source, open(dest, "wb") as target:
                    shutil.copyfileobj(source, target)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid zip archive") from exc

    return JSONResponse({"status": "imported", "capsuleId": target_name})


@app.post("/api/capsules/build-preprocessed")
async def build_preprocessed(file: UploadFile = File(...)) -> JSONResponse:
    """Build a capsule from client-side preprocessed data packaged in a zip.

    Used when ingesting via browser / remote server: client extracted EXIF and resized
    thumbnails in JavaScript, then uploaded this lightweight bundle.
    """
    import tempfile
    import zipfile
    from datetime import date as _date

    from trippo.service import jobs, library
    from trippo.service.preprocessed import PreprocessedBuildRequest

    staging_dir = Path(tempfile.mkdtemp(prefix="trippo_preprocessed_"))
    try:
        content = await file.read()
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            z.extractall(staging_dir)

        manifest_path = staging_dir / "ingest_manifest.json"
        if not manifest_path.is_file():
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400, detail="Missing ingest_manifest.json in archive"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        title = (manifest.get("title") or "Untitled trip").strip()
        description = manifest.get("description")
        date_from_str = manifest.get("date_from")
        date_to_str = manifest.get("date_to")
        default_offset = int(manifest.get("default_offset_minutes") or 0)
        enrich = bool(manifest.get("enrich", True))

        date_from = _date.fromisoformat(date_from_str) if date_from_str else None
        date_to = _date.fromisoformat(date_to_str) if date_to_str else None

        out = library.unique_path(title)
        job = jobs.start_preprocessed(
            PreprocessedBuildRequest(
                title=title,
                description=description,
                out=out,
                staging_dir=staging_dir,
                date_from=date_from,
                date_to=date_to,
                default_offset_minutes=default_offset,
                enrich=enrich,
            )
        )
        return JSONResponse({"jobId": job.id, "capsuleId": out.name})
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid zip archive") from exc
    except HTTPException:
        raise
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ============================================================================ creation


class BrowseRequest(BaseModel):
    kind: str = "folder"
    title: str = "Choose a folder"


@app.post("/api/browse")
def browse(req: BrowseRequest) -> JSONResponse:
    """Open a native picker on the machine running the backend.

    A browser cannot give us a real path, and streaming 8 GB through fetch to avoid that
    would defeat the whole premise. The backend is local, so it asks the desktop. The UI
    falls back to a paste-a-path field when this returns nothing.
    """
    from trippo.service.jobs import pick_file, pick_folder

    path = pick_folder(req.title) if req.kind == "folder" else pick_file(req.title)
    return JSONResponse({"path": path})


class ProposeRequest(BaseModel):
    media: list[str] = []


@app.post("/api/propose-dates")
def propose(req: ProposeRequest) -> JSONResponse:
    """Guess the trip's dates from photo timestamps, without a full ingest."""
    from trippo.service.build import propose_dates

    found = propose_dates([Path(p) for p in req.media if p])
    if not found:
        return JSONResponse({"start": None, "end": None})
    return JSONResponse({"start": found[0].isoformat(), "end": found[1].isoformat()})


class CreateRequest(BaseModel):
    title: str
    description: str | None = None
    timeline: str | None = None
    gpx: str | None = None
    media: list[str] = []
    date_from: str | None = None
    date_to: str | None = None
    enrich: bool = True
    derivatives: bool = True


@app.post("/api/capsules")
def create_capsule(req: CreateRequest) -> JSONResponse:
    """Start an ingest. Returns immediately with a job to watch over SSE."""
    from trippo.service import jobs, library
    from trippo.service.build import BuildRequest

    if not (req.timeline or req.gpx or req.media):
        raise HTTPException(status_code=400, detail="Add at least one source.")

    out = library.unique_path(req.title)
    job = jobs.start(
        BuildRequest(
            title=req.title.strip() or "Untitled trip",
            description=req.description,
            out=out,
            timeline=Path(req.timeline) if req.timeline else None,
            gpx=Path(req.gpx) if req.gpx else None,
            media=[Path(p) for p in req.media if p],
            date_from=_date.fromisoformat(req.date_from) if req.date_from else None,
            date_to=_date.fromisoformat(req.date_to) if req.date_to else None,
            enrich=req.enrich,
            derivatives=req.derivatives,
        )
    )
    return JSONResponse({"jobId": job.id, "capsuleId": out.name})


@app.get("/api/jobs")
def list_jobs() -> JSONResponse:
    """Every job this process knows about, newest first.

    Exists because the job id otherwise lives only in the browser tab that started the
    import, which makes a long-running job impossible to check on from anywhere else.
    """
    from trippo.service import jobs

    known = sorted(jobs.all_jobs(), key=lambda j: j.started, reverse=True)
    return JSONResponse(
        {
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "status": j.status,
                    "error": j.error,
                    "capsuleId": j.capsule_id,
                    "started": j.started,
                    "lastEvent": j.events[-1].as_dict if j.events else None,
                    "eventCount": len(j.events),
                }
                for j in known
            ]
        }
    )


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    from trippo.service import jobs

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return JSONResponse(
        {
            "id": job.id,
            "status": job.status,
            "error": job.error,
            "capsuleId": job.capsule_id,
            "events": [e.as_dict for e in job.events],
        }
    )


@app.get("/api/jobs/{job_id}/stream")
def job_stream(job_id: str) -> StreamingResponse:
    """Progress as server-sent events. A seven-minute spinner tells the user nothing."""
    from trippo.service import jobs

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")

    def gen():
        for ev in job.drain():
            if ev is None:
                # An SSE comment. EventSource ignores it, proxies keep the socket warm,
                # and the client learns that nothing has gone wrong.
                yield ": ping\n\n"
                continue
            yield f"data: {json.dumps(ev.as_dict)}\n\n"
        payload = {
            "status": job.status,
            "error": job.error,
            "capsuleId": job.capsule_id,
        }
        yield f"event: end\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================================ the capsule


@app.get("/api/trip")
def get_trip() -> JSONResponse:
    """The whole capsule. ~2 MB for a 27-day trip -- small enough to send at once, and
    far simpler than paginating something the explorer needs in full anyway."""
    return JSONResponse(_trip().model_dump(mode="json"))


@app.get("/api/report")
def ingestion_report() -> JSONResponse:
    """Per-day coverage and degradations, shown BEFORE the itinerary.

    This is what turns "why is day 3 empty?" into "day 3 has no data, and here is why".
    """
    trip = _trip()
    return JSONResponse(
        {
            "sources": [
                {
                    "kind": s.kind.value,
                    "name": s.display_name,
                    "format": s.detected_format,
                    "report": s.report.model_dump(mode="json") if s.report else None,
                }
                for s in trip.sources
            ],
            "coverage": [c.model_dump(mode="json") for c in trip.stats.coverage],
            "degradations": [
                d for s in trip.sources if s.report for d in s.report.degradations
            ],
        }
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
    path = Path(str(_STATE["root"])) / track.simplified_ref
    if not path.exists():
        raise HTTPException(status_code=404, detail="Track geometry was not written.")
    return FileResponse(path, media_type="application/json")


# ============================================================================ curation


class OpRequest(BaseModel):
    op: str
    payload: dict = {}


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


@app.get("/api/events/{event_id}/nearby")
def nearby_media(event_id: str, minutes: int = 45) -> JSONResponse:
    """Photographs taken around an event, for attaching in bulk.

    Searches the unassigned pool first -- those have no home -- then everything else, so
    the user can see what is already attached elsewhere before stealing it.
    """
    from datetime import timedelta

    trip = _trip()
    event = trip.event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Unknown event")

    window = timedelta(minutes=max(1, min(minutes, 240)))
    lo, hi = event.start - window, event.end + window
    owned = {m for e in trip.events for m in e.media_ids}
    pool = set(trip.unassigned_media_ids)

    out = []
    for m in trip.media:
        if m.captured_at is None or not (lo <= m.captured_at <= hi):
            continue
        if m.id in event.media_ids:
            continue
        owner = next((e for e in trip.events if m.id in e.media_ids), None)
        out.append(
            {
                "id": m.id,
                "thumb": m.thumb_ref,
                "capturedAt": m.captured_at.isoformat(),
                "unassigned": m.id in pool,
                "ownerEventId": owner.id if owner else None,
                "ownerTitle": owner.title if owner else None,
            }
        )
    out.sort(key=lambda x: (not x["unassigned"], x["capturedAt"]))
    return JSONResponse({"window": minutes, "candidates": out, "totalOwned": len(owned)})


SUGGESTION_KINDS = ("group", "demote", "day_title", "activity_shape", "place_name")


@app.post("/api/suggestions/{kind}")
def generate_suggestions(kind: str) -> JSONResponse:
    """Ask the model for structural proposals of one kind.

    Nothing is applied. Each suggestion carries the operations that would apply it, so the
    user accepts or rejects, and an accepted one is undoable like any other edit.
    """
    from trippo.ai import suggestions as sg

    if kind not in SUGGESTION_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown kind {kind!r}")

    llm = _llm()
    # Demotion is a deterministic rule; the model only refines it. Everything else needs
    # a model to say anything at all.
    if not llm.available and kind != "demote":
        return JSONResponse(status_code=204, content=None)

    trip = _trip()
    if kind == "place_name":
        items = sg.suggest_place_names(llm, trip, candidates_for=_cached_candidates)
    else:
        items = sg.GENERATORS[kind](llm, trip)

    return JSONResponse(
        {
            "kind": kind,
            "items": [i.as_dict for i in items],
            # A blocked key and an empty answer look identical otherwise.
            "error": getattr(llm, "last_error", None),
        }
    )


def _cached_candidates(event) -> list[str]:
    """Names the geocoder already saw for this point, straight from the cache.

    Re-querying Overpass to break a tie would be absurd -- the candidates were fetched
    minutes ago and are sitting on disk.
    """
    from trippo.enrich.cache import GeocodeCache, cache_key

    if not event.place or event.place.lat is None:
        return []
    names: list[str] = []
    with GeocodeCache() as cache:
        for provider in ("overpass", "nominatim"):
            for radius in (100, 200, 300, 400, 500, 600, 800, 1000):
                hit = cache.get(
                    cache_key(event.place.lat, event.place.lon, radius, provider)
                )
                for c in hit or []:
                    if c.name not in names:
                        names.append(c.name)
    return names[:10]


@app.get("/api/curation/agenda")
def curation_agenda() -> JSONResponse:
    """What the user still has to decide, ordered by how much it matters.

    This is the guided pass between ingestion and a finished trip: the machine has made a
    draft, and this is the list of things only a person can settle.
    """
    from trippo.ai.agenda import blocking_count, build_agenda

    trip = _trip()
    items = build_agenda(trip)
    return JSONResponse(
        {
            "status": trip.status.value,
            "curatedAt": trip.curated_at.isoformat() if trip.curated_at else None,
            "items": [i.as_dict for i in items],
            "blocking": blocking_count(items),
            "counts": {
                "decide": sum(1 for i in items if i.kind.value == "decide"),
                "check": sum(1 for i in items if i.kind.value == "check"),
                "polish": sum(1 for i in items if i.kind.value == "polish"),
            },
        }
    )


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


# ============================================================================ ai


class SuggestRequest(BaseModel):
    kind: str
    day_id: str | None = None
    text: str | None = None


@app.post("/api/suggest")
def suggest(req: SuggestRequest) -> JSONResponse:
    """Optional AI. Returns 204 when no model is configured, so the UI hides the feature."""
    from trippo.ai import suggest as s

    llm = _llm()
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
            {"ok": False, "reason": "No usable suggestion was produced."}
        )
    return JSONResponse(
        {"ok": True, "value": result.value, "alternatives": result.alternatives}
    )


# ============================================================================ frontend spa
_static_dir_env = os.environ.get("TRIPPO_STATIC_DIR")
_static_dir = (
    Path(_static_dir_env)
    if _static_dir_env
    else Path(__file__).resolve().parents[3] / "frontend" / "dist"
)

if _static_dir.is_dir() and (_static_dir / "index.html").is_file():
    _assets_dir = _static_dir / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/")
    async def serve_spa_root() -> FileResponse:
        return FileResponse(_static_dir / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "media/", "tracks/")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static_dir / "index.html")

