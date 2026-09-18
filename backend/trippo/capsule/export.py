"""Export a capsule as a self-contained HTML page.

One file plus a `media/` folder: opens from disk with no server, no build step and no
network beyond the map tiles. That is the whole point -- a trip you can hand to someone.

Deliberately NOT the React explorer. Shipping the studio would mean bundling a megabyte of
map engine per trip and a build pipeline into the backend. The export is a simpler reading
view of the same data: the itinerary, the photographs, the telemetry and the honest gaps.

Video is referenced but not copied, per the POC scope.
"""

from __future__ import annotations

import html
import json
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from trippo.domain.models import (
    ActivityDetail,
    EventStatus,
    EventType,
    MediaKind,
    Trip,
    UnknownDetail,
)

TYPE_ICON: dict[str, str] = {
    "drive": "&#128663;", "stop": "&#128205;", "visit": "&#127963;",
    "overnight": "&#127749;", "hike": "&#9968;", "walk": "&#128694;",
    "bike": "&#128690;", "flight": "&#9992;", "ferry": "&#9973;",
    "unknown": "&#10067;",
}


@dataclass
class ExportReport:
    photos_copied: int = 0
    bytes_written: int = 0
    videos_skipped: int = 0
    missing: int = 0

    def summary(self) -> str:
        return (
            f"{self.photos_copied} photographs ({self.bytes_written / 1_048_576:,.0f} MB)"
            + (f", {self.videos_skipped} videos referenced only" if self.videos_skipped else "")
            + (f", {self.missing} missing" if self.missing else "")
        )


def _e(s: object) -> str:
    return html.escape(str(s or ""))


def _local(dt, offset):
    return dt + timedelta(minutes=offset or 0)


def _fdate(d, long: bool = False) -> str:
    return f"{d:%A} {d.day} {d:%B}" if long else f"{d:%a} {d.day} {d:%b}"


def export_html(trip: Trip, capsule_root: Path, out_dir: Path) -> ExportReport:
    report = ExportReport()
    out_dir.mkdir(parents=True, exist_ok=True)
    media_out = out_dir / "media"
    (media_out / "thumb").mkdir(parents=True, exist_ok=True)
    (media_out / "web").mkdir(parents=True, exist_ok=True)

    for m in trip.media:
        if m.kind is MediaKind.VIDEO:
            report.videos_skipped += 1
            continue
        for ref in (m.thumb_ref, m.web_ref):
            if not ref:
                continue
            src = capsule_root / ref
            if not src.exists():
                report.missing += 1
                continue
            dst = out_dir / ref
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            report.bytes_written += dst.stat().st_size
        if m.thumb_ref:
            report.photos_copied += 1

    (out_dir / "index.html").write_text(_render(trip), encoding="utf-8")
    return report


# --------------------------------------------------------------------------- render


