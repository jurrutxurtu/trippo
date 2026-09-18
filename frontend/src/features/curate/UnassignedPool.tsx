import { useState } from "react";
import { useTrip, selectedEvent } from "@/store/trip";

/**
 * The unassigned pool.
 *
 * Every photograph Trippo could not place, plus everything freed by deleting or hiding an
 * event. Docked at the bottom because it must be visibly non-empty: the promise that
 * nothing is lost only means something if you can see where things went.
 */
export function UnassignedPool() {
  const state = useTrip();
  const { trip, applyOp, openLightbox } = state;
  const event = selectedEvent(state);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  if (!trip) return null;
  const byId = new Map(trip.media.map((m) => [m.id, m]));
  const items = trip.unassigned_media_ids
    .map((id) => byId.get(id))
    .filter((m) => m?.thumb_ref);

  if (items.length === 0) return null;

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className="shrink-0 border-t border-zinc-200 bg-white">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-5 py-2 text-left hover:bg-zinc-50"
      >
        <span className="flex items-center gap-2 text-[11px]">
          <span className="font-semibold text-zinc-900">Unassigned</span>
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
            {items.length}
          </span>
          <span className="text-zinc-400">
            photographs with no event &mdash; nothing is ever deleted
          </span>
        </span>
        <span className="text-[11px] text-zinc-400">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <div className="border-t border-zinc-100 px-5 py-3">
          <div className="grid max-h-40 grid-cols-10 gap-1 overflow-y-auto">
            {items.map((m) => (
              <button
                key={m!.id}
                onClick={() => toggle(m!.id)}
                onDoubleClick={() =>
                  openLightbox(items.filter(Boolean) as never, items.indexOf(m))
                }
                title={m!.captured_at?.slice(0, 16).replace("T", " ") ?? m!.filename}
                className={`overflow-hidden rounded ring-2 ${
                  picked.has(m!.id) ? "ring-indigo-500" : "ring-transparent"
                }`}
              >
                <img
                  src={`/${m!.thumb_ref}`}
                  alt=""
                  loading="lazy"
                  className="aspect-square w-full object-cover"
                />
              </button>
            ))}
          </div>

          <div className="mt-2.5 flex items-center justify-between">
            <span className="text-[11px] text-zinc-500">{picked.size} selected</span>
            <button
              disabled={!picked.size || !event}
              onClick={() => {
                if (!event) return;
                void applyOp("move_media", {
                  media_ids: [...picked],
                  target_event_id: event.id,
                }).then(() => setPicked(new Set()));
              }}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-indigo-500 disabled:bg-zinc-300"
              title={event ? undefined : "Select an event first"}
            >
              {event
                ? `Attach to ${(event.title ?? "the selected event").slice(0, 28)}`
                : "Select an event to attach"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
