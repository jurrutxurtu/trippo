import { useEffect } from "react";
import { useTrip } from "@/store/trip";
import type { MediaAsset } from "@/lib/types";

/**
 * Full-size photograph viewer.
 *
 * Opened from anywhere a thumbnail appears -- the timeline, the activity panel, a map
 * popup -- so a photograph is always one click from being seen properly, which was the
 * whole complaint about the first build.
 */
export function Lightbox() {
  const { lightbox, closeLightbox, stepLightbox } = useTrip();

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeLightbox();
      if (e.key === "ArrowRight") stepLightbox(1);
      if (e.key === "ArrowLeft") stepLightbox(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, closeLightbox, stepLightbox]);

  if (!lightbox) return null;
  const { items, index } = lightbox;
  const media = items[index];
  if (!media) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-zinc-950/95"
      onClick={closeLightbox}
    >
      <div className="flex shrink-0 items-center justify-between px-6 py-4 text-xs text-zinc-400">
        <span className="tnum">
          {index + 1} / {items.length}
          {media.captured_at && (
            <span className="ml-3 text-zinc-500">
              {new Date(media.captured_at).toISOString().slice(0, 16).replace("T", " ")}
            </span>
          )}
          {media.location_source === "inferred" && (
            <span
              className="ml-3 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400"
              title="No GPS in this photo; the position was interpolated from the timeline or a track"
            >
              position inferred
            </span>
          )}
        </span>
        <button className="rounded px-2 py-1 hover:bg-white/10" onClick={closeLightbox}>
          Close &times;
        </button>
      </div>

      <div
        className="flex min-h-0 flex-1 items-center justify-center px-16 pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="absolute left-4 rounded-full bg-white/10 px-3 py-4 text-white hover:bg-white/20"
          onClick={() => stepLightbox(-1)}
          aria-label="Previous"
        >
          &larr;
        </button>
        <img
          src={`/${media.web_ref ?? media.thumb_ref}`}
          alt={media.filename}
          className="max-h-full max-w-full rounded-lg object-contain"
        />
        <button
          className="absolute right-4 rounded-full bg-white/10 px-3 py-4 text-white hover:bg-white/20"
          onClick={() => stepLightbox(1)}
          aria-label="Next"
        >
          &rarr;
        </button>
      </div>

      <Filmstrip items={items} index={index} />
    </div>
  );
}

function Filmstrip({ items, index }: { items: MediaAsset[]; index: number }) {
  const openLightbox = useTrip((s) => s.openLightbox);
  if (items.length < 2) return null;
  return (
    <div
      className="shrink-0 overflow-x-auto px-6 pb-5"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex gap-1.5">
        {items.map((m, i) => (
          <button key={m.id} onClick={() => openLightbox(items, i)}>
            <img
              src={`/${m.thumb_ref}`}
              alt=""
              loading="lazy"
              className={`h-14 w-14 rounded object-cover ${
                i === index ? "ring-2 ring-white" : "opacity-50 hover:opacity-90"
              }`}
            />
          </button>
        ))}
      </div>
    </div>
  );
}
