"""Generate clickable HTML prototypes from a real capsule.

    python scripts/make_prototypes.py --capsule ./Ireland.capsule --out ../prototypes

These are DESIGN PROTOTYPES, not the application. Tailwind arrives via the Play CDN and
all state is static. The point is to argue about layout, density and hierarchy using real
Irish place names, real photo counts and real unaccounted gaps -- lorem ipsum hides
exactly the problems worth finding.

The production frontend (M5) is React + Vite with Tailwind compiled properly.
"""

from __future__ import annotations

import argparse
import html
from datetime import timedelta
from pathlib import Path

from trippo.capsule import io
from trippo.domain.models import EventStatus, EventType, Trip

# --------------------------------------------------------------------------- design system

#: Event types carry an icon and a muted dot. Colour is reserved for STATUS, so the eye is
#: drawn to what needs attention rather than to a rainbow of categories.
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
<style type="text/tailwindcss">
  @layer base {{ html {{ -webkit-font-smoothing: antialiased; }} }}
</style>
</head>
<body class="{body_class}">
"""

FOOT = """
<div class="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full bg-zinc-900/90 px-4 py-2
            text-xs text-zinc-300 shadow-lg ring-1 ring-white/10">
  <span class="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
  Prototype &middot; real data from Ireland 2023
  <span class="text-zinc-500">|</span>
  <a class="underline hover:text-white" href="01-new-trip.html">new</a>
  <a class="underline hover:text-white" href="02-curate.html">curate</a>
  <a class="underline hover:text-white" href="03-capsule.html">capsule</a>
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
    """Portable date formatting. %-d is glibc-only and dies on Windows."""
    if fmt == "short":  # Mon 25 Sep
        return f"{d:%a} {d.day} {d:%b}"
    if fmt == "long":  # Monday 25 September
        return f"{d:%A} {d.day} {d:%B}"
    if fmt == "dm":  # 25 September
        return f"{d.day} {d:%B}"
    return f"{d.day} {d:%B %Y}"


# --------------------------------------------------------------------------- 1. new trip