def _render(trip: Trip) -> str:
    s = trip.stats
    on_foot = sum(
        s.distance_by_mode_m.get(k, 0.0) for k in ("hike", "walk", "bike")
    )
    days = [d for d in trip.days if not d.excluded]

    # A tiny amount of inline script for the photo viewer. No framework, no build.
    return f"""<!doctype html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(trip.title)}</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-zinc-100 antialiased">

<header class="border-b border-white/10">
  <div class="mx-auto max-w-5xl px-6 py-14 sm:px-10">
    <p class="text-xs font-medium uppercase tracking-[0.2em] text-emerald-400">
      {_fdate(trip.date_range.start)} &ndash; {_fdate(trip.date_range.end)}
      {trip.date_range.end.year}
    </p>
    <h1 class="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">{_e(trip.title)}</h1>
    {f'<p class="mt-4 max-w-2xl text-lg leading-relaxed text-zinc-300">{_e(trip.subtitle)}</p>'
     if trip.subtitle else ''}
  </div>
</header>

<section class="border-b border-white/10 bg-zinc-900/50">
  <div class="mx-auto grid max-w-5xl grid-cols-2 gap-6 px-6 py-8 sm:grid-cols-5 sm:px-10">
    {_stat(s.day_count, 'days')}
    {_stat(f"{s.distance_by_mode_m.get('drive', 0) / 1000:,.0f} km", 'driven')}
    {_stat(f"{on_foot / 1000:,.0f} km", 'on foot')}
    {_stat(s.overnight_count, 'nights away')}
    {_stat(f"{s.photo_count:,}", 'photographs')}
  </div>
</section>

<main class="mx-auto max-w-5xl px-6 py-12 sm:px-10">
  {''.join(_day(trip, d) for d in days)}
</main>

<footer class="border-t border-white/10 bg-zinc-900/50">
  <div class="mx-auto max-w-5xl px-6 py-8 text-xs text-zinc-500 sm:px-10">
    Made with Trippo &middot; {s.photo_count:,} photographs, {s.track_count} tracks
    {f', {s.unaccounted_count} honest gaps' if s.unaccounted_count else ''}
  </div>
</footer>

<div id="viewer" class="fixed inset-0 z-50 hidden items-center justify-center bg-zinc-950/95 p-6">
  <button onclick="closeViewer()" class="absolute right-6 top-6 text-sm text-zinc-400 hover:text-white">Close &times;</button>
  <button onclick="step(-1)" class="absolute left-4 rounded-full bg-white/10 px-3 py-4 hover:bg-white/20">&larr;</button>
  <img id="viewer-img" class="max-h-full max-w-full rounded-lg object-contain" alt="">
  <button onclick="step(1)" class="absolute right-4 rounded-full bg-white/10 px-3 py-4 hover:bg-white/20">&rarr;</button>
</div>

<script>
  let shots = [], at = 0;
  function openViewer(list, i) {{
    shots = list; at = i;
    document.getElementById('viewer-img').src = shots[at];
    const v = document.getElementById('viewer');
    v.classList.remove('hidden'); v.classList.add('flex');
  }}
  function closeViewer() {{
    const v = document.getElementById('viewer');
    v.classList.add('hidden'); v.classList.remove('flex');
  }}
  function step(d) {{
    if (!shots.length) return;
    at = (at + d + shots.length) % shots.length;
    document.getElementById('viewer-img').src = shots[at];
  }}
  document.addEventListener('keydown', e => {{
    if (e.key === 'Escape') closeViewer();
    if (e.key === 'ArrowRight') step(1);
    if (e.key === 'ArrowLeft') step(-1);
  }});
</script>
</body></html>
"""


def _stat(value: object, label: str) -> str:
    return (
        '<div><div class="text-2xl font-semibold tracking-tight tabular-nums text-white">'
        f"{_e(value)}</div>"
        f'<div class="mt-1 text-[10px] uppercase tracking-wider text-zinc-500">{label}</div></div>'
    )


