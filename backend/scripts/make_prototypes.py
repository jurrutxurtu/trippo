"""Generate clickable HTML prototypes from a real capsule.

    python scripts/make_prototypes.py --capsule ./Ireland.capsule --out ../prototypes

DESIGN PROTOTYPES, not the application: Tailwind arrives via the Play CDN and all state is
static. The point is to argue about layout, density and hierarchy against real Irish place
names, real photographs and real unaccounted gaps. Placeholder content hides exactly the
problems worth finding -- a 47-hour void needing a card of its own, a day at sea with no
events, a city day where every name is a war memorial.

The production frontend (M5) is React + Vite with Tailwind compiled properly (ADR-0002).

Design system encoded here
--------------------------
* Two densities. The studio is a data tool (text-xs/sm, p-3, gap-2); the capsule is
  editorial (text-lg+, p-10, gap-8). One "spacious minimal" scale would push an 11-event
  day off-screen and break keyboard curation.
* Colour means STATUS, not category. Types get an icon and a muted dot; saturated colour
  is reserved for amber=unaccounted and zinc=needs-confirming. Otherwise the three gaps
  that actually need attention stop standing out among 219 events.
* Indigo is UI chrome only. Map data uses emerald (tracks), cyan (ferry, sparse geometry)
  and zinc (road), so the accent never competes with the route.
* Three elevation levels: flat, shadow-sm cards, shadow-lg floating.
* The capsule is dark; photographs sit better on it.
"""

from __future__ import annotations

import argparse
import html
import math
from datetime import timedelta
from pathlib import Path

from trippo.capsule import io
from trippo.domain.models import EventStatus, EventType, MediaKind, Trip

TYPE_META: dict[str, tuple[str, str]] = {
    "drive": ("&#128663;", "bg-zinc-300"),
    "stop": ("&#128205;", "bg-zinc-300"),
    "visit": ("&#127963;", "bg-sky-300"),
    "overnight": ("&#127749;", "bg-violet-300"),
    "hike": ("&#9968;", "bg-emerald-400"),
    "walk": ("&#128694;", "bg-teal-300"),
    "bike": ("&#128690;", "bg-lime-300"),
    "flight": ("&#9992;", "bg-fuchsia-300"),
    "ferry": ("&#9973;", "bg-cyan-300"),
    "unknown": ("&#10067;", "bg-amber-400"),
}

HEAD = """<!doctype html>
<html lang="en" class="{html_class}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1280">
<title>{title}</title>
<script src="https://cdn.tailwindcss.com?plugins=forms"></script>
</head>
<body class="{body_class}">
"""

FOOT = """
<div class="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full bg-zinc-900/90 px-4 py-2
            text-xs text-zinc-300 shadow-lg ring-1 ring-white/10">
  <span class="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
  Prototype &middot; real Ireland 2023 data
  <span class="text-zinc-500">|</span>
  <a class="underline hover:text-white" href="index.html">index</a>
</div>
</body></html>
"""


def esc(s: object) -> str:
    return html.escape(str(s or ""))


def local(dt, offset_min):  # noqa: ANN001, ANN201
    return dt + timedelta(minutes=offset_min or 0)


def km(m: float) -> str:
    return f"{m / 1000:,.0f} km"


def fdate(d, fmt: str = "short") -> str:  # noqa: ANN001
    """Portable date formatting. `%-d` is glibc-only and dies on Windows."""
    if fmt == "short":
        return f"{d:%a} {d.day} {d:%b}"
    if fmt == "long":
        return f"{d:%A} {d.day} {d:%B}"
    if fmt == "dm":
        return f"{d.day} {d:%B}"
    return f"{d.day} {d:%B %Y}"


def active_events(trip: Trip, day) -> list:  # noqa: ANN001, ANN201
    return [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]


def day_media(trip: Trip, day, limit: int | None = None) -> list:  # noqa: ANN001, ANN201
    """Thumbnail-bearing media for a day, in capture order."""
    out = []
    for e in active_events(trip, day):
        for mid in e.media_ids:
            m = trip.media_by_id(mid)
            if m and m.thumb_ref and m.kind is MediaKind.PHOTO:
                out.append(m)
    out.sort(key=lambda m: m.captured_at or 0)
    return out[:limit] if limit else out


def rel(ref: str, depth: str = "capsule") -> str:
    """Prototype pages sit beside a `capsule/` symlink-free copy of the media folders."""
    return f"{depth}/{ref}"


# --------------------------------------------------------------------------- 1. new trip