def page_new_trip(trip: Trip) -> str:
    s = trip.stats
    out = [
        HEAD.format(
            title="Trippo &middot; New trip",
            html_class="",
            body_class="min-h-screen bg-zinc-50 text-zinc-900",
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
    <div class="flex items-center gap-3 text-xs text-zinc-400">
      <span class="font-medium text-zinc-900">1 Sources</span>
      <span>&rarr;</span><span>2 Review import</span>
      <span>&rarr;</span><span>3 Curate</span>
      <span>&rarr;</span><span>4 Capsule</span>
    </div>
  </header>

  <div class="grid grid-cols-12 gap-6">

    <!-- ---------------------------------------------------------------- details -->
    <section class="col-span-4 space-y-4">
      <div class="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 class="text-sm font-semibold text-zinc-900">Trip details</h2>

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
          <label class="block">
            <span class="text-xs font-medium text-zinc-600">From</span>
            <input type="date" value="2023-09-20"
                   class="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm
                          focus:border-indigo-500 focus:ring-indigo-500">
          </label>
          <label class="block">
            <span class="text-xs font-medium text-zinc-600">To</span>
            <input type="date" value="2023-10-16"
                   class="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm
                          focus:border-indigo-500 focus:ring-indigo-500">
          </label>
        </div>
        <p class="mt-2 flex items-start gap-1.5 text-xs text-zinc-500">
          <span class="text-indigo-600">&#9679;</span>
          Proposed from your photo timestamps. Edit if the trip started earlier.
        </p>
      </div>

      <div class="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 class="text-sm font-semibold text-zinc-900">Privacy</h2>
        <label class="mt-4 flex items-start gap-3">
          <input type="checkbox" checked
                 class="mt-0.5 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500">
          <span class="text-xs leading-relaxed text-zinc-600">
            <span class="font-medium text-zinc-900">Look up place names</span><br>
            Sends coordinates to OpenStreetMap. Without this, stops are labelled by
            latitude and longitude.
          </span>
        </label>
        <label class="mt-3 flex items-start gap-3">
          <input type="checkbox"
                 class="mt-0.5 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500">
          <span class="text-xs leading-relaxed text-zinc-600">
            <span class="font-medium text-zinc-900">AI title suggestions</span><br>
            Sends curated place names and times. Never your photos or location history.
          </span>
        </label>
        <p class="mt-4 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-500">
          Originals never leave this machine.
        </p>
      </div>
    </section>

    <!-- ---------------------------------------------------------------- sources -->
    <section class="col-span-8 space-y-4">
      {_source_card(
        "Location history", "optional",
        "Timeline_2023.json", "Google Timeline &middot; on-device export",
        f"{s.coverage and 4731:,} segments &middot; 2,325 in your date range", True)}

      {_source_card(
        "GPS tracks", "optional",
        "ireland_gpx_activities/", "7 GPX files &middot; Garmin Connect",
        "County Wicklow, Down, Donegal, Galway, Clare, Kerry &times;2", True)}

      {_source_card(
        "Photos and videos", "optional",
        "Ireland/", "1,097 photos &middot; 127 videos &middot; 8.1 GB",
        "Timestamps found in all files", True)}

      <div class="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div class="flex gap-3">
          <span class="text-amber-600">&#9888;</span>
          <div class="text-xs leading-relaxed text-amber-900">
            <span class="font-semibold">No GPS data in any of your photos.</span>
            Positions will be inferred from the timeline and tracks where possible.
            If these came from a Google Photos export, re-exporting with location enabled
            would substantially improve the result.
            <button class="mt-2 block font-medium text-amber-900 underline
                           underline-offset-2">How to re-export</button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between rounded-xl border border-zinc-200
                  bg-white p-5 shadow-sm">
        <div class="text-xs text-zinc-500">
          Nothing is copied or uploaded. Trippo reads your files where they are.
        </div>
        <button class="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white
                       shadow-sm hover:bg-indigo-500 focus:outline-none focus:ring-2
                       focus:ring-indigo-500 focus:ring-offset-2">
          Build draft itinerary
        </button>
      </div>
    </section>
  </div>
</div>
""")
    out.append(FOOT)
    return "".join(out)


def _source_card(kind: str, opt: str, name: str, meta: str, detail: str, loaded: bool) -> str:
    if not loaded:
        return f"""
      <div class="rounded-xl border-2 border-dashed border-zinc-300 bg-white p-8 text-center">
        <p class="text-sm font-medium text-zinc-900">{kind}</p>
        <p class="mt-1 text-xs text-zinc-500">Drop files here, or
          <button class="font-medium text-indigo-600 underline">browse</button></p>
      </div>"""
    return f"""
      <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div class="flex items-start justify-between gap-6">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold text-zinc-900">{kind}</h3>
              <span class="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium
                           uppercase tracking-wide text-zinc-500">{opt}</span>
              <span class="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                <span class="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                read
              </span>
            </div>
            <p class="mt-2 truncate font-mono text-xs text-zinc-700">{name}</p>
            <p class="mt-1 text-xs text-zinc-500">{meta}</p>
            <p class="mt-0.5 text-xs text-zinc-400">{detail}</p>
          </div>
          <button class="shrink-0 text-xs font-medium text-zinc-500 hover:text-zinc-900">
            Replace
          </button>
        </div>
      </div>"""


# --------------------------------------------------------------------------- 2. curate


def page_curate(trip: Trip, day_index: int = 6) -> str:
    day = next(d for d in trip.days if d.index == day_index)
    events = [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]
    hidden = len(day.event_ids) - len(events)

    out = [
        HEAD.format(
            title="Trippo &middot; Curate",
            html_class="",
            body_class="h-screen overflow-hidden bg-zinc-100 text-zinc-900",
        )
    ]

    out.append(f"""
<div class="flex h-screen flex-col">

  <!-- ------------------------------------------------------------------ top bar -->
  <header class="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200
                 bg-white px-5">
    <div class="flex items-center gap-4">
      <span class="text-sm font-semibold tracking-tight">{esc(trip.title)}</span>
      <span class="text-xs text-zinc-400">
        {trip.date_range.start} &ndash; {trip.date_range.end} &middot;
        {trip.stats.day_count} days
      </span>
    </div>
    <div class="flex items-center gap-2">
      <div class="mr-3 flex items-center gap-3 text-xs">
        <span class="flex items-center gap-1.5 text-amber-700">
          <span class="inline-block h-2 w-2 rounded-full bg-amber-400"></span>
          {trip.stats.unaccounted_count} unaccounted
        </span>
        <span class="flex items-center gap-1.5 text-zinc-500">
          <span class="inline-block h-2 w-2 rounded-full bg-zinc-300"></span>
          58 to confirm
        </span>
      </div>
      <button class="rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-500
                     hover:bg-zinc-100" title="Undo (Cmd+Z)">Undo</button>
      <button class="rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-500
                     hover:bg-zinc-100">Redo</button>
      <button class="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white
                     shadow-sm hover:bg-indigo-500">Finish &amp; view capsule</button>
    </div>
  </header>

  <div class="flex min-h-0 flex-1">

    <!-- ---------------------------------------------------------------- day rail -->
    <nav class="flex w-56 shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div class="flex items-center justify-between px-4 py-3">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">Days</span>
        <button class="text-[11px] font-medium text-indigo-600 hover:underline">+ Add</button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto pb-4">
        {"".join(_day_row(trip, d, d.index == day_index) for d in trip.days)}
      </div>
    </nav>

    <!-- ---------------------------------------------------------------- events -->
    <main class="flex min-w-0 flex-1 flex-col bg-zinc-50">
      <div class="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3">
        <div>
          <h2 class="text-base font-semibold">Day {day.index}
            <span class="ml-1.5 font-normal text-zinc-400">{fdate(day.date, "long")}</span>
          </h2>
          <p class="mt-0.5 text-xs text-zinc-500">
            {len(events)} events &middot;
            {sum(len(e.media_ids) for e in events)} photos &middot;
            Mourne Mountains
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button class="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs
                         font-medium text-zinc-700 hover:bg-zinc-50">+ Add event</button>
          <button class="rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-500
                         hover:bg-zinc-100">Exclude day</button>
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        <ol class="space-y-2">
          {"".join(_event_card(trip, e, i == 3) for i, e in enumerate(events))}
        </ol>

        <button class="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border
                       border-dashed border-zinc-300 py-2.5 text-xs font-medium text-zinc-500
                       hover:border-zinc-400 hover:text-zinc-700">
          Show {hidden} hidden minor stops
        </button>
      </div>

      <!-- -------------------------------------------------------------- pool -->
      <div class="shrink-0 border-t border-zinc-200 bg-white px-6 py-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="text-xs font-semibold text-zinc-900">Unassigned</span>
            <span class="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-600">
              0 photos
            </span>
            <span class="text-[11px] text-zinc-400">
              Deleting an event returns its photos here &mdash; nothing is ever lost.
            </span>
          </div>
          <button class="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium
                         text-zinc-700 hover:bg-zinc-50">Find nearby photos&hellip;</button>
        </div>
      </div>
    </main>

    <!-- ---------------------------------------------------------------- inspector -->
    <aside class="flex w-[420px] shrink-0 flex-col border-l border-zinc-200 bg-white">
      {_inspector(trip, events[3])}
    </aside>
  </div>
</div>
""")
    out.append(FOOT)
    return "".join(out)


def _day_row(trip: Trip, day, active: bool) -> str:  # noqa: ANN001
    cov = next((c for c in trip.stats.coverage if c.date == day.date), None)
    n_active = sum(
        1
        for i in day.event_ids
        if (e := trip.event_by_id(i)) and e.status is EventStatus.ACTIVE
    )
    media = sum(len(e.media_ids) for i in day.event_ids if (e := trip.event_by_id(i)))
    has_gap = any(
        (e := trip.event_by_id(i)) and e.type is EventType.UNKNOWN for i in day.event_ids
    )

    def bar(on: bool, colour: str) -> str:
        return (
            f'<span class="h-1 w-3.5 rounded-sm {colour}"></span>'
            if on
            else '<span class="h-1 w-3.5 rounded-sm bg-zinc-200"></span>'
        )

    strip = (
        bar(bool(cov and cov.timeline_records), "bg-sky-400")
        + bar(bool(cov and cov.media_count), "bg-violet-400")
        + bar(bool(cov and cov.track_count), "bg-emerald-500")
    )
    sel = (
        "bg-indigo-50 ring-1 ring-inset ring-indigo-200"
        if active
        else "hover:bg-zinc-50"
    )
    label = (
        "text-indigo-900" if active else "text-zinc-900"
    )
    return f"""
        <button class="block w-full px-3 py-2 text-left {sel}">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold {label}">Day {day.index}</span>
            <span class="flex items-center gap-0.5">{strip}</span>
          </div>
          <div class="mt-0.5 flex items-center justify-between">
            <span class="text-[11px] text-zinc-500">{fdate(day.date, "short")}</span>
            <span class="flex items-center gap-1.5 text-[11px] text-zinc-400">
              {'<span class="text-amber-500">&#9679;</span>' if has_gap else ''}
              {n_active}&nbsp;ev
              {f'&middot; {media}&nbsp;ph' if media else ''}
            </span>
          </div>
        </button>"""


def _event_card(trip: Trip, e, selected: bool) -> str:  # noqa: ANN001
    icon, dot = TYPE_META.get(e.type.value, ("&#9679;", "bg-zinc-300"))
    start = local(e.start, e.utc_offset_minutes)
    end = local(e.end, e.utc_offset_minutes)
    mins = e.duration_s / 60
    dur = f"{mins:.0f} min" if mins < 90 else f"{mins / 60:.1f} h"
    name = esc(e.title or (e.place.name if e.place else ""))

    if e.type is EventType.UNKNOWN:
        return _gap_card(e, start, end)

    ring = (
        "ring-2 ring-indigo-500 border-transparent"
        if selected
        else "border-zinc-200 hover:border-zinc-300"
    )

    telemetry = ""
    if e.track_ids and (t := trip.track_by_id(e.track_ids[0])):
        telemetry = f"""
            <div class="mt-2 flex items-center gap-4 text-[11px] text-zinc-600">
              <span><span class="font-semibold text-zinc-900">
                {t.stats.distance_m / 1000:.1f}</span> km</span>
              <span><span class="font-semibold text-zinc-900">
                +{t.stats.ascent_m:.0f}</span> m</span>
              <span><span class="font-semibold text-zinc-900">
                {t.stats.moving_time_s / 3600:.0f}h {(t.stats.moving_time_s % 3600) / 60:.0f}m
                </span> moving</span>
              {f'<span class="text-zinc-400">{t.stats.avg_hr:.0f} bpm avg</span>'
               if t.stats.avg_hr else ''}
            </div>"""

    contested = (
        e.place
        and e.place.confidence
        and e.place.confidence < 0.9
        and e.place.source.value in ("osm", "nominatim")
    )
    badge = (
        '<span class="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium '
        'text-zinc-500" title="Trippo was unsure between two nearby places">'
        "confirm?</span>"
        if contested
        else ""
    )

    photos = ""
    if e.media_ids:
        n = len(e.media_ids)
        thumbs = "".join(
            f'<div class="h-9 w-9 shrink-0 rounded bg-gradient-to-br '
            f'from-zinc-{200 + (j % 3) * 100} to-zinc-{300 + (j % 3) * 100}"></div>'
            for j in range(min(n, 6))
        )
        photos = f"""
            <div class="mt-2.5 flex items-center gap-1.5">
              {thumbs}
              {f'<span class="ml-1 text-[11px] text-zinc-500">+{n - 6} more</span>'
               if n > 6 else ''}
            </div>"""

    return f"""
        <li class="rounded-xl border bg-white p-3.5 shadow-sm {ring}">
          <div class="flex gap-3">
            <div class="flex w-14 shrink-0 flex-col items-end pt-0.5">
              <span class="font-mono text-xs font-medium text-zinc-900">{start:%H:%M}</span>
              <span class="mt-0.5 font-mono text-[10px] text-zinc-400">{end:%H:%M}</span>
            </div>
            <div class="flex w-4 shrink-0 justify-center pt-1">
              <span class="h-2.5 w-2.5 rounded-full {dot}"></span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="truncate text-sm font-semibold text-zinc-900">{name}</span>
                    {badge}
                  </div>
                  <div class="mt-0.5 flex items-center gap-2 text-[11px] text-zinc-500">
                    <span class="capitalize">{icon} {e.type.value}</span>
                    <span class="text-zinc-300">&middot;</span>
                    <span>{dur}</span>
                    {f'<span class="text-zinc-300">&middot;</span><span>{len(e.media_ids)} photos</span>'
                     if e.media_ids else ''}
                  </div>
                </div>
                <button class="shrink-0 rounded px-1.5 text-zinc-300 hover:bg-zinc-100
                               hover:text-zinc-600">&#8942;</button>
              </div>
              {telemetry}
              {photos}
            </div>
          </div>
        </li>"""


def _gap_card(e, start, end) -> str:  # noqa: ANN001
    d = e.detail
    return f"""
        <li class="rounded-xl border-2 border-amber-300 bg-amber-50 p-4">
          <div class="flex gap-3">
            <div class="w-14 shrink-0 text-right">
              <span class="font-mono text-xs font-medium text-amber-900">{start:%H:%M}</span>
            </div>
            <div class="flex w-4 shrink-0 justify-center pt-0.5">
              <span class="text-amber-500">&#9888;</span>
            </div>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-amber-900">
                {d.gap_hours:.0f} hours unaccounted
              </p>
              <p class="mt-1 text-xs leading-relaxed text-amber-800">
                {d.displacement_km:,.0f} km of travel that no source explains.
                {f'{len(e.media_ids)} photos fall inside it.' if e.media_ids else ''}
                Trippo will not guess &mdash; what happened here?
              </p>
              <div class="mt-3 flex flex-wrap items-center gap-2">
                {"".join(
                    f'<button class="rounded-lg bg-white px-3 py-1.5 text-xs font-medium '
                    f'text-amber-900 shadow-sm ring-1 ring-amber-300 hover:bg-amber-100">'
                    f'{TYPE_META.get(t.value, ("", ""))[0]} {t.value.title()}</button>'
                    for t in d.candidate_types
                )}
                <button class="px-2 text-xs font-medium text-amber-700 underline
                               underline-offset-2">Something else&hellip;</button>
              </div>
            </div>
          </div>
        </li>"""


def _inspector(trip: Trip, e) -> str:  # noqa: ANN001
    t = trip.track_by_id(e.track_ids[0]) if e.track_ids else None
    name = esc(e.title or (e.place.name if e.place else ""))

    profile = ""
    if t:
        pts = 64
        import math

        path = " ".join(
            f"{i / (pts - 1) * 100:.1f},{40 - 34 * (0.5 + 0.5 * math.sin(i / pts * 3.14159 * 1.4 - 1.2)):.1f}"
            for i in range(pts)
        )
        profile = f"""
      <div class="border-t border-zinc-200 px-5 py-4">
        <div class="flex items-baseline justify-between">
          <h4 class="text-xs font-semibold text-zinc-900">Elevation</h4>
          <span class="text-[10px] text-zinc-400">
            gain above {t.stats.elevation_threshold_m:.0f} m steps
          </span>
        </div>
        <svg viewBox="0 0 100 42" preserveAspectRatio="none" class="mt-2 h-24 w-full">
          <polyline points="{path}" fill="none" stroke="rgb(16 185 129)" stroke-width="1.2"
                    vector-effect="non-scaling-stroke"/>
          <polygon points="0,42 {path} 100,42" fill="rgb(16 185 129)" opacity="0.10"/>
          <line x1="46" y1="0" x2="46" y2="42" stroke="rgb(113 113 122)" stroke-width="0.4"
                stroke-dasharray="1.5 1.5" vector-effect="non-scaling-stroke"/>
        </svg>
        <div class="flex justify-between text-[10px] text-zinc-400">
          <span>0 km</span>
          <span class="font-medium text-zinc-600">
            5.6 km &middot; {t.stats.max_ele_m:.0f} m
          </span>
          <span>{t.stats.distance_m / 1000:.1f} km</span>
        </div>
      </div>"""

    return f"""
      <!-- map -->
      <div class="relative h-[300px] shrink-0 bg-zinc-200">
        <div class="absolute inset-0 bg-[radial-gradient(circle_at_30%_40%,theme(colors.emerald.100),theme(colors.zinc.200))]"></div>
        <svg class="absolute inset-0 h-full w-full" viewBox="0 0 400 300">
          <path d="M60 240 C 120 210, 140 160, 190 140 S 280 90, 330 60"
                fill="none" stroke="rgb(16 185 129)" stroke-width="3" stroke-linecap="round"/>
          <circle cx="60" cy="240" r="6" fill="white" stroke="rgb(16 185 129)" stroke-width="3"/>
          <circle cx="330" cy="60" r="6" fill="rgb(16 185 129)" stroke="white" stroke-width="3"/>
          <circle cx="190" cy="140" r="9" fill="rgb(99 102 241)" stroke="white" stroke-width="2.5"/>
          <text x="204" y="144" class="text-[11px]" fill="rgb(39 39 42)">12 photos</text>
        </svg>
        <div class="absolute left-3 top-3 flex gap-1 rounded-lg bg-white/95 p-1 shadow-sm
                    ring-1 ring-black/5">
          <button class="rounded px-2.5 py-1 text-[11px] font-medium bg-zinc-900 text-white">
            Street</button>
          <button class="rounded px-2.5 py-1 text-[11px] font-medium text-zinc-600
                         hover:bg-zinc-100">Satellite</button>
        </div>
        <div class="absolute bottom-3 right-3 rounded bg-white/95 px-2 py-1 text-[10px]
                    text-zinc-500 shadow-sm ring-1 ring-black/5">
          &copy; OpenStreetMap
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <div class="px-5 py-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <input value="{name}"
                     class="w-full border-0 border-b border-transparent bg-transparent p-0
                            text-base font-semibold text-zinc-900 focus:border-indigo-500
                            focus:outline-none focus:ring-0">
              <p class="mt-1 text-xs text-zinc-500">County Down, Northern Ireland</p>
            </div>
          </div>

          <div class="mt-4">
            <span class="text-[11px] font-medium text-zinc-500">Type</span>
            <div class="mt-1.5 flex flex-wrap gap-1">
              {"".join(
                  '<button class="rounded-md px-2 py-1 text-[11px] font-medium '
                  + ('bg-zinc-900 text-white' if k == e.type.value
                     else 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200')
                  + f'">{v[0]} {k}</button>'
                  for k, v in TYPE_META.items() if k != "unknown"
              )}
            </div>
          </div>

          <label class="mt-4 block">
            <span class="text-[11px] font-medium text-zinc-500">Your note</span>
            <textarea rows="3" placeholder="Steep from the saddle. Hail at the summit&hellip;"
                      class="mt-1.5 block w-full rounded-lg border-zinc-300 text-xs
                             focus:border-indigo-500 focus:ring-indigo-500"></textarea>
          </label>
        </div>

        {profile}

        <div class="border-t border-zinc-200 px-5 py-4">
          <h4 class="text-xs font-semibold text-zinc-900">Why is this here?</h4>
          <ul class="mt-2 space-y-1.5 text-[11px] leading-relaxed text-zinc-500">
            {"".join(f'<li class="flex gap-2"><span class="text-zinc-300">&mdash;</span>'
                     f'<span>{esc(r)}</span></li>' for r in e.provenance.rules[:4])}
          </ul>
          <p class="mt-3 text-[11px] text-zinc-400">
            Source: GPX track &middot; {t.point_count if t else 0:,} points
          </p>
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

    days = [d for d in trip.days if not d.excluded][:6]

    out.append(f"""
<!-- ---------------------------------------------------------------- hero -->
<section class="relative flex h-[520px] items-end overflow-hidden">
  <div class="absolute inset-0 bg-gradient-to-br from-emerald-900 via-zinc-900 to-zinc-950"></div>
  <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,theme(colors.emerald.700/40),transparent_60%)]"></div>
  <div class="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-zinc-950 to-transparent"></div>
  <div class="relative mx-auto w-full max-w-[1200px] px-10 pb-14">
    <p class="text-xs font-medium uppercase tracking-[0.2em] text-emerald-400">
      {fdate(trip.date_range.start, "dm")} &ndash; {fdate(trip.date_range.end, "full")}
    </p>
    <h1 class="mt-3 text-6xl font-semibold tracking-tight">{esc(trip.title)}</h1>
    <p class="mt-4 max-w-2xl text-lg leading-relaxed text-zinc-300">
      Twenty-seven days around the island in the van &mdash; two long crossings of the Bay
      of Biscay, seven mountains, and a great deal of rain.
    </p>
  </div>
</section>

<!-- ---------------------------------------------------------------- stats -->
<section class="border-y border-white/10 bg-zinc-900/60">
  <div class="mx-auto grid max-w-[1200px] grid-cols-6 gap-8 px-10 py-8">
    {_stat(str(s.day_count), "days")}
    {_stat(km(s.distance_by_mode_m.get("drive", 0)), "driven")}
    {_stat(km(s.distance_by_mode_m.get("hike", 0) + s.distance_by_mode_m.get("walk", 0)), "on foot")}
    {_stat(str(s.overnight_count), "nights out")}
    {_stat(f"{s.photo_count:,}", "photos")}
    {_stat(str(s.place_count), "places")}
  </div>
</section>

<!-- ---------------------------------------------------------------- map -->
<section class="mx-auto max-w-[1200px] px-10 py-12">
  <div class="relative h-[420px] overflow-hidden rounded-2xl bg-zinc-900 ring-1 ring-white/10">
    <div class="absolute inset-0 bg-[radial-gradient(circle_at_40%_45%,theme(colors.zinc.800),theme(colors.zinc.950))]"></div>
    <svg class="absolute inset-0 h-full w-full" viewBox="0 0 1000 420">
      <path d="M300 340 C 280 300, 300 250, 340 200 S 420 120, 500 100 S 640 120, 700 180
               S 720 280, 660 330 S 480 380, 380 360 Z"
            fill="none" stroke="rgb(52 211 153)" stroke-width="2.5" opacity="0.9"/>
      <path d="M300 340 C 200 360, 120 400, 80 420" fill="none" stroke="rgb(34 211 238)"
            stroke-width="2" stroke-dasharray="7 6" opacity="0.8"/>
      {"".join(
          f'<circle cx="{300 + (i * 67) % 400}" cy="{140 + (i * 53) % 200}" r="4" '
          f'fill="rgb(52 211 153)" opacity="0.85"/>' for i in range(14)
      )}
    </svg>
    <div class="absolute bottom-4 left-4 flex gap-4 rounded-lg bg-zinc-950/80 px-4 py-2.5
                text-[11px] text-zinc-300 ring-1 ring-white/10 backdrop-blur">
      <span class="flex items-center gap-2">
        <span class="h-0.5 w-5 rounded bg-emerald-400"></span>road &amp; trail</span>
      <span class="flex items-center gap-2">
        <span class="h-0.5 w-5 rounded border-t-2 border-dashed border-cyan-400"></span>
        ferry &middot; approximate</span>
    </div>
  </div>
</section>

<!-- ---------------------------------------------------------------- days -->
<section class="mx-auto max-w-[1200px] px-10 pb-24">
  <h2 class="mb-8 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">
    Day by day
  </h2>
  <div class="space-y-16">
    {"".join(_capsule_day(trip, d) for d in days)}
  </div>
  <div class="mt-16 border-t border-white/10 pt-8 text-center">
    <button class="text-sm font-medium text-emerald-400 hover:text-emerald-300">
      Show the remaining {s.day_count - len(days)} days
    </button>
  </div>
</section>

<footer class="border-t border-white/10 bg-zinc-900/50">
  <div class="mx-auto flex max-w-[1200px] items-center justify-between px-10 py-8
              text-xs text-zinc-500">
    <span>Made with Trippo &middot; {s.photo_count:,} photos, {s.track_count} tracks</span>
    <span>Maps &copy; OpenStreetMap contributors</span>
  </div>
</footer>
""")
    out.append(FOOT)
    return "".join(out)


def _stat(value: str, label: str) -> str:
    return f"""
    <div>
      <div class="text-3xl font-semibold tracking-tight text-white">{value}</div>
      <div class="mt-1 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>"""


def _capsule_day(trip: Trip, day) -> str:  # noqa: ANN001
    events = [
        e
        for e in (trip.event_by_id(i) for i in day.event_ids)
        if e and e.status is EventStatus.ACTIVE
    ]
    named = [e for e in events if e.type not in (EventType.DRIVE, EventType.UNKNOWN)]
    media = sum(len(e.media_ids) for e in events)
    track = next(
        (trip.track_by_id(e.track_ids[0]) for e in events if e.track_ids), None
    )

    highlights = " &middot; ".join(
        esc(e.title or (e.place.name if e.place else "")) for e in named[:3]
    )

    telemetry = ""
    if track:
        telemetry = f"""
        <div class="mt-4 inline-flex items-center gap-5 rounded-lg bg-white/5 px-4 py-2.5
                    text-xs ring-1 ring-white/10">
          <span class="font-medium text-emerald-400">{esc(track.name)}</span>
          <span class="text-zinc-400">{track.stats.distance_m / 1000:.1f} km</span>
          <span class="text-zinc-400">+{track.stats.ascent_m:.0f} m</span>
          <span class="text-zinc-400">{track.stats.max_ele_m:.0f} m max</span>
        </div>"""

    gap = next((e for e in events if e.type is EventType.UNKNOWN), None)
    gap_html = ""
    if gap:
        gap_html = f"""
        <div class="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <p class="text-xs text-amber-200">
            <span class="font-semibold">{gap.detail.gap_hours:.0f} hours at sea.</span>
            No track, no signal &mdash; only {len(gap.media_ids)} photos of grey water.
          </p>
        </div>"""

    tiles = "".join(
        f'<div class="aspect-[4/3] rounded-lg bg-gradient-to-br '
        f'from-zinc-{700 + (i % 2) * 100} to-zinc-{800 + (i % 2) * 100} ring-1 ring-white/5"></div>'
        for i in range(min(max(media // 20, 3), 6))
    )

    return f"""
    <article class="grid grid-cols-12 gap-8">
      <div class="col-span-3">
        <div class="sticky top-8">
          <div class="text-5xl font-semibold tracking-tight text-zinc-700">
            {day.index:02d}
          </div>
          <div class="mt-1 text-xs uppercase tracking-wider text-zinc-500">
            {fdate(day.date, "short")}
          </div>
          <div class="mt-4 text-[11px] leading-relaxed text-zinc-600">
            {len(events)} events<br>{media} photos
          </div>
        </div>
      </div>
      <div class="col-span-9">
        <h3 class="text-2xl font-semibold tracking-tight text-white">
          {esc(day.title or (named[0].title if named else "A quiet day"))}
        </h3>
        <p class="mt-2 text-sm leading-relaxed text-zinc-400">{highlights}</p>
        {telemetry}
        {gap_html}
        <div class="mt-5 grid grid-cols-3 gap-3">{tiles}</div>
      </div>
    </article>"""


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capsule", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    trip = io.read(Path(a.capsule))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    pages = {
        "01-new-trip.html": page_new_trip(trip),
        "02-curate.html": page_curate(trip),
        "03-capsule.html": page_capsule(trip),
    }
    for name, content in pages.items():
        (out / name).write_text(content, encoding="utf-8")
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
