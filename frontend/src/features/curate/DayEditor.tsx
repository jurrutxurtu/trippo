import { useEffect, useState } from "react";
import { useTrip } from "@/store/trip";
import type { Day } from "@/lib/types";

/** Day-level editing: title, note, exclude, and adding an event the sources missed. */
export function DayEditor({ day }: { day: Day }) {
  const { applyOp, busy } = useTrip();
  const [title, setTitle] = useState(day.title ?? "");
  const [note, setNote] = useState(day.note ?? "");
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState("");

  useEffect(() => {
    setTitle(day.title ?? "");
    setNote(day.note ?? "");
  }, [day.id, day.title, day.note]);

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-zinc-200 bg-zinc-50 p-3">
      <div>
        <label className="text-[11px] font-medium text-zinc-500">Day title</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() =>
            title !== (day.title ?? "") &&
            void applyOp("set_day_title", { day_id: day.id, title })
          }
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="mt-1 block w-full rounded-lg border-zinc-300 text-xs focus:border-indigo-500 focus:ring-indigo-500"
        />
        {day.user_title && (
          <p className="mt-1 text-[10px] text-emerald-600">
            Your title &mdash; it will not be regenerated.
          </p>
        )}
      </div>

      <div>
        <label className="text-[11px] font-medium text-zinc-500">Day note</label>
        <textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() =>
            note !== (day.note ?? "") &&
            void applyOp("set_day_note", { day_id: day.id, note })
          }
          placeholder="Rain all afternoon&hellip;"
          className="mt-1 block w-full rounded-lg border-zinc-300 text-xs focus:border-indigo-500 focus:ring-indigo-500"
        />
      </div>

      {adding ? (
        <div className="flex gap-1.5">
          <input
            autoFocus
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="What happened?"
            className="min-w-0 flex-1 rounded-lg border-zinc-300 text-xs focus:border-indigo-500 focus:ring-indigo-500"
          />
          <button
            disabled={busy || !newTitle.trim()}
            onClick={() => {
              void applyOp("add_event", {
                day_id: day.id,
                type: "visit",
                title: newTitle.trim(),
              });
              setNewTitle("");
              setAdding(false);
            }}
            className="rounded-lg bg-indigo-600 px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
          >
            Add
          </button>
          <button
            onClick={() => setAdding(false)}
            className="px-2 text-[11px] text-zinc-500 hover:text-zinc-800"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAdding(true)}
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50"
          >
            + Add event
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void applyOp("set_day_excluded", {
                day_id: day.id,
                excluded: !day.excluded,
              })
            }
            className="rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-zinc-500 hover:bg-zinc-200"
          >
            {day.excluded ? "Include this day" : "Exclude this day"}
          </button>
        </div>
      )}
    </div>
  );
}
