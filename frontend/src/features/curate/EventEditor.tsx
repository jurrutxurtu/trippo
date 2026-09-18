import { useEffect, useState } from "react";
import { useTrip } from "@/store/trip";
import { TYPE_META } from "@/lib/format";
import { EDITABLE_TYPES, type EventType, type TripEvent } from "@/lib/types";

/**
 * Editing controls for one event.
 *
 * Only rendered in edit mode. Every change goes through the server, which validates
 * invariants and can reject -- the client never mutates the capsule itself.
 */
export function EventEditor({ event }: { event: TripEvent }) {
  const { applyOp, busy } = useTrip();
  const [name, setName] = useState(event.title ?? event.place?.name ?? "");
  const [note, setNote] = useState(event.note ?? "");

  useEffect(() => {
    setName(event.title ?? event.place?.name ?? "");
    setNote(event.note ?? "");
  }, [event.id, event.title, event.place?.name, event.note]);

  const commitName = () => {
    const trimmed = name.trim();
    if (trimmed && trimmed !== (event.title ?? event.place?.name))
      void applyOp("rename_event", { event_id: event.id, name: trimmed });
  };

  return (
    <div className="space-y-4 border-t border-zinc-200 px-5 py-4">
      <div>
        <label className="text-[11px] font-medium text-zinc-500">Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="mt-1 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
        />
        {event.place?.source === "user" && (
          <p className="mt-1 text-[10px] text-emerald-600">
            Your name &mdash; place lookup will not overwrite it.
          </p>
        )}
      </div>

      <div>
        <label className="text-[11px] font-medium text-zinc-500">Type</label>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {EDITABLE_TYPES.map((t) => (
            <button
              key={t}
              disabled={busy}
              onClick={() =>
                void applyOp(
                  event.type === "unknown" ? "resolve_gap" : "set_event_type",
                  { event_id: event.id, type: t },
                )
              }
              className={`rounded-md px-2 py-1 text-[11px] font-medium ${
                t === event.type
                  ? "bg-zinc-900 text-white"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
              }`}
            >
              {TYPE_META[t as EventType].icon} {t}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="text-[11px] font-medium text-zinc-500">Your note</label>
        <textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() =>
            note !== (event.note ?? "") &&
            void applyOp("set_note", { event_id: event.id, note })
          }
          placeholder="Hail at the summit&hellip;"
          className="mt-1 block w-full rounded-lg border-zinc-300 text-xs focus:border-indigo-500 focus:ring-indigo-500"
        />
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          disabled={busy}
          onClick={() => void applyOp("suppress_event", { event_id: event.id })}
          className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Hide
        </button>
        <button
          disabled={busy}
          onClick={() => void applyOp("delete_event", { event_id: event.id })}
          className="rounded-lg border border-red-200 px-2.5 py-1.5 text-[11px] font-medium text-red-700 hover:bg-red-50"
        >
          Delete
        </button>
        <span className="text-[10px] text-zinc-400">
          Photographs are never deleted &mdash; they return to the pool.
        </span>
      </div>
    </div>
  );
}

/** One-click resolution for an unaccounted gap, offered inline in the timeline. */
export function GapResolver({ event }: { event: TripEvent }) {
  const { applyOp, busy } = useTrip();
  if (event.detail.kind !== "unknown") return null;
  const options = event.detail.candidate_types.length
    ? event.detail.candidate_types
    : (["drive", "ferry", "flight"] as EventType[]);

  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
      {options.map((t) => (
        <button
          key={t}
          disabled={busy}
          onClick={() => void applyOp("resolve_gap", { event_id: event.id, type: t })}
          className="rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-medium text-amber-900 shadow-sm ring-1 ring-amber-300 hover:bg-amber-100"
        >
          {TYPE_META[t].icon} It was a {t}
        </button>
      ))}
    </div>
  );
}
