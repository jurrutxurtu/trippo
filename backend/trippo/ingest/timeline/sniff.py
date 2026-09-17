"""Timeline format sniffing. See docs/technical/ingestion.md.

Detection is on the top-level shape, which is stable across Google's export generations.
An unrecognised file is reported, never silently skipped (AGENTS.md section 5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: The on-device export stores coordinates as degree-suffixed strings, and the degree sign
#: sometimes arrives mojibaked depending on the encoding of the export. Be tolerant.
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class SniffResult:
    format: str  # on_device | semantic_lh | records | unknown
    confidence: float
    record_count: int
    note: str = ""


def sniff(payload: Any) -> SniffResult:
    if not isinstance(payload, dict):
        return SniffResult("unknown", 0.0, 0, "top level is not a JSON object")

    if isinstance(payload.get("semanticSegments"), list):
        segs = payload["semanticSegments"]
        return SniffResult("on_device", 1.0, len(segs), "Google Timeline on-device export (2024+)")

    if isinstance(payload.get("timelineObjects"), list):
        objs = payload["timelineObjects"]
        return SniffResult(
            "semantic_lh", 1.0, len(objs), "legacy Semantic Location History month file"
        )

    if isinstance(payload.get("locations"), list):
        locs = payload["locations"]
        return SniffResult("records", 1.0, len(locs), "legacy Records.json raw location points")

    return SniffResult("unknown", 0.0, 0, f"unrecognised keys: {sorted(payload)[:6]}")


def parse_lat_lng(value: str | None) -> tuple[float, float] | None:
    """Parse ``"43.248688°, -2.8871506°"`` and its mojibaked variants.

    Also accepts the ``geo:lat,lon`` form used by some exports.
    """
    if not value or not isinstance(value, str):
        return None
    nums = _NUM.findall(value)
    if len(nums) < 2:
        return None
    try:
        lat, lon = float(nums[0]), float(nums[1])
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def e7(value: Any) -> float | None:
    """Legacy exports store coordinates as integer degrees x 1e7."""
    try:
        return float(value) / 1e7
    except (TypeError, ValueError):
        return None