def page_new_trip(trip: Trip) -> str:
    out = [
        HEAD.format(
            title="Trippo &middot; New trip",
            html_class="",
            body_class="min-h-screen bg-zinc-50 text-zinc-900 antialiased",
        )
    ]
    out.append(f"""
<div class="mx-auto max-w-[1400px] px-10 py-8">
  <header class="mb-8 flex items-baseline justify-between">
    <div>
      <h1 class="text-2xl font-semibold tracking-tight">New trip</h1>
      <p class="mt-1 text-sm text-zinc-500">
        Add whatever you have. Every source is optional &mdash; a folder of photos is enough.
      </p>
    </div>
    {_steps(1)}
  </header>

  <div class="grid grid-cols-12 gap-6">
    <section class="col-span-4 space-y-4">
      <div class="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 class="text-sm font-semibold">Trip details</h2>
        <label class="mt-5 block">
          <span class="text-xs font-medium text-zinc-600">Title</span>
          <input type="text" value="Ireland 2023"
                 class="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm
                        focus:border-indigo-500 focus:ring-indigo-500">
        </label>
        <label class="mt-4 block">
          <span class="text-xs font-medium text-zinc-600">Description
            <span class="font-normal text-zinc-400">&middot; optional</span></span>
          <textarea rows="3" placeholder="Three weeks around the island in the van&hellip;"
                 class="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm
                        focus:border-indigo-500 focus:ring-indigo-500"></textarea>
        </label>
        <div class="mt-4 grid grid-cols-2 gap-3">
          <label class="block"><span class="text-xs font-medium text-zinc-600">From</span>
            <input type="date" value="2023-09-20"
                   class="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm
                          focus:border-indigo-500 focus:ring-indigo-500"></label>
          <label class="block"><span class="text-xs font-medium text-zinc-600">To</span>
            <input type="date" value="2023-10-16"
                   class="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm
                          focus:border-indigo-500 focus:ring-indigo-500"></label>
        </div>
        <p class="mt-2 flex items-start gap-1.5 text-xs text-zinc-500">
          <span class="text-indigo-600">&#9679;</span>
          Proposed from your photo timestamps.
        </p>
      </div>

      <div class="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 class="text-sm font-semibold">Privacy</h2>
        <label class="mt-4 flex items-start gap-3">
          <input type="checkbox" checked
                 class="mt-0.5 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500">
          <span class="text-xs leading-relaxed text-zinc-600">
            <span class="font-medium text-zinc-900">Look up place names</span><br>
            Sends coordinates to OpenStreetMap. Without it, stops are labelled by latitude.
          </span></label>
        <label class="mt-3 flex items-start gap-3">
          <input type="checkbox"
                 class="mt-0.5 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500">
          <span class="text-xs leading-relaxed text-zinc-600">
            <span class="font-medium text-zinc-900">AI title suggestions</span><br>
            Sends place names and times. Never your photos or location history.
          </span></label>
        <p class="mt-4 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-500">
          Originals never leave this machine.
        </p>
      </div>
    </section>

    <section class="col-span-8 space-y-4">
      {_source_card("Location history", "Timeline_2023.json",
                    "Google Timeline &middot; on-device export",
                    "4,731 segments &middot; 2,325 inside your dates")}
      {_source_card("GPS tracks", "ireland_gpx_activities/",
                    "7 GPX files &middot; Garmin Connect",
                    "Wicklow, Down, Donegal, Galway, Clare, Kerry &times;2")}
      {_source_card("Photos and videos", "Ireland/",
                    "1,097 photos &middot; 127 videos &middot; 8.1 GB",
                    "Timestamps found in every file")}

      <div class="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div class="flex gap-3">
          <span class="text-amber-600">&#9888;</span>
          <div class="text-xs leading-relaxed text-amber-900">
            <span class="font-semibold">No GPS data in any of your photos.</span>
            Positions will be inferred from the timeline and tracks where possible.
            If these came from a Google Photos export, re-exporting with location enabled
            would substantially improve the result.
            <button class="mt-2 block font-medium underline underline-offset-2">
              How to re-export</button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between rounded-xl border border-zinc-200
                  bg-white p-5 shadow-sm">
        <p class="text-xs text-zinc-500">
          Nothing is copied or uploaded. Trippo reads your files where they are.</p>
        <button class="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white
                       shadow-sm hover:bg-indigo-500">Build draft itinerary</button>
      </div>
    </section>
  </div>
</div>
""")
    out.append(FOOT)
    return "".join(out)


def _steps(active: int) -> str:
    names = ["Sources", "Review import", "Curate", "Capsule"]
    bits = []
    for i, n in enumerate(names, start=1):
        cls = "font-medium text-zinc-900" if i == active else "text-zinc-400"
        bits.append(f'<span class="{cls}">{i} {n}</span>')
    return (
        '<div class="flex items-center gap-3 text-xs text-zinc-400">'
        + '<span>&rarr;</span>'.join(bits)
        + "</div>"
    )


def _source_card(kind: str, name: str, meta: str, detail: str) -> str:
    return f"""
      <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div class="flex items-start justify-between gap-6">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold">{kind}</h3>
              <span class="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium
                           uppercase tracking-wide text-zinc-500">optional</span>
              <span class="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                <span class="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>read</span>
            </div>
            <p class="mt-2 truncate font-mono text-xs text-zinc-700">{name}</p>
            <p class="mt-1 text-xs text-zinc-500">{meta}</p>
            <p class="mt-0.5 text-xs text-zinc-400">{detail}</p>
          </div>
          <button class="shrink-0 text-xs font-medium text-zinc-500 hover:text-zinc-900">
            Replace</button>
        </div>
      </div>"""


# --------------------------------------------------------------------------- 2. curate


