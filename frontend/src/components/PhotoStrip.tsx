import { useTrip, eventPhotos } from "@/store/trip";
import type { Trip, TripEvent } from "@/lib/types";

/**
 * Thumbnails for an event, with the suggested selection shown first.
 *
 * The backend picks a small, well-spread set (`selected_media_ids`) so a 87-photograph
 * hike does not flood a timeline row. "+N more" reveals the rest -- the full set is always
 * owned by the event and never hidden permanently.
 */
export function PhotoStrip({
  trip,
  event,
  columns = 4,
  compact = false,
}: {
  trip: Trip;
  event: TripEvent;
  columns?: number;
  compact?: boolean;
}) {
  const expandedPhotos = useTrip((s) => s.expandedPhotos);
  const toggleExpandedPhotos = useTrip((s) => s.toggleExpandedPhotos);
  const openLightbox = useTrip((s) => s.openLightbox);
  const setHoveredMedia = useTrip((s) => s.setHoveredMedia);

  const expanded = expandedPhotos.has(event.id);
  const { shown, all, hidden } = eventPhotos(trip, event, expanded);
  if (all.length === 0) return null;

  return (
    <div className={compact ? "mt-2" : "mt-2.5"}>
      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {shown.map((m) => (
          <button
            key={m.id}
            onClick={(e) => {
              e.stopPropagation();
              openLightbox(all, all.indexOf(m));
            }}
            onMouseEnter={() => setHoveredMedia(m.id)}
            onMouseLeave={() => setHoveredMedia(null)}
            className="group relative overflow-hidden rounded ring-1 ring-black/5"
            title={m.captured_at?.slice(11, 16) ?? m.filename}
          >
            <img
              src={`/${m.thumb_ref}`}
              alt=""
              loading="lazy"
              className="aspect-square w-full object-cover transition group-hover:brightness-110"
            />
            {m.kind === "video" && (
              <span className="absolute bottom-0.5 right-0.5 rounded bg-black/60 px-1 text-[8px] text-white">
                video
              </span>
            )}
          </button>
        ))}
      </div>

      {hidden > 0 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleExpandedPhotos(event.id);
          }}
          className="mt-1.5 text-[11px] font-medium text-indigo-600 hover:underline"
        >
          Show {hidden} more {hidden === 1 ? "photograph" : "photographs"}
        </button>
      )}
      {expanded && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleExpandedPhotos(event.id);
          }}
          className="mt-1.5 text-[11px] font-medium text-zinc-500 hover:underline"
        >
          Show only the {event.selected_media_ids.length} suggested
        </button>
      )}
    </div>
  );
}
