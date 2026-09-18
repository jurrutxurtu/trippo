import { useEffect, useState } from "react";
import { useTrip } from "@/store/trip";
import type { TripEvent } from "@/lib/types";

interface Candidate {
  id: string;
  thumb: string | null;
  capturedAt: string;
  unassigned: boolean;
  ownerEventId: string | null;
  ownerTitle: string | null;
}

/**
 * Attach photographs taken around an event.
 *
 * Unassigned ones come first -- those have no home. Anything already attached elsewhere is
 * shown with its current owner, so moving a photograph is a deliberate act rather than an
 * accident.
 */
export function FindNearby({ event }: { event: TripEvent }) {
  const applyOp = useTrip((s) => s.applyOp);
  const [open, setOpen] = useState(false);
  const [minutes, setMinutes] = useState(45);
  const [items, setItems] = useState<Candidate[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    fetch(`/api/events/${event.id}/nearby?minutes=${minutes}`)
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) {
          setItems(d.candidates as Candidate[]);
          setLoading(false);
        }
      })
      .catch(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, minutes, event.id]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-2 rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50"
      >
        Find nearby photographs&hellip;
      </button>
    );
  }

  const free = items?.filter((c) => c.unassigned) ?? [];
  const taken = items?.filter((c) => !c.unassigned) ?? [];

  const attach = async () => {
    if (!picked.size) return;
    const ok = await applyOp("move_media", {
      media_ids: [...picked],
      target_event_id: event.id,
    });
    if (ok) {
      setPicked(new Set());
      setOpen(false);
    }
  };

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className="mt-2 rounded-lg border border-zinc-300 bg-white p-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-zinc-900">
          Photographs within
        </span>
        <button
          onClick={() => setOpen(false)}
          className="text-[11px] text-zinc-400 hover:text-zinc-700"
        >
          Close
        </button>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <input
          type="range"
          min={15}
          max={240}
          step={15}
          value={minutes}
          onChange={(e) => setMinutes(Number(e.target.value))}
          className="flex-1 accent-indigo-600"
        />
        <span className="tnum w-16 shrink-0 text-right text-[11px] text-zinc-600">
          &plusmn;{minutes} min
        </span>
      </div>

      {loading ? (
        <p className="mt-3 text-center text-[11px] text-zinc-400">Looking&hellip;</p>
      ) : items && items.length === 0 ? (
        <p className="mt-3 text-center text-[11px] text-zinc-400">
          Nothing else was taken in that window.
        </p>
      ) : (
        <>
          <Group
            label={`${free.length} unassigned`}
            items={free}
            picked={picked}
            toggle={toggle}
          />
          <Group
            label={`${taken.length} attached elsewhere`}
            items={taken}
            picked={picked}
            toggle={toggle}
            muted
          />
        </>
      )}

      <div className="mt-3 flex items-center justify-between">
        <span className="text-[11px] text-zinc-500">{picked.size} selected</span>
        <button
          disabled={!picked.size}
          onClick={() => void attach()}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-indigo-500 disabled:bg-zinc-300"
        >
          Attach to this event
        </button>
      </div>
    </div>
  );
}

function Group({
  label,
  items,
  picked,
  toggle,
  muted,
}: {
  label: string;
  items: Candidate[];
  picked: Set<string>;
  toggle: (id: string) => void;
  muted?: boolean;
}) {
  if (!items.length) return null;
  return (
    <div className="mt-3">
      <p className="text-[10px] uppercase tracking-wide text-zinc-400">{label}</p>
      <div className="mt-1.5 grid grid-cols-6 gap-1">
        {items.map((c) => (
          <button
            key={c.id}
            onClick={() => toggle(c.id)}
            title={`${c.capturedAt.slice(11, 16)}${c.ownerTitle ? ` \u00b7 ${c.ownerTitle}` : ""}`}
            className={`relative overflow-hidden rounded ring-2 ${
              picked.has(c.id) ? "ring-indigo-500" : "ring-transparent"
            }`}
          >
            {c.thumb && (
              <img
                src={`/${c.thumb}`}
                alt=""
                loading="lazy"
                className={`aspect-square w-full object-cover ${muted ? "opacity-60" : ""}`}
              />
            )}
            {picked.has(c.id) && (
              <span className="absolute right-0.5 top-0.5 rounded bg-indigo-600 px-1 text-[9px] text-white">
                &#10003;
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
