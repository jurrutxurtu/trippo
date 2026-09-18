"""Background ingest jobs, and the native folder picker.

Ingestion takes minutes. It runs in a thread and reports progress over server-sent events,
because a seven-minute POST with a spinner tells the user nothing and looks broken.

The folder picker is the awkward part of a local-first web app: a browser cannot hand the
backend a real path, and streaming 8 GB through fetch to avoid that would defeat the entire
premise. Since the backend runs on the user's own machine, it opens a native dialog --
which is exactly what a desktop app would do. A paste-a-path field is the fallback for
anyone running the backend elsewhere.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trippo.service.build import BuildRequest, run_build


@dataclass
class JobEvent:
    stage: str
    message: str
    done: int = 0
    total: int = 0

    @property
    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "done": self.done,
            "total": self.total,
        }


@dataclass
class Job:
    id: str
    title: str
    out: Path
    status: str = "running"  # running | done | failed
    error: str | None = None
    capsule_id: str | None = None
    started: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    events: list[JobEvent] = field(default_factory=list)
    #: Readers wait on this rather than popping a queue, so the event list stays the single
    #: source of truth. A queue made a late client receive everything twice -- once from
    #: the replay, once from the queue -- and let a second client steal the first one's
    #: events.
    _cond: threading.Condition = field(
        default_factory=threading.Condition, repr=False
    )

    def emit(self, ev: JobEvent) -> None:
        with self._cond:
            self.events.append(ev)
            self._cond.notify_all()

    def finish(self, status: str, error: str | None = None) -> None:
        with self._cond:
            self.status = status
            self.error = error
            self._cond.notify_all()

    def drain(self, heartbeat: float = 10.0):
        """Yield events as they arrive; `None` is a heartbeat, not an ending.

        Silence is normal during ingestion -- a single Overpass batch can stall for over a
        minute -- so an idle stream must NOT be read as a finished one. Returning on a
        timeout is exactly what made a healthy import look like a failure: the stream
        closed, the endpoint then described a still-running job as over, and the UI had
        nothing better to do with that than call it an error.

        Each reader keeps its own cursor, so several clients can watch the same job and a
        late one still sees the whole history.
        """
        cursor = 0
        while True:
            with self._cond:
                while cursor >= len(self.events) and self.status == "running":
                    if not self._cond.wait(timeout=heartbeat):
                        break  # nothing new; fall through and send a heartbeat
                pending = self.events[cursor:]
                cursor = len(self.events)
                finished = self.status != "running"

            yield from pending
            if finished:
                return
            if not pending:
                yield None  # keep the connection open; say nothing


_JOBS: dict[str, Job] = {}


def get(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def start(req: BuildRequest, on_done=None) -> Job:
    """Run a build in the background. Returns immediately with a job to watch."""
    job = Job(id=uuid.uuid4().hex[:12], title=req.title, out=req.out)
    _JOBS[job.id] = job

    def progress(stage: str, message: str, done: int, total: int) -> None:
        job.emit(JobEvent(stage=stage, message=message, done=done, total=total))

    def worker() -> None:
        try:
            result = run_build(req, progress)
            job.capsule_id = result.out.name
            job.finish("done")
            if on_done:
                on_done(job, result)
        except Exception as exc:
            job.emit(JobEvent(stage="error", message=str(exc)[:300]))
            job.finish("failed", str(exc)[:300])

    threading.Thread(target=worker, daemon=True, name=f"ingest-{job.id}").start()
    return job


# --------------------------------------------------------------------------- picker


def pick_folder(title: str = "Choose a folder") -> str | None:
    """Open a native folder dialog on the machine running the backend.

    Tk must own its thread, so this creates and destroys a root each time rather than
    reusing one. Returns None when the user cancels, or when there is no desktop at all --
    in which case the UI falls back to a paste-a-path field.
    """
    return _pick(title, folder=True)


def pick_file(title: str = "Choose a file") -> str | None:
    return _pick(title, folder=False)


def _pick(title: str, folder: bool) -> str | None:
    result: dict[str, Any] = {"path": None}

    def run() -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)  # otherwise it opens behind the browser
            result["path"] = (
                filedialog.askdirectory(title=title)
                if folder
                else filedialog.askopenfilename(
                    title=title, filetypes=[("JSON", "*.json"), ("All files", "*.*")]
                )
            )
            root.destroy()
        except Exception:
            result["path"] = None

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=300)
    path = result["path"]
    return str(path) if path else None
