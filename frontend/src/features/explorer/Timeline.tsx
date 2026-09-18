import { useState } from "react";
import { useTrip, selectedDay, selectedEvent, dayEvents, spanningEvents } from "@/store/trip";
import {
  TYPE_META,
  duration,
  eventName,
  formatDate,
  isContested,
  km,
  localTime,
  dayDistance,
} from "@/lib/format";
import type { Day, Trip, TripEvent } from "@/lib/types";
import { ActivityPanel } from "@/features/activity/ActivityPanel";
import { PhotoStrip } from "@/components/PhotoStrip";
import { EventEditor, GapResolver } from "@/features/curate/EventEditor";
import { ReviewPanel } from "@/features/curate/ReviewPanel";
import { Toolbar } from "@/features/curate/Toolbar";
import { TitleSuggester } from "@/features/curate/TitleSuggester";
import { DayEditor } from "@/features/curate/DayEditor";
import { FindNearby } from "@/features/curate/FindNearby";
import { PhotoPicker } from "@/features/curate/PhotoPicker";

/** The left pane. Collapsed days at trip scope, expanded events at day scope. */
export function Timeline() {
  const state = useTrip();
  const { trip, scope } = state;
  const day = selectedDay(state);
  const event = selectedEvent(state);
  const [tab, setTab] = useState<"days" | "review">("days");
  if (!trip) return null;

  return (
    <div className="flex h-full flex-col bg-white">
      <Toolbar />
      <Header trip={trip} />
      {scope === "trip" && (
        <div className="flex shrink-0 gap-1 border-b border-zinc-200 px-5 py-1.5">
          {(["days", "review"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-2.5 py-1 text-[11px] font-medium capitalize ${
                tab === t ? "bg-zinc-900 text-white" : "text-zinc-500 hover:bg-zinc-100"
              }`}
            >
              {t === "review" ? "Review" : "Itinerary"}
            </button>
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {scope === "activity" && event ? (
          <ActivityPanel event={event} />
        ) : day ? (
          <DayDetail trip={trip} day={day} />
        ) : tab === "review" ? (
          <ReviewPanel />
        ) : (
          <DayList trip={trip} />
        )}
      </div>
    </div>
  );
}

function Header({ trip }: { trip: Trip }) {
  const s = trip.stats;
  const onFoot =
    (s.distance_by_mode_m.hike ?? 0) +
    (s.distance_by_mode_m.walk ?? 0) +
    (s.distance_by_mode_m.bike ?? 0);
  return (
    <header className="shrink-0 border-b border-zinc-200 px-6 py-5">
      <h1 className="text-xl font-semibold tracking-tight text-zinc-900">{trip.title}</h1>
      <p className="mt-0.5 text-xs text-zinc-500">
        {formatDate(trip.date_range.start)} &ndash; {formatDate(trip.date_range.end)}
      </p>
      <div className="mt-4 grid grid-cols-4 gap-3">
        <Stat value={String(s.day_count)} label="days" />
        <Stat value={km(s.distance_by_mode_m.drive ?? 0)} label="driven" />
        <Stat value={km(onFoot, 0)} label="on foot" />
        <Stat value={s.photo_count.toLocaleString()} label="photos" />
      </div>
      {s.unaccounted_count > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-amber-700">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400" />
          {s.unaccounted_count} unaccounted {s.unaccounted_count === 1 ? "gap" : "gaps"} &middot;{" "}
          {Math.round(s.unaccounted_hours)} h
        </p>
      )}
    </header>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="tnum text-lg font-semibold tracking-tight text-zinc-900">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-400">{label}</div>
    </div>
  );
}

function DayList({ trip }: { trip: Trip }) {
  const select = useTrip((s) => s.selectDay);
  return (
    <ol className="divide-y divide-zinc-100">
      {trip.days
        .filter((d) => !d.excluded)
        .map((d) => (
          <li key={d.id}>
            <button
              onClick={() => select(d.id)}
              className="flex w-full items-start gap-4 px-6 py-3.5 text-left hover:bg-zinc-50"
            >
              <div className="w-8 shrink-0 pt-0.5">
                <div className="tnum text-lg font-semibold tracking-tight text-zinc-300">
                  {String(d.index).padStart(2, "0")}
                </div>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm font-medium text-zinc-900">
                    {d.title ?? "\u2014"}
                  </span>
                  <span className="shrink-0 text-[11px] text-zinc-400">
                    {formatDate(d.date)}
                  </span>
                </div>
                {d.subtitle && (
                  <p className="mt-0.5 truncate text-[11px] text-zinc-500">{d.subtitle}</p>
                )}
                <DayMeta day={d} />
              </div>
            </button>
          </li>
        ))}
    </ol>
  );
}

function DayMeta({ day }: { day: Day }) {
  const dist = dayDistance(day);
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-400">
      {dist > 0 && <span className="tnum">{km(dist)}</span>}
      {/* Elevation appears only when the day actually contained an activity. */}
      {day.stats.ascent_m != null && (
        <span className="tnum text-emerald-600">+{Math.round(day.stats.ascent_m)} m</span>
      )}
      {day.stats.photo_count > 0 && (
        <span className="tnum">{day.stats.photo_count} photos</span>
      )}
      {day.stats.unaccounted_hours > 0 && (
        <span className="text-amber-600">
          {Math.round(day.stats.unaccounted_hours)} h unaccounted
        </span>
      )}
    </div>
  );
}

function DayDetail({ trip, day }: { trip: Trip; day: Day }) {
  const events = dayEvents(trip, day);
  const spanning = spanningEvents(trip, day);
  const select = useTrip((s) => s.selectEvent);
  const selectDay = useTrip((s) => s.selectDay);
  const editing = useTrip((s) => s.editing);
  const applyOp = useTrip((s) => s.applyOp);
  const [showHidden, setShowHidden] = useState(false);
  const hidden = day.event_ids
    .map((i) => trip.events.find((e) => e.id === i))
    .filter((e): e is NonNullable<typeof e> => !!e && e.status === "suppressed");

  return (
    <div>
      <div className="sticky top-0 z-10 border-b border-zinc-200 bg-white px-6 py-4">
        <button
          onClick={() => selectDay(null)}
          className="text-[11px] font-medium text-zinc-400 hover:text-zinc-700"
        >
          &larr; All days
        </button>
        <h2 className="mt-1.5 text-lg font-semibold tracking-tight text-zinc-900">
          {day.title}
        </h2>
        <p className="mt-0.5 text-xs text-zinc-500">
          Day {day.index} &middot; {formatDate(day.date, "long")}
        </p>
        {day.subtitle && <p className="mt-1 text-[11px] text-zinc-400">{day.subtitle}</p>}
        {editing && (
          <>
            <DayEditor day={day} />
            <TitleSuggester dayId={day.id} current={day.title ?? ""} />
          </>
        )}
      </div>

      <div className="px-6 py-4">
        {spanning.map((e) => (
          <div
            key={e.id}
            className="mb-3 rounded-lg border border-dashed border-zinc-300 px-3 py-2"
          >
            <p className="text-[11px] text-zinc-500">
              <span className="font-medium text-zinc-700">Continues from an earlier day</span>
              {" \u00b7 "}
              {eventName(e)}
            </p>
          </div>
        ))}

        {events.length === 0 && spanning.length === 0 && (
          <p className="py-10 text-center text-xs text-zinc-400">
            Nothing was recorded on this day.
          </p>
        )}

        {hidden.length > 0 && (
          <button
            onClick={() => setShowHidden(!showHidden)}
            className="mb-2 w-full rounded-lg border border-dashed border-zinc-300 py-1.5 text-[11px] font-medium text-zinc-500 hover:border-zinc-400 hover:text-zinc-700"
          >
            {showHidden ? "Hide" : "Show"} {hidden.length} minor stops Trippo set aside
          </button>
        )}
        {showHidden &&
          hidden.map((e) => (
            <div
              key={e.id}
              className="mb-1.5 flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-[11px] text-zinc-500">
                {eventName(e)}
                <span className="ml-2 text-zinc-400">{e.suppress_reason}</span>
              </span>
              {editing && (
                <button
                  onClick={() => void applyOp("restore_event", { event_id: e.id })}
                  className="shrink-0 text-[11px] font-medium text-indigo-600 hover:underline"
                >
                  Keep it
                </button>
              )}
            </div>
          ))}

        <ol className="space-y-1.5">
          {events.map((e) => (
            <div key={e.id}>
              <EventRow trip={trip} event={e} onSelect={() => select(e.id)} />
              {editing && (
                <div className="mb-2 rounded-lg border border-zinc-200 bg-zinc-50">
                  <EventEditor event={e} />
                  <div className="border-t border-zinc-200 px-5 py-4">
                    <PhotoPicker trip={trip} event={e} />
                    <FindNearby event={e} />
                  </div>
                </div>
              )}
            </div>
          ))}
        </ol>
      </div>
    </div>
  );
}

function EventRow({
  trip,
  event,
  onSelect,
}: {
  trip: Trip;
  event: TripEvent;
  onSelect: () => void;
}) {
  const meta = TYPE_META[event.type];
  const track = trip.tracks.find((t) => t.id === event.track_ids[0]);
  const clickable = !!track;

  if (event.type === "unknown" && event.detail.kind === "unknown") {
    return (
      <li className="rounded-lg border border-amber-300 bg-amber-50 p-3">
        <p className="text-xs font-semibold text-amber-900">
          {Math.round(event.detail.gap_hours)} hours unaccounted
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-amber-800">
          {Math.round(event.detail.displacement_km).toLocaleString()} km that no source
          explains.
          {event.media_ids.length > 0 &&
            ` ${event.media_ids.length} photographs fall inside it.`}
        </p>
        <GapResolver event={event} />
        <PhotoStrip trip={trip} event={event} columns={6} compact />
      </li>
    );
  }

  return (
    <li>
      <button
        onClick={onSelect}
        disabled={!clickable}
        className={`flex w-full gap-2.5 rounded-lg p-2.5 text-left ${
          clickable ? "hover:bg-zinc-50" : "cursor-default"
        }`}
      >
        <span className="tnum w-10 shrink-0 pt-0.5 text-right font-mono text-[11px] text-zinc-500">
          {localTime(event.start, event.utc_offset_minutes)}
        </span>
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${meta.dot}`} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="truncate text-sm text-zinc-900">{eventName(event)}</span>
            {isContested(event) && (
              <span
                title="Trippo was unsure between two nearby places"
                className="shrink-0 rounded bg-zinc-100 px-1 text-[9px] font-medium text-zinc-500"
              >
                ?
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-zinc-400">
            <span>{meta.icon}</span>
            <span>{duration((event.end
              ? new Date(event.end).getTime() - new Date(event.start).getTime()
              : 0) / 1000)}</span>
            {event.media_ids.length > 0 && (
              <span>&middot; {event.media_ids.length} photos</span>
            )}
          </div>
          <PhotoStrip trip={trip} event={event} columns={6} compact />
          {track && (
            <div className="tnum mt-1 flex items-center gap-3 text-[11px] text-zinc-600">
              <span>
                <b className="font-semibold text-zinc-900">
                  {(track.stats.distance_m / 1000).toFixed(1)}
                </b>{" "}
                km
              </span>
              <span>
                <b className="font-semibold text-zinc-900">
                  +{Math.round(track.stats.ascent_m)}
                </b>{" "}
                m
              </span>
              <span className="text-indigo-600">view &rarr;</span>
            </div>
          )}
        </div>
      </button>
    </li>
  );
}
