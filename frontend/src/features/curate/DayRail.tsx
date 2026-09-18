import { useTrip, dayEvents } from "@/store/trip";
import { formatDate } from "@/lib/format";
import type { Trip } from "@/lib/types";

/**
 * The day rail: navigation plus a per-day view of what data actually exists.
 *
 * The three bars are timeline, photographs and tracks. They are the cheapest possible
 * answer to "why does this day look wrong?" -- usually because one of them is grey.
 */
export function DayRail({ trip }: { trip: Trip }) {
  const { dayId, selectDay } = useTrip();

  return (
    <nav className="flex h-full w-[168px] shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
          Days
        </span>
        <span className="flex items-center gap-0.5" title="timeline · photos · tracks">
          <span className="h-1 w-2.5 rounded-sm bg-sky-400" />
          <span className="h-1 w-2.5 rounded-sm bg-violet-400" />
          <span className="h-1 w-2.5 rounded-sm bg-emerald-500" />
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-3">
        {trip.days.map((d) => {
          const cov = trip.stats.coverage?.find((c) => c.date === d.date);
          const events = dayEvents(trip, d);
          const gap = events.some((e) => e.type === "unknown");
          const active = d.id === dayId;
          return (
            <button
              key={d.id}
              onClick={() => selectDay(d.id)}
              className={`block w-full px-2.5 py-1.5 text-left ${
                active
                  ? "bg-indigo-50 ring-1 ring-inset ring-indigo-200"
                  : d.excluded
                    ? "opacity-40 hover:bg-zinc-50"
                    : "hover:bg-zinc-50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span
                  className={`text-[11px] font-semibold ${
                    active ? "text-indigo-900" : "text-zinc-900"
                  }`}
                >
                  {d.excluded ? "\u2014" : `Day ${d.index}`}
                </span>
                <span className="flex items-center gap-0.5">
                  <Bar on={!!cov?.timeline_records} colour="bg-sky-400" />
                  <Bar on={!!cov?.media_count} colour="bg-violet-400" />
                  <Bar on={!!cov?.track_count} colour="bg-emerald-500" />
                </span>
              </div>
              <div className="mt-0.5 truncate text-[10px] text-zinc-500">
                {d.title ?? formatDate(d.date)}
              </div>
              <div className="mt-0.5 flex items-center gap-1 text-[10px] text-zinc-400">
                {gap && <span className="text-amber-500">&#9679;</span>}
                <span>{events.length} ev</span>
                {d.stats.photo_count > 0 && <span>&middot; {d.stats.photo_count} ph</span>}
              </div>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function Bar({ on, colour }: { on: boolean; colour: string }) {
  return <span className={`h-1 w-2.5 rounded-sm ${on ? colour : "bg-zinc-200"}`} />;
}
