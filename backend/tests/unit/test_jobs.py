"""Background ingest jobs and the progress stream.

The stream is the part that broke: a healthy Morocco import reported "The import stopped"
with an empty error box, because the SSE generator gave up after thirty seconds of silence
and the endpoint then described a still-running job as finished.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from trippo.service.build import BuildRequest
from trippo.service.jobs import Job, JobEvent, start


@pytest.fixture
def job() -> Job:
    return Job(id="j1", title="Morocco", out=Path("/tmp/x.capsule"))


def _collect(job: Job, heartbeat: float, stop_after: int) -> list:
    out = []
    for ev in job.drain(heartbeat=heartbeat):
        out.append(ev)
        if len(out) >= stop_after:
            break
    return out


# --------------------------------------------------------------------------- the bug


def test_silence_does_not_end_the_stream(job: Job):
    """The regression.

    Overpass can stall for over a minute on one batch. The stream must keep the connection
    open rather than concluding the job is over -- that is what turned a working import
    into "The import stopped" with no message.
    """
    got = _collect(job, heartbeat=0.05, stop_after=3)
    assert got == [None, None, None], "expected heartbeats, not an ended stream"
    assert job.status == "running"


def test_a_heartbeat_is_distinguishable_from_an_event(job: Job):
    job.emit(JobEvent(stage="enrich", message="overpass 1-6", done=0, total=97))
    got = _collect(job, heartbeat=0.05, stop_after=2)
    assert isinstance(got[0], JobEvent)
    assert got[1] is None


def test_the_stream_ends_when_the_job_finishes(job: Job):
    def finish() -> None:
        time.sleep(0.1)
        job.emit(JobEvent(stage="save", message="Saved"))
        job.finish("done")

    threading.Thread(target=finish, daemon=True).start()
    events = list(job.drain(heartbeat=0.02))
    assert any(isinstance(e, JobEvent) and e.stage == "save" for e in events)
    assert job.status == "done"


def test_a_late_client_still_sees_everything(job: Job):
    """Opening the page after the import finished must not show an empty log."""
    job.emit(JobEvent(stage="media", message="252 photographs"))
    job.emit(JobEvent(stage="build", message="13 days, 97 events"))
    job.finish("done")

    events = list(job.drain(heartbeat=0.02))
    assert [e.stage for e in events if e] == ["media", "build"]


def test_a_failed_job_ends_the_stream_with_its_reason(job: Job):
    job.emit(JobEvent(stage="error", message="boom"))
    job.finish("failed", "boom")
    events = list(job.drain(heartbeat=0.02))
    assert job.status == "failed"
    assert job.error == "boom"
    assert len(events) == 1


# --------------------------------------------------------------------------- lifecycle


def test_a_failing_build_is_reported_not_raised(tmp_path):
    """A bad import must mark the job failed, never kill the server thread."""
    req = BuildRequest(title="Nothing", out=tmp_path / "x.capsule", enrich=False,
                       derivatives=False)
    job = start(req)
    for _ in range(100):
        if job.status != "running":
            break
        time.sleep(0.05)
    assert job.status == "failed"
    assert job.error and "no usable data" in job.error.lower()


def test_a_successful_build_reports_its_capsule(tmp_path):
    gpx = tmp_path / "t.gpx"
    gpx.write_bytes(
        b"""<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1">
        <trk><name>Toubkal</name><type>hiking</type><trkseg>
          <trkpt lat="31.06" lon="-7.91"><ele>3200</ele>
            <time>2024-04-02T08:00:00Z</time></trkpt>
          <trkpt lat="31.07" lon="-7.92"><ele>4100</ele>
            <time>2024-04-02T12:00:00Z</time></trkpt>
        </trkseg></trk></gpx>"""
    )
    out = tmp_path / "Morocco.capsule"
    job = start(
        BuildRequest(title="Morocco", out=out, gpx=gpx, enrich=False, derivatives=False)
    )
    for _ in range(200):
        if job.status != "running":
            break
        time.sleep(0.05)

    assert job.status == "done", job.error
    assert job.capsule_id == "Morocco.capsule"
    assert (out / "capsule.json").exists()
    assert any(e.stage == "save" for e in job.events)