def _day(trip: Trip, day) -> str:
    events = [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]
    spanning = [
        e
        for e in (trip.event_by_id(i) for i in day.spanning_event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]
    if not events and not spanning:
        return ""

    return f"""
  <article class="border-t border-white/10 py-10 first:border-t-0 first:pt-0">
    <div class="flex items-baseline gap-4">
      <span class="tabular-nums text-3xl font-semibold tracking-tight text-zinc-700">
        {day.index:02d}</span>
      <div>
        <h2 class="text-xl font-semibold tracking-tight text-white">{_e(day.title)}</h2>
        <p class="mt-0.5 text-xs text-zinc-500">{_fdate(day.date, True)}
          {f' &middot; {_e(day.subtitle)}' if day.subtitle else ''}</p>
      </div>
    </div>
    {f'<p class="mt-4 max-w-2xl text-sm leading-relaxed text-zinc-300">{_e(day.note)}</p>'
     if day.note else ''}
    {''.join(_spanning(e) for e in spanning)}
    <div class="mt-6 space-y-5">{''.join(_event(trip, e) for e in events)}</div>
  </article>"""


def _spanning(e) -> str:
    name = _e(e.title or (e.place.name if e.place else "Continuing"))
    return (
        '<p class="mt-4 rounded-lg border border-dashed border-white/15 px-3 py-2 '
        f'text-xs text-zinc-500">Continues from an earlier day &middot; {name}</p>'
    )


def _event(trip: Trip, e) -> str:
    icon = TYPE_ICON.get(e.type.value, "")
    name = _e(e.title or (e.place.name if e.place else e.type.value.title()))
    start = _local(e.start, e.utc_offset_minutes)

    if e.type is EventType.UNKNOWN and isinstance(e.detail, UnknownDetail):
        return f"""
      <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
        <p class="text-sm font-medium text-amber-200">
          {e.detail.gap_hours:.0f} hours unaccounted</p>
        <p class="mt-1 text-xs leading-relaxed text-amber-200/80">
          {e.detail.displacement_km:,.0f} km that no source explains
          {f'&mdash; only {len(e.media_ids)} photographs from inside it.'
           if e.media_ids else '.'}</p>
        {_photos(trip, e)}
      </div>"""

    telemetry = ""
    if isinstance(e.detail, ActivityDetail) and e.track_ids:
        st = e.detail.stats
        peaks = " &middot; ".join(
            f"{_e(h.name)}{f' {h.ele_m:.0f} m' if h.ele_m else ''}"
            for h in e.detail.highlights
            if h.kind == "natural=peak"
        )
        telemetry = f"""
        <div class="mt-2 flex flex-wrap items-center gap-4 rounded-lg bg-white/5 px-3 py-2
                    text-xs tabular-nums text-zinc-400">
          <span class="text-emerald-400">{st.distance_m / 1000:.1f} km</span>
          <span>+{st.ascent_m:.0f} m</span>
          {f'<span>{st.max_ele_m:.0f} m highest</span>' if st.max_ele_m else ''}
          {f'<span>{st.moving_time_s / 3600:.1f} h moving</span>' if st.moving_time_s else ''}
          {f'<span class="text-zinc-300">{peaks}</span>' if peaks else ''}
        </div>"""

    return f"""
      <div>
        <div class="flex items-baseline gap-3">
          <span class="tabular-nums w-11 shrink-0 text-right font-mono text-xs text-zinc-500">
            {start:%H:%M}</span>
          <span class="text-sm">{icon}</span>
          <span class="text-sm font-medium text-white">{name}</span>
        </div>
        <div class="pl-[4.5rem]">
          {f'<p class="mt-1 text-xs leading-relaxed text-zinc-400">{_e(e.note)}</p>'
           if e.note else ''}
          {telemetry}
          {_photos(trip, e)}
        </div>
      </div>"""


def _photos(trip: Trip, e) -> str:
    by_id = {m.id: m for m in trip.media}
    shown = [
        m
        for mid in (e.selected_media_ids or e.media_ids)
        if (m := by_id.get(mid)) and m.thumb_ref and m.kind is MediaKind.PHOTO
    ]
    if not shown:
        return ""
    all_web = [m.web_ref or m.thumb_ref for m in shown]
    payload = _e(json.dumps(all_web))
    tiles = "".join(
        f'<button onclick=\'openViewer({payload}, {i})\' class="overflow-hidden rounded-lg">'
        f'<img src="{_e(m.thumb_ref)}" loading="lazy" alt="" '
        f'class="aspect-square w-full object-cover ring-1 ring-white/10 '
        f'transition hover:brightness-110"></button>'
        for i, m in enumerate(shown)
    )
    hidden = len(e.media_ids) - len(shown)
    return f"""
          <div class="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6">{tiles}</div>
          {f'<p class="mt-1.5 text-[11px] text-zinc-600">+{hidden} more not shown</p>'
           if hidden > 0 else ''}"""
