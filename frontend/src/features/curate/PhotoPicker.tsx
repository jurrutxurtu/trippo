import { useTrip, eventPhotos } from "@/store/trip";
import type { Trip, TripEvent } from "@/lib/types";

/**
 * Choose which photographs represent an event.
 *
 * Selecting is not deleting: the event keeps all 87 either way. This only decides which
 * few appear first, and marks the choice as the user's so it is never recomputed.
 */
export function PhotoPicker({ trip, event }: { trip: Trip; event: TripEvent }) {
  const applyOp = useTrip((s) => s.applyOp);
  const openLightbox = useTrip((s) => s.openLightbox);
  const { all } = eventPhotos(trip, event, true);
  if (all.length === 0) return null;

  const selected = new Set(event.selected_media_ids);

  const toggle = (id: string) => {
    const next = selected.has(id)
      ? event.selected_media_ids.filter((x) => x !== id)
      : [...event.selected_media_ids, id];
    void applyOp("set_selected_media", { event_id: event.id, media_ids: next });
  };

  return (
    <div className="mt-3">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-semibold text-zinc-900">
          Representative photographs
          <span className="ml-1.5 font-normal text-zinc-400">
            {selected.size} of {all.length}
          </span>
        </span>
        {event.user_selected_media && (
          <span className="text-[10px] text-emerald-600">your choice</span>
        )}
      </div>

      <div className="mt-2 grid max-h-64 grid-cols-6 gap-1 overflow-y-auto">
        {all.map((m) => (
          <div key={m.id} className="relative">
            <button
              onClick={() => toggle(m.id)}
              title={m.captured_at?.slice(11, 16) ?? ""}
              className={`block overflow-hidden rounded ring-2 ${
                selected.has(m.id) ? "ring-indigo-500" : "ring-transparent"
              }`}
            >
              <img
                src={`/${m.thumb_ref}`}
                alt=""
                loading="lazy"
                className={`aspect-square w-full object-cover ${
                  selected.has(m.id) ? "" : "opacity-45"
                }`}
              />
            </button>
            <button
              onClick={() => openLightbox(all, all.indexOf(m))}
              className="absolute bottom-0.5 right-0.5 rounded bg-black/60 px-1 text-[9px] text-white opacity-0 hover:opacity-100"
              title="View full size"
            >
              view
            </button>
          </div>
        ))}
      </div>

      <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-400">
        Unselected photographs stay attached to this event &mdash; they simply do not appear
        first.
      </p>
    </div>
  );
}
