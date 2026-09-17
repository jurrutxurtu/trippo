"""Google Timeline adapters -> NormalizedObservation.

Two-layer model (ADR-0009):
  * Layer 1 -- `visit` and `activity` become candidate events.
  * Layer 2 -- `timelinePath` feeds the PositionIndex ONLY and never creates an event.

Provider hints (`type`, `distanceMeters`) are carried but never trusted: the reference
export labelled a ~900 km ferry crossing as 24 km (pathology P2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from dateutil import parser as dtparse

from trippo.domain.models import IngestionReport, SourceKind
from trippo.ingest.timeline.sniff import SniffResult, e7, parse_lat_lng, sniff
from trippo.observe.models import NormalizedObservation, ObservationKind


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        d = dtparse.isoparse(str(value))
    except (ValueError, OverflowError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _in_window(t: datetime, start: datetime | None, end: datetime | None) -> bool:
    return not ((start and t < start) or (end and t > end))


def load(
    payload: Any,
    source_id: str,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[list[NormalizedObservation], IngestionReport]:
    """Dispatch on the sniffed format and normalise."""
    s = sniff(payload)
    report = IngestionReport(
        source_id=source_id,
        kind=SourceKind.TIMELINE,
        detected_format=s.format,
        confidence=s.confidence,
        files_seen=1,
        files_parsed=1 if s.format != "unknown" else 0,
        records_total=s.record_count,
        notes=[s.note] if s.note else [],
    )
    if s.format == "unknown":
        report.degradations.append(
            "Timeline file not recognised; it contributed nothing to this trip."
        )
        return [], report

    # Widen the window by a day so a visit that starts before midnight local still lands.
    pad = timedelta(days=1)
    ws = window_start - pad if window_start else None
    we = window_end + pad if window_end else None

    fn = {
        "on_device": _load_on_device,
        "semantic_lh": _load_semantic_lh,
        "records": _load_records,
    }[s.format]
    obs = fn(payload, source_id, ws, we, report, s)
    report.records_in_window = len(obs)
    _annotate(report, obs)
    return obs, report


def _annotate(report: IngestionReport, obs: list[NormalizedObservation]) -> None:
    counts = {k: 0 for k in ObservationKind}
    for o in obs:
        counts[o.kind] += 1
    report.notes.append(
        f"layer 1 (events): {counts[ObservationKind.VISIT]} visits, "
        f"{counts[ObservationKind.MOVE]} moves; "
        f"layer 2 (positions only): {counts[ObservationKind.BREADCRUMB]} breadcrumbs"
    )
    if not obs:
        report.degradations.append("No timeline records fall inside the selected date window.")


# --------------------------------------------------------------------------- on-device (2024+)


def _load_on_device(
    payload: dict[str, Any],
    source_id: str,
    ws: datetime | None,
    we: datetime | None,
    report: IngestionReport,
    _s: SniffResult,
) -> list[NormalizedObservation]:
    out: list[NormalizedObservation] = []
    for i, seg in enumerate(payload.get("semanticSegments", [])):
        if not isinstance(seg, dict):
            continue
        start, end = _dt(seg.get("startTime")), _dt(seg.get("endTime"))
        if start is None or end is None or not _in_window(start, ws, we):
            continue
        off = seg.get("startTimeTimezoneUtcOffsetMinutes")
        off = int(off) if isinstance(off, (int, float)) else None
        ref = f"seg{i}"

        if (visit := seg.get("visit")) and isinstance(visit, dict):
            cand = (visit.get("topCandidate") or {}) if isinstance(visit, dict) else {}
            coord = parse_lat_lng((cand.get("placeLocation") or {}).get("latLng"))
            out.append(
                NormalizedObservation(
                    t=start,
                    end_t=end,
                    kind=ObservationKind.VISIT,
                    source_id=source_id,
                    lat=coord[0] if coord else None,
                    lon=coord[1] if coord else None,
                    end_lat=coord[0] if coord else None,
                    end_lon=coord[1] if coord else None,
                    utc_offset_minutes=off,
                    ref=ref,
                    hints={
                        # No place NAME exists in this format -- only an id. ADR-0008.
                        "place_id": cand.get("placeId"),
                        "semantic_type": cand.get("semanticType"),
                        "probability": visit.get("probability"),
                        # Nested visits produce duplicates at identical times -- P4.
                        "hierarchy_level": visit.get("hierarchyLevel", 0),
                    },
                )
            )
            continue

        if (act := seg.get("activity")) and isinstance(act, dict):
            a = parse_lat_lng((act.get("start") or {}).get("latLng"))
            b = parse_lat_lng((act.get("end") or {}).get("latLng"))
            cand = act.get("topCandidate") or {}
            out.append(
                NormalizedObservation(
                    t=start,
                    end_t=end,
                    kind=ObservationKind.MOVE,
                    source_id=source_id,
                    lat=a[0] if a else None,
                    lon=a[1] if a else None,
                    end_lat=b[0] if b else None,
                    end_lon=b[1] if b else None,
                    utc_offset_minutes=off,
                    ref=ref,
                    hints={
                        # Hints only. The reference export reported 24 km for a ~900 km
                        # ferry crossing -- pathology P2. Distance is always recomputed.
                        "mode": cand.get("type"),
                        "provider_distance_m": act.get("distanceMeters"),
                        "probability": cand.get("probability"),
                    },
                )
            )
            continue

        if (tpath := seg.get("timelinePath")) and isinstance(tpath, list):
            # LAYER 2. Positions only -- never an event. ADR-0009.
            for j, pt in enumerate(tpath):
                if not isinstance(pt, dict):
                    continue
                c = parse_lat_lng(pt.get("point"))
                pt_t = _dt(pt.get("time")) or start
                if c is None or not _in_window(pt_t, ws, we):
                    continue
                out.append(
                    NormalizedObservation(
                        t=pt_t,
                        kind=ObservationKind.BREADCRUMB,
                        source_id=source_id,
                        lat=c[0],
                        lon=c[1],
                        utc_offset_minutes=off,
                        ref=f"{ref}.{j}",
                    )
                )

    out.sort(key=lambda o: o.t)
    return out


# --------------------------------------------------------------------------- legacy semantic


def _load_semantic_lh(
    payload: dict[str, Any],
    source_id: str,
    ws: datetime | None,
    we: datetime | None,
    report: IngestionReport,
    _s: SniffResult,
) -> list[NormalizedObservation]:
    out: list[NormalizedObservation] = []
    for i, obj in enumerate(payload.get("timelineObjects", [])):
        if not isinstance(obj, dict):
            continue
        if pv := obj.get("placeVisit"):
            dur = pv.get("duration") or {}
            start = _dt_ms(dur.get("startTimestampMs") or dur.get("startTimestamp"))
            end = _dt_ms(dur.get("endTimestampMs") or dur.get("endTimestamp"))
            loc = pv.get("location") or {}
            lat, lon = e7(loc.get("latitudeE7")), e7(loc.get("longitudeE7"))
            if start and end and _in_window(start, ws, we):
                out.append(
                    NormalizedObservation(
                        t=start,
                        end_t=end,
                        kind=ObservationKind.VISIT,
                        source_id=source_id,
                        lat=lat,
                        lon=lon,
                        end_lat=lat,
                        end_lon=lon,
                        ref=f"pv{i}",
                        hints={
                            # The legacy format DOES carry names -- a real advantage.
                            "name": loc.get("name"),
                            "address": loc.get("address"),
                            "place_id": loc.get("placeId"),
                            "hierarchy_level": 0,
                        },
                    )
                )
        elif asg := obj.get("activitySegment"):
            dur = asg.get("duration") or {}
            start = _dt_ms(dur.get("startTimestampMs") or dur.get("startTimestamp"))
            end = _dt_ms(dur.get("endTimestampMs") or dur.get("endTimestamp"))
            a, b = asg.get("startLocation") or {}, asg.get("endLocation") or {}
            if start and end and _in_window(start, ws, we):
                out.append(
                    NormalizedObservation(
                        t=start,
                        end_t=end,
                        kind=ObservationKind.MOVE,
                        source_id=source_id,
                        lat=e7(a.get("latitudeE7")),
                        lon=e7(a.get("longitudeE7")),
                        end_lat=e7(b.get("latitudeE7")),
                        end_lon=e7(b.get("longitudeE7")),
                        ref=f"as{i}",
                        hints={
                            "mode": asg.get("activityType"),
                            "provider_distance_m": asg.get("distance"),
                        },
                    )
                )
                for j, p in enumerate((asg.get("waypointPath") or {}).get("waypoints") or []):
                    la, lo = e7(p.get("latE7")), e7(p.get("lngE7"))
                    if la is not None and lo is not None:
                        out.append(
                            NormalizedObservation(
                                t=start,
                                kind=ObservationKind.BREADCRUMB,
                                source_id=source_id,
                                lat=la,
                                lon=lo,
                                ref=f"as{i}.w{j}",
                            )
                        )
    out.sort(key=lambda o: o.t)
    return out


def _dt_ms(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError):
        return _dt(value)


# --------------------------------------------------------------------------- legacy records


def _load_records(
    payload: dict[str, Any],
    source_id: str,
    ws: datetime | None,
    we: datetime | None,
    report: IngestionReport,
    _s: SniffResult,
) -> list[NormalizedObservation]:
    """Raw points only -- no provider segmentation, so everything is a breadcrumb.

    Stop/move segmentation is then entirely up to `draft/`, which is exactly why the
    builder must not depend on provider segments existing.
    """
    report.degradations.append(
        "Raw Records.json: no provider segmentation available, so stops and moves are "
        "derived entirely from Trippo's own clustering."
    )
    out: list[NormalizedObservation] = []
    for i, loc in enumerate(payload.get("locations", [])):
        if not isinstance(loc, dict):
            continue
        t = _dt_ms(loc.get("timestampMs")) or _dt(loc.get("timestamp"))
        lat, lon = e7(loc.get("latitudeE7")), e7(loc.get("longitudeE7"))
        if t is None or lat is None or lon is None or not _in_window(t, ws, we):
            continue
        out.append(
            NormalizedObservation(
                t=t,
                kind=ObservationKind.BREADCRUMB,
                source_id=source_id,
                lat=lat,
                lon=lon,
                ref=f"rec{i}",
                hints={"accuracy": loc.get("accuracy")},
            )
        )
    out.sort(key=lambda o: o.t)
    return out