def page_curate(trip: Trip, day_index: int, filename: str, note: str) -> str:
    day = next(d for d in trip.days if d.index == day_index)
    events = active_events(trip, day)
    spanning = [
        e
        for e in (trip.event_by_id(i) for i in day.spanning_event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]
    hidden = len(day.event_ids) - len(events)
    selected = next(
        (e for e in events if e.track_ids),
        next((e for e in events if e.media_ids), events[0] if events else None),
    )
    media = day_media(trip, day)

    out = [
        HEAD.format(
            title=f"Trippo &middot; Curate &middot; Day {day_index}",
            html_class="",
            body_class="h-screen overflow-hidden bg-zinc-100 text-zinc-900 antialiased",
        )
    ]
    out.append(f"""
<div class="flex h-screen flex-col">
  <header class="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200
                 bg-white px-5">
    <div class="flex items-center gap-4">
      <span class="text-sm font-semibold tracking-tight">{esc(trip.title)}</span>
      <span class="text-xs text-zinc-400">
        {trip.date_range.start} &ndash; {trip.date_range.end} &middot;
        {trip.stats.day_count} days</span>
      <span class="rounded bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-600">{note}</span>
    </div>
    <div class="flex items-center gap-2">
      <div class="mr-3 flex items-center gap-3 text-xs">
        <span class="flex items-center gap-1.5 text-amber-700">
          <span class="inline-block h-2 w-2 rounded-full bg-amber-400"></span>
          {trip.stats.unaccounted_count} unaccounted</span>
        <span class="flex items-center gap-1.5 text-zinc-500">
          <span class="inline-block h-2 w-2 rounded-full bg-zinc-300"></span>58 to confirm</span>
      </div>
      <button class="rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-500
                     hover:bg-zinc-100">Undo</button>
      <button class="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white
                     shadow-sm hover:bg-indigo-500">Finish &amp; view capsule</button>
    </div>
  </header>

  <div class="flex min-h-0 flex-1">
    <!-- day rail -->
    <nav class="flex w-52 shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div class="flex items-center justify-between px-3 py-2.5">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">Days</span>
        <div class="flex items-center gap-1 text-[10px] text-zinc-400">
          <span class="h-1 w-2.5 rounded-sm bg-sky-400" title="timeline"></span>
          <span class="h-1 w-2.5 rounded-sm bg-violet-400" title="photos"></span>
          <span class="h-1 w-2.5 rounded-sm bg-emerald-500" title="tracks"></span>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto pb-4">
        {"".join(_day_row(trip, d, d.index == day_index) for d in trip.days)}
      </div>
    </nav>

    <!-- events -->
    <main class="flex w-[480px] shrink-0 flex-col border-r border-zinc-200 bg-zinc-50">
      <div class="border-b border-zinc-200 bg-white px-5 py-3">
        <div class="flex items-start justify-between">
          <div>
            <h2 class="text-base font-semibold">Day {day.index}
              <span class="ml-1.5 text-sm font-normal text-zinc-400">
                {fdate(day.date, "long")}</span></h2>
            <p class="mt-0.5 text-xs text-zinc-500">
              {len(events)} events &middot; {len(media)} photos</p>
          </div>
          <button class="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs
                         font-medium text-zinc-700 hover:bg-zinc-50">+ Event</button>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {"".join(_spanning_card(e) for e in spanning)}
        {_empty_day() if not events else ""}
        <ol class="space-y-2">
          {"".join(_event_card(trip, e, e is selected) for e in events)}
        </ol>
        {f'''<button class="mt-3 flex w-full items-center justify-center rounded-lg border
             border-dashed border-zinc-300 py-2 text-xs font-medium text-zinc-500
             hover:border-zinc-400 hover:text-zinc-700">
             Show {hidden} hidden minor stops</button>''' if hidden else ""}
      </div>
      <div class="shrink-0 border-t border-zinc-200 bg-white px-4 py-2.5">
        <div class="flex items-center justify-between">
          <span class="text-[11px] text-zinc-500">
            <span class="font-semibold text-zinc-900">Unassigned</span> &middot; 0 photos
          </span>
          <button class="rounded-lg border border-zinc-300 px-2.5 py-1 text-[11px]
                         font-medium text-zinc-700 hover:bg-zinc-50">Find nearby&hellip;</button>
        </div>
      </div>
    </main>

    <!-- map: persistent, full height -->
    <section class="relative min-w-0 flex-1 bg-zinc-200">
      {_map(trip, day, events)}
    </section>

    <!-- inspector -->
    <aside class="flex w-[340px] shrink-0 flex-col border-l border-zinc-200 bg-white">
      {_inspector(trip, selected, media) if selected else _inspector_empty()}
    </aside>
  </div>
</div>
""")
    out.append(FOOT)
    return "".join(out)


def _day_row(trip: Trip, day, active: bool) -> str:  # noqa: ANN001
    cov = next((c for c in trip.stats.coverage if c.date == day.date), None)
    n = len(active_events(trip, day))
    media = sum(
        len(e.media_ids) for i in day.event_ids if (e := trip.event_by_id(i))
    )
    has_gap = any(
        (e := trip.event_by_id(i)) and e.type is EventType.UNKNOWN
        for i in (*day.event_ids, *day.spanning_event_ids)
    )

    def bar(on: bool, colour: str) -> str:
        return f'<span class="h-1 w-3 rounded-sm {colour if on else "bg-zinc-200"}"></span>'

    strip = (
        bar(bool(cov and cov.timeline_records), "bg-sky-400")
        + bar(bool(cov and cov.media_count), "bg-violet-400")
        + bar(bool(cov and cov.track_count), "bg-emerald-500")
    )
    sel = "bg-indigo-50 ring-1 ring-inset ring-indigo-200" if active else "hover:bg-zinc-50"
    return f"""
        <a href="02-curate-day{day.index}.html" class="block w-full px-3 py-1.5 text-left {sel}">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold {'text-indigo-900' if active else 'text-zinc-900'}">
              Day {day.index}</span>
            <span class="flex items-center gap-0.5">{strip}</span>
          </div>
          <div class="mt-0.5 flex items-center justify-between">
            <span class="text-[11px] text-zinc-500">{fdate(day.date)}</span>
            <span class="flex items-center gap-1 text-[11px] text-zinc-400">
              {'<span class="text-amber-500">&#9679;</span>' if has_gap else ''}
              {n} ev{f' &middot; {media} ph' if media else ''}
            </span>
          </div>
        </a>"""


def _spanning_card(e) -> str:  # noqa: ANN001
    name = esc(e.title or (e.place.name if e.place else "Continuing"))
    return f"""
        <div class="mb-2 rounded-lg border border-dashed border-zinc-300 bg-white/60 px-3 py-2">
          <p class="text-[11px] text-zinc-500">
            <span class="font-medium text-zinc-700">Continues from an earlier day</span>
            &middot; {name}
          </p>
        </div>"""


def _empty_day() -> str:
    return """
        <div class="rounded-xl border border-zinc-200 bg-white px-5 py-10 text-center shadow-sm">
          <p class="text-sm font-medium text-zinc-900">Nothing recorded on this day</p>
          <p class="mx-auto mt-1.5 max-w-xs text-xs leading-relaxed text-zinc-500">
            No timeline data, no photos, no tracks. The crossing above accounts for it.
          </p>
          <button class="mt-4 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs
                         font-medium text-zinc-700 hover:bg-zinc-50">
            Add an event by hand</button>
        </div>"""


def _event_card(trip: Trip, e, selected: bool) -> str:  # noqa: ANN001
    icon, dot = TYPE_META.get(e.type.value, ("&#9679;", "bg-zinc-300"))
    start = local(e.start, e.utc_offset_minutes)
    mins = e.duration_s / 60
    dur = f"{mins:.0f} min" if mins < 90 else f"{mins / 60:.1f} h"
    name = esc(e.title or (e.place.name if e.place else ""))

    if e.type is EventType.UNKNOWN:
        return _gap_card(e, start)

    ring = (
        "ring-2 ring-indigo-500 border-transparent"
        if selected
        else "border-zinc-200 hover:border-zinc-300"
    )
    telemetry = ""
    if e.track_ids and (t := trip.track_by_id(e.track_ids[0])):
        telemetry = f"""
            <div class="mt-1.5 flex items-center gap-3 text-[11px] tabular-nums text-zinc-600">
              <span><b class="font-semibold text-zinc-900">{t.stats.distance_m / 1000:.1f}</b> km</span>
              <span><b class="font-semibold text-zinc-900">+{t.stats.ascent_m:.0f}</b> m</span>
              <span><b class="font-semibold text-zinc-900">{t.stats.moving_time_s / 3600:.1f}</b> h</span>
            </div>"""

    contested = (
        e.place and e.place.confidence < 0.9 and e.place.source.value in ("osm", "nominatim")
    )
    badge = (
        '<span class="shrink-0 rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium '
        'text-zinc-500">confirm?</span>' if contested else ""
    )

    strip = ""
    thumbs = [
        m for mid in e.media_ids if (m := trip.media_by_id(mid)) and m.thumb_ref
    ][:7]
    if thumbs:
        tiles = "".join(
            f'<img src="{rel(m.thumb_ref)}" loading="lazy" alt=""'
            f' class="h-10 w-10 shrink-0 rounded object-cover ring-1 ring-black/5">'
            for m in thumbs
        )
        more = len(e.media_ids) - len(thumbs)
        strip = f"""
            <div class="mt-2 flex items-center gap-1">
              {tiles}
              {f'<span class="ml-1 text-[11px] text-zinc-400">+{more}</span>' if more > 0 else ''}
            </div>"""

    return f"""
        <li class="rounded-xl border bg-white p-3 shadow-sm {ring}">
          <div class="flex gap-2.5">
            <div class="w-11 shrink-0 pt-0.5 text-right">
              <span class="font-mono text-xs font-medium tabular-nums text-zinc-900">
                {start:%H:%M}</span>
            </div>
            <div class="flex w-3 shrink-0 justify-center pt-1">
              <span class="h-2 w-2 rounded-full {dot}"></span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-2">
                <span class="truncate text-sm font-semibold text-zinc-900">{name}</span>
                {badge}
              </div>
              <div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-zinc-500">
                <span class="capitalize">{icon} {e.type.value}</span>
                <span class="text-zinc-300">&middot;</span><span>{dur}</span>
                {f'<span class="text-zinc-300">&middot;</span><span>{len(e.media_ids)} ph</span>'
                 if e.media_ids else ''}
              </div>
              {telemetry}{strip}
            </div>
          </div>
        </li>"""


def _gap_card(e, start) -> str:  # noqa: ANN001
    d = e.detail
    buttons = "".join(
        f'<button class="rounded-lg bg-white px-2.5 py-1.5 text-xs font-medium text-amber-900 '
        f'shadow-sm ring-1 ring-amber-300 hover:bg-amber-100">'
        f'{TYPE_META.get(t.value, ("", ""))[0]} {t.value.title()}</button>'
        for t in d.candidate_types
    )
    return f"""
        <li class="rounded-xl border-2 border-amber-300 bg-amber-50 p-3.5 shadow-sm">
          <div class="flex gap-2.5">
            <div class="w-11 shrink-0 text-right">
              <span class="font-mono text-xs font-medium tabular-nums text-amber-900">
                {start:%H:%M}</span></div>
            <div class="flex w-3 shrink-0 justify-center"><span class="text-amber-500">&#9888;</span></div>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-amber-900">
                {d.gap_hours:.0f} hours unaccounted</p>
              <p class="mt-1 text-xs leading-relaxed text-amber-800">
                {d.displacement_km:,.0f} km of travel that no source explains.
                {f'{len(e.media_ids)} photos fall inside it.' if e.media_ids else ''}
                Trippo will not guess &mdash; what happened here?</p>
              <div class="mt-2.5 flex flex-wrap items-center gap-1.5">{buttons}
                <button class="px-1.5 text-xs font-medium text-amber-700 underline
                               underline-offset-2">Other&hellip;</button></div>
            </div>
          </div>
        </li>"""


def _map(trip: Trip, day, events: list) -> str:  # noqa: ANN001
    """A stylised map. The real thing is MapLibre (ADR-0006); this argues for the layout."""
    track = next(
        (trip.track_by_id(e.track_ids[0]) for e in events if e.track_ids), None
    )
    has_gap = any(e.type is EventType.UNKNOWN for e in events)

    if track:
        path = ("M70 320 C 150 300, 180 230, 250 200 S 380 140, 460 90")
        overlay = f"""
          <path d="{path}" fill="none" stroke="white" stroke-width="7" stroke-linecap="round"
                opacity="0.85"/>
          <path d="{path}" fill="none" stroke="rgb(5 150 105)" stroke-width="3.5"
                stroke-linecap="round"/>
          <circle cx="70" cy="320" r="7" fill="white" stroke="rgb(5 150 105)" stroke-width="3"/>
          <circle cx="460" cy="90" r="7" fill="rgb(5 150 105)" stroke="white" stroke-width="3"/>"""
        caption = f"{esc(track.name)} &middot; {track.stats.distance_m / 1000:.1f} km"
    elif has_gap:
        overlay = """
          <path d="M80 340 C 200 300, 340 200, 470 90" fill="none" stroke="rgb(245 158 11)"
                stroke-width="3" stroke-dasharray="10 9" stroke-linecap="round" opacity="0.9"/>
          <circle cx="80" cy="340" r="7" fill="white" stroke="rgb(245 158 11)" stroke-width="3"/>
          <circle cx="470" cy="90" r="7" fill="rgb(245 158 11)" stroke="white" stroke-width="3"/>"""
        caption = "Unaccounted &middot; route unknown"
    else:
        overlay = """
          <path d="M90 300 C 180 280, 240 220, 320 190 S 430 150, 480 120" fill="none"
                stroke="white" stroke-width="7" stroke-linecap="round" opacity="0.85"/>
          <path d="M90 300 C 180 280, 240 220, 320 190 S 430 150, 480 120" fill="none"
                stroke="rgb(113 113 122)" stroke-width="3.5" stroke-linecap="round"/>"""
        caption = "City walking &middot; 14 stops"

    pins = "".join(
        f'<circle cx="{110 + (i * 71) % 400}" cy="{110 + (i * 97) % 260}" r="8" '
        f'fill="rgb(99 102 241)" stroke="white" stroke-width="2.5" opacity="0.95"/>'
        for i, e in enumerate(events)
        if e.media_ids
    )

    return f"""
      <div class="absolute inset-0 bg-[radial-gradient(circle_at_35%_45%,theme(colors.emerald.50),theme(colors.zinc.200))]"></div>
      <svg class="absolute inset-0 h-full w-full" viewBox="0 0 560 420" preserveAspectRatio="xMidYMid slice">
        <g opacity="0.35" stroke="rgb(161 161 170)" stroke-width="1">
          <path d="M0 150 H560 M0 260 H560 M170 0 V420 M390 0 V420" fill="none"/>
        </g>
        {overlay}{pins}
      </svg>

      <div class="absolute left-4 top-4 flex gap-1 rounded-lg bg-white/95 p-1 shadow-lg
                  ring-1 ring-black/5">
        <button class="rounded bg-zinc-900 px-3 py-1.5 text-[11px] font-medium text-white">
          Street</button>
        <button class="rounded px-3 py-1.5 text-[11px] font-medium text-zinc-600
                       hover:bg-zinc-100">Satellite</button>
      </div>

      <div class="absolute right-4 top-4 flex flex-col gap-1 rounded-lg bg-white/95 p-1
                  shadow-lg ring-1 ring-black/5">
        <button class="h-7 w-7 rounded text-sm text-zinc-600 hover:bg-zinc-100">+</button>
        <button class="h-7 w-7 rounded text-sm text-zinc-600 hover:bg-zinc-100">&minus;</button>
      </div>

      <div class="absolute bottom-4 left-4 rounded-lg bg-white/95 px-3 py-2 text-[11px]
                  text-zinc-600 shadow-lg ring-1 ring-black/5">
        {caption}
      </div>
      <div class="absolute bottom-4 right-4 rounded bg-white/90 px-2 py-1 text-[10px]
                  text-zinc-500">&copy; OpenStreetMap</div>"""


def _inspector_empty() -> str:
    return """
      <div class="flex h-full items-center justify-center p-8 text-center">
        <p class="text-xs text-zinc-400">Select an event to inspect it.</p>
      </div>"""


def _inspector(trip: Trip, e, media: list) -> str:  # noqa: ANN001
    t = trip.track_by_id(e.track_ids[0]) if e.track_ids else None
    name = esc(e.title or (e.place.name if e.place else ""))

    profile = ""
    if t:
        pts = 72
        coords = [
            (
                i / (pts - 1) * 100,
                38 - 32 * (0.5 + 0.5 * math.sin(i / pts * math.pi * 1.4 - 1.2)),
            )
            for i in range(pts)
        ]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        profile = f"""
        <div class="border-t border-zinc-200 px-4 py-3">
          <div class="flex items-baseline justify-between">
            <h4 class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
              Elevation</h4>
            <span class="text-[10px] text-zinc-400">
              gain above {t.stats.elevation_threshold_m:.0f} m steps</span>
          </div>
          <svg viewBox="0 0 100 40" preserveAspectRatio="none" class="mt-2 h-20 w-full">
            <polygon points="0,40 {path} 100,40" fill="rgb(5 150 105)" opacity="0.12"/>
            <polyline points="{path}" fill="none" stroke="rgb(5 150 105)" stroke-width="1.2"
                      vector-effect="non-scaling-stroke"/>
            <line x1="46" y1="0" x2="46" y2="40" stroke="rgb(99 102 241)" stroke-width="0.6"
                  vector-effect="non-scaling-stroke"/>
          </svg>
          <div class="flex justify-between text-[10px] tabular-nums text-zinc-400">
            <span>0 km</span>
            <span class="font-medium text-zinc-700">{t.stats.max_ele_m:.0f} m max</span>
            <span>{t.stats.distance_m / 1000:.1f} km</span>
          </div>
        </div>"""

    strip = ""
    thumbs = [m for mid in e.media_ids if (m := trip.media_by_id(mid)) and m.thumb_ref]
    if thumbs:
        tiles = "".join(
            f'<img src="{rel(m.thumb_ref)}" loading="lazy" alt=""'
            f' class="aspect-square w-full rounded object-cover ring-1 ring-black/5">'
            for m in thumbs[:12]
        )
        strip = f"""
        <div class="border-t border-zinc-200 px-4 py-3">
          <div class="flex items-baseline justify-between">
            <h4 class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
              Photos</h4>
            <span class="text-[10px] text-zinc-400">{len(thumbs)} attached</span>
          </div>
          <div class="mt-2 grid grid-cols-4 gap-1">{tiles}</div>
          <button class="mt-2 w-full rounded-lg border border-zinc-300 py-1.5 text-[11px]
                         font-medium text-zinc-700 hover:bg-zinc-50">Move to&hellip;</button>
        </div>"""

    types = "".join(
        '<button class="rounded-md px-2 py-1 text-[11px] font-medium '
        + ("bg-zinc-900 text-white" if k == e.type.value
           else "bg-zinc-100 text-zinc-600 hover:bg-zinc-200")
        + f'">{v[0]} {k}</button>'
        for k, v in TYPE_META.items()
        if k != "unknown"
    )
    rules = "".join(
        f'<li class="flex gap-1.5"><span class="text-zinc-300">&mdash;</span>'
        f"<span>{esc(r)}</span></li>"
        for r in e.provenance.rules[:4]
    )

    return f"""
      <div class="min-h-0 flex-1 overflow-y-auto">
        <div class="px-4 py-3">
          <input value="{name}"
                 class="w-full border-0 border-b border-transparent bg-transparent p-0
                        text-sm font-semibold text-zinc-900 focus:border-indigo-500
                        focus:outline-none focus:ring-0">
          <p class="mt-1 text-[11px] text-zinc-500">
            {esc((e.place.category or "").replace("=", " &middot; ")) if e.place else ""}
          </p>
          <div class="mt-3">
            <span class="text-[11px] font-medium text-zinc-500">Type</span>
            <div class="mt-1.5 flex flex-wrap gap-1">{types}</div>
          </div>
          <label class="mt-3 block">
            <span class="text-[11px] font-medium text-zinc-500">Your note</span>
            <textarea rows="2" placeholder="Hail at the summit&hellip;"
                      class="mt-1.5 block w-full rounded-lg border-zinc-300 text-xs
                             focus:border-indigo-500 focus:ring-indigo-500"></textarea>
          </label>
        </div>
        {profile}{strip}
        <div class="border-t border-zinc-200 px-4 py-3">
          <h4 class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            Why is this here?</h4>
          <ul class="mt-2 space-y-1 text-[11px] leading-relaxed text-zinc-500">{rules}</ul>
        </div>
      </div>"""


# --------------------------------------------------------------------------- 3. capsule


def page_capsule(trip: Trip) -> str:
    s = trip.stats
    out = [
        HEAD.format(
            title=f"{esc(trip.title)} &middot; Trippo",
            html_class="dark",
            body_class="bg-zinc-950 text-zinc-100 antialiased",
        )
    ]

    hero = day_media(trip, trip.days[7], 1)
    hero_src = rel(hero[0].thumb_ref) if hero else ""
    all_days = [d for d in trip.days if not d.excluded]

    out.append(f"""
<section class="relative flex h-[560px] items-end overflow-hidden">
  {f'<img src="{hero_src}" class="absolute inset-0 h-full w-full object-cover opacity-40" alt="">'
   if hero_src else ''}
  <div class="absolute inset-0 bg-gradient-to-t from-zinc-950 via-zinc-950/70 to-zinc-950/30"></div>
  <div class="relative mx-auto w-full max-w-[1200px] px-10 pb-14">
    <p class="text-xs font-medium uppercase tracking-[0.2em] text-emerald-400">
      {fdate(trip.date_range.start, "dm")} &ndash; {fdate(trip.date_range.end, "full")}</p>
    <h1 class="mt-3 text-6xl font-semibold tracking-tight">{esc(trip.title)}</h1>
    <p class="mt-4 max-w-2xl text-lg leading-relaxed text-zinc-300">
      Twenty-seven days around the island in the van &mdash; two long crossings of the Bay
      of Biscay, seven mountains, and a great deal of rain.</p>
  </div>
</section>

<section class="border-y border-white/10 bg-zinc-900/60">
  <div class="mx-auto grid max-w-[1200px] grid-cols-6 gap-8 px-10 py-8">
    {_stat(str(s.day_count), "days")}
    {_stat(km(s.distance_by_mode_m.get("drive", 0)), "driven")}
    {_stat(km(s.distance_by_mode_m.get("hike", 0) + s.distance_by_mode_m.get("walk", 0)), "on foot")}
    {_stat(str(s.overnight_count), "nights out")}
    {_stat(f"{s.photo_count:,}", "photos")}
    {_stat(str(s.track_count), "tracks")}
  </div>
</section>

<section class="mx-auto max-w-[1200px] px-10 py-12">
  <div class="relative h-[420px] overflow-hidden rounded-2xl bg-zinc-900 ring-1 ring-white/10">
    <div class="absolute inset-0 bg-[radial-gradient(circle_at_42%_45%,theme(colors.zinc.800),theme(colors.zinc.950))]"></div>
    <svg class="absolute inset-0 h-full w-full" viewBox="0 0 1000 420">
      <path d="M430 330 C 380 280, 360 210, 400 150 S 500 70, 580 90 S 660 160, 640 240
               S 540 360, 470 345 Z" fill="none" stroke="rgb(52 211 153)" stroke-width="2.5"/>
      <path d="M430 335 C 340 370, 220 400, 120 415" fill="none" stroke="rgb(34 211 238)"
            stroke-width="2" stroke-dasharray="8 7"/>
      {"".join(f'<circle cx="{400 + (i * 83) % 260}" cy="{110 + (i * 61) % 230}" r="3.5" '
               f'fill="rgb(52 211 153)" opacity="0.8"/>' for i in range(22))}
    </svg>
    <div class="absolute bottom-4 left-4 flex gap-4 rounded-lg bg-zinc-950/80 px-4 py-2.5
                text-[11px] text-zinc-300 ring-1 ring-white/10 backdrop-blur">
      <span class="flex items-center gap-2">
        <span class="h-0.5 w-5 rounded bg-emerald-400"></span>road &amp; trail</span>
      <span class="flex items-center gap-2">
        <span class="h-0.5 w-5 border-t-2 border-dashed border-cyan-400"></span>
        ferry &middot; approximate</span>
    </div>
  </div>
</section>

<section class="mx-auto max-w-[1200px] px-10 pb-24">
  <h2 class="mb-10 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">
    Day by day</h2>
  <div class="space-y-20">
    {"".join(_capsule_day(trip, d) for d in all_days)}
  </div>
</section>

<footer class="border-t border-white/10 bg-zinc-900/50">
  <div class="mx-auto flex max-w-[1200px] items-center justify-between px-10 py-8
              text-xs text-zinc-500">
    <span>Made with Trippo &middot; {s.photo_count:,} photos, {s.track_count} tracks,
      {s.unaccounted_count} honest gaps</span>
    <span>Maps &copy; OpenStreetMap contributors</span>
  </div>
</footer>
""")
    out.append(FOOT)
    return "".join(out)


def _stat(value: str, label: str) -> str:
    return f"""
    <div>
      <div class="text-3xl font-semibold tracking-tight tabular-nums text-white">{value}</div>
      <div class="mt-1 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>"""


def _capsule_day(trip: Trip, day) -> str:  # noqa: ANN001
    events = active_events(trip, day)
    spanning = [
        e
        for e in (trip.event_by_id(i) for i in day.spanning_event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]
    named = [
        e
        for e in events
        if e.type not in (EventType.DRIVE, EventType.UNKNOWN) and (e.title or e.place)
    ]
    media = day_media(trip, day)
    track = next((trip.track_by_id(e.track_ids[0]) for e in events if e.track_ids), None)
    gap = next((e for e in [*events, *spanning] if e.type is EventType.UNKNOWN), None)

    # --- a day with nothing of its own, covered by a crossing
    if not events and spanning:
        return f"""
    <article class="grid grid-cols-12 gap-8 opacity-70">
      <div class="col-span-3">
        <div class="text-5xl font-semibold tracking-tight tabular-nums text-zinc-800">
          {day.index:02d}</div>
        <div class="mt-1 text-xs uppercase tracking-wider text-zinc-600">
          {fdate(day.date)}</div>
      </div>
      <div class="col-span-9 border-l border-white/5 pl-8">
        <h3 class="text-xl font-medium tracking-tight text-zinc-400">At sea</h3>
        <p class="mt-2 max-w-xl text-sm leading-relaxed text-zinc-500">
          Nothing was recorded on this day. The crossing that began the day before accounts
          for all of it.</p>
      </div>
    </article>"""

    title = esc(day.title or (named[0].title if named else "A quiet day"))
    highlights = " &middot; ".join(
        esc(e.title or (e.place.name if e.place else "")) for e in named[:4]
    )

    telemetry = ""
    if track:
        telemetry = f"""
        <div class="mt-4 inline-flex flex-wrap items-center gap-5 rounded-lg bg-white/5 px-4
                    py-2.5 text-xs ring-1 ring-white/10">
          <span class="font-medium text-emerald-400">{esc(track.name)}</span>
          <span class="tabular-nums text-zinc-400">{track.stats.distance_m / 1000:.1f} km</span>
          <span class="tabular-nums text-zinc-400">+{track.stats.ascent_m:.0f} m</span>
          <span class="tabular-nums text-zinc-400">{track.stats.max_ele_m:.0f} m max</span>
          {f'<span class="tabular-nums text-zinc-500">{track.stats.avg_hr:.0f} bpm</span>'
           if track.stats.avg_hr else ''}
        </div>"""

    gap_html = ""
    if gap:
        gap_html = f"""
        <div class="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <p class="text-xs leading-relaxed text-amber-200">
            <span class="font-semibold">{gap.detail.gap_hours:.0f} hours unaccounted.</span>
            {gap.detail.displacement_km:,.0f} km that no source explains
            {f'&mdash; only {len(gap.media_ids)} photographs from inside it.'
             if gap.media_ids else '.'}
          </p>
        </div>"""

    grid = ""
    if media:
        big = media[0]
        rest = media[1:9]
        tiles = "".join(
            f'<img src="{rel(m.thumb_ref)}" loading="lazy" alt=""'
            f' class="aspect-square w-full rounded-lg object-cover ring-1 ring-white/10">'
            for m in rest
        )
        more = len(media) - 1 - len(rest)
        grid = f"""
        <div class="mt-6 grid grid-cols-4 gap-2">
          <img src="{rel(big.thumb_ref)}" loading="lazy" alt=""
               class="col-span-2 row-span-2 aspect-square w-full rounded-lg object-cover
                      ring-1 ring-white/10">
          {tiles}
        </div>
        {f'<p class="mt-2 text-[11px] text-zinc-600">+{more} more photographs</p>'
         if more > 0 else ''}"""

    return f"""
    <article class="grid grid-cols-12 gap-8">
      <div class="col-span-3">
        <div class="sticky top-8">
          <div class="text-5xl font-semibold tracking-tight tabular-nums text-zinc-700">
            {day.index:02d}</div>
          <div class="mt-1 text-xs uppercase tracking-wider text-zinc-500">
            {fdate(day.date)}</div>
          <div class="mt-4 space-y-0.5 text-[11px] leading-relaxed text-zinc-600">
            <div>{len(events)} events</div>
            {f'<div>{len(media)} photos</div>' if media else ''}
          </div>
        </div>
      </div>
      <div class="col-span-9 border-l border-white/5 pl-8">
        <h3 class="text-2xl font-semibold tracking-tight text-white">{title}</h3>
        {f'<p class="mt-2 text-sm leading-relaxed text-zinc-400">{highlights}</p>'
         if highlights else ''}
        {telemetry}{gap_html}{grid}
      </div>
    </article>"""


# --------------------------------------------------------------------------- index


def page_index(trip: Trip, curate_days: list[tuple[int, str, str]]) -> str:
    links = "".join(
        f"""
    <a href="{fn}" class="block rounded-xl border border-white/10 bg-zinc-900 p-4
                          hover:border-white/20">
      <div class="flex items-baseline gap-3">
        <span class="font-mono text-xs text-zinc-500">Day {idx}</span>
        <span class="text-sm font-medium">{esc(note)}</span>
      </div>
    </a>"""
        for idx, fn, note in curate_days
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Trippo &middot; prototypes</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
<div class="mx-auto max-w-3xl px-10 py-20">
  <h1 class="text-3xl font-semibold tracking-tight">Trippo &middot; design prototypes</h1>
  <p class="mt-3 text-sm leading-relaxed text-zinc-400">
    Static HTML generated from the real Ireland 2023 capsule &mdash; real place names, real
    photographs, real unaccounted gaps. Tailwind via the Play CDN; nothing is interactive.
  </p>

  <h2 class="mt-12 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">Flow</h2>
  <div class="mt-4 space-y-3">
    <a href="01-new-trip.html" class="block rounded-xl border border-white/10 bg-zinc-900 p-5
                                      hover:border-white/20">
      <div class="flex items-baseline gap-3"><span class="font-mono text-xs text-zinc-500">01</span>
        <span class="text-base font-medium">New trip</span></div>
      <p class="mt-1.5 text-xs text-zinc-400">
        Details, sources, privacy &mdash; and the stripped-GPS warning before any claim is made.</p>
    </a>
    <a href="03-capsule.html" class="block rounded-xl border border-white/10 bg-zinc-900 p-5
                                     hover:border-white/20">
      <div class="flex items-baseline gap-3"><span class="font-mono text-xs text-zinc-500">03</span>
        <span class="text-base font-medium">Capsule</span>
        <span class="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium
                     text-emerald-400">all {trip.stats.day_count} days, real photos</span></div>
      <p class="mt-1.5 text-xs text-zinc-400">
        The finished read view. Dark, because photographs sit better on it.</p>
    </a>
  </div>

  <h2 class="mt-12 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">
    02 &middot; Curate &mdash; three days worth arguing about</h2>
  <div class="mt-4 space-y-3">{links}</div>

  <p class="mt-12 text-xs leading-relaxed text-zinc-600">
    Thumbnails are real, generated by <code class="rounded bg-zinc-800 px-1.5 py-0.5">
    trippo.ingest.media.derivatives</code>: 1,097 photos, 3.4&nbsp;GB of originals reduced to
    9&nbsp;MB of 256&nbsp;px WebP. Maps are stylised &mdash; MapLibre lands in M6.
  </p>
</div></body></html>
"""


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capsule", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    trip = io.read(Path(a.capsule))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # Pick three days that stress the layout differently.
    best_day = max(
        trip.days,
        key=lambda d: (
            any(e.track_ids for e in active_events(trip, d)),
            len(day_media(trip, d)),
        ),
    )
    empty_day = next(
        (d for d in trip.days if not active_events(trip, d) and d.spanning_event_ids),
        trip.days[2],
    )
    busy_day = max(trip.days, key=lambda d: len(active_events(trip, d)))

    variants = [
        (best_day.index, "a good day: GPX hike, telemetry, photographs"),
        (busy_day.index, "the awkward day: many stops, contested names"),
        (empty_day.index, "the empty day: at sea, nothing recorded"),
    ]

    pages: dict[str, str] = {
        "01-new-trip.html": page_new_trip(trip),
        "03-capsule.html": page_capsule(trip),
    }
    # Generate every day so the rail is genuinely clickable; highlight the three that
    # stress the layout in different ways.
    notes = dict(variants)
    for d in trip.days:
        fn = f"02-curate-day{d.index}.html"
        pages[fn] = page_curate(trip, d.index, fn, notes.get(d.index, ""))

    links = [(i, f"02-curate-day{i}.html", n) for i, n in variants]
    pages["index.html"] = page_index(trip, links)

    for name, content in pages.items():
        (out / name).write_text(content, encoding="utf-8")
        print(f"wrote {out / name}")

    print(
        "\nNOTE: copy or link the capsule's media folder next to these pages:\n"
        f"  {out / 'capsule'}  ->  <capsule>/media"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
