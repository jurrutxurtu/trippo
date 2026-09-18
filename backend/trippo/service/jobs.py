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

import queue
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
    _queue: queue.Queue = field(default_factory=queue.Queue, repr=False)

    def emit(self, ev: JobEvent) -> None:
        self.events.append(ev)
        self._queue.put(ev)

    def finish(self, status: str, error: str | None = None) -> None:
        self.status = status
        self.error = error
        self._queue.put(None)  # sentinel: closes any open stream

    def drain(self, timeout: float = 30.0):
        """Yield events as they arrive, then stop when the job finishes."""
        # Anything that happened before the client connected still needs sending.
        yield from list(self.events)
        if self.status != "running":
            return
        while True:
            try:
                ev = self._queue.get(timeout=timeout)
            except queue.Empty:
                return
            if ev is None:
                return
            yield ev


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
