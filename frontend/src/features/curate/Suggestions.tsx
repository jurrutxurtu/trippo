import { useState } from "react";
import { useTrip } from "@/store/trip";
import type { Suggestion, SuggestionKind, Trip } from "@/lib/types";

const KINDS: { kind: SuggestionKind; label: string; blurb: string; needsAi: boolean }[] = [
  {
    kind: "group",
    label: "Group repetitive stops",
    blurb:
      "A dozen stops eighty metres apart are one visit to a quarter. Geometry finds the runs; the model names them.",
    needsAi: true,
  },
  {
    kind: "demote",
    label: "Hide passing-through stops",
    blurb:
      "Brief, photograph-less and unremarkable. Never applied to anything with a photograph attached.",
    needsAi: false,
  },
  {
    kind: "day_title",
    label: "Name days by what they were for",
    blurb:
      "The current titles pick the longest stop. A whole-day view can say what the day was about.",
    needsAi: true,
  },
  {
    kind: "activity_shape",
    label: "Describe the walks",
    blurb:
      "Shape, effort and what it went over, from the track's own telemetry and the summits it crossed.",
    needsAi: true,
  },
  {
    kind: "place_name",
    label: "Settle contested names",
    blurb:
      "Where two nearby candidates scored the same. The model may only choose from the list.",
    needsAi: true,
  },
];

/**
 * Model-driven suggestions.
 *
 * Every one proposes a structural change over data the model can already see, and you
 * accept or reject it. Nothing is applied until you say so, and everything applied is one
 * undoable operation.
 */
export function Suggestions({ trip }: { trip: Trip }) {
  const { applyOp, aiAvailable } = useTrip();
  const [open, setOpen] = useState<SuggestionKind | null>(null);
  const [items, setItems] = useState<Record<string, Suggestion[]>>({});
  const [loading, setLoading] = useState<SuggestionKind | null>(null);
  const [applied, setApplied] = useState<Set<string>>(new Set());
  const [note, setNote] = useState<string | null>(null);

  const run = async (kind: SuggestionKind) => {
    setLoading(kind);
    setOpen(kind);
    setNote(null);
    try {
      const res = await fetch(`/api/suggestions/${kind}`, { method: "POST" });
      if (res.status === 204) {
        setNote("No model is configured, so this suggestion is unavailable.");
        setItems((p) => ({ ...p, [kind]: [] }));
        return;
      }
      const data = await res.json();
      const list = (data.items ?? []) as Suggestion[];
      setItems((p) => ({ ...p, [kind]: list }));
      if (data.error) setNote(data.error);
      else if (list.length === 0)
        setNote("Nothing to suggest here \u2014 it already looks right.");
    } catch {
      setNote("Could not reach the model.");
    } finally {
      setLoading(null);
    }
  };

  const accept = async (s: Suggestion) => {
    for (const op of s.ops) {
      const ok = await applyOp(op.op, op.payload);
      if (!ok) return;
    }
    setApplied((prev) => new Set(prev).add(s.id));
  };

  return (
    <section className="mt-8">
      <h2 className="text-xs font-semibold uppercase tracking-[0.15em] text-zinc-500">
        Let the model help
      </h2>
      <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-zinc-500">
        Each of these proposes a change over what is already in your trip. Nothing is
        applied until you accept it, and anything you accept can be undone.
      </p>

      <div className="mt-4 space-y-2">
        {KINDS.map((k) => {
          const unavailable = k.needsAi && !aiAvailable;
          const list = items[k.kind];
          const isOpen = open === k.kind;
          return (
            <div
              key={k.kind}
              className="overflow-hidden rounded-xl border border-zinc-200 bg-white"
            >
              <div className="flex items-start justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-medium text-zinc-900">{k.label}</h3>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-zinc-500">
                    {k.blurb}
                  </p>
                  {unavailable && (
                    <p className="mt-1 text-[10px] text-zinc-400">
                      Needs a model. Set GEMINI_API_KEY in backend/.env.
                    </p>
                  )}
                </div>
                <button
                  disabled={unavailable || loading === k.kind}
                  onClick={() => (isOpen ? setOpen(null) : void run(k.kind))}
                  className="shrink-0 rounded-lg border border-zinc-300 px-3 py-1.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-40"
                >
                  {loading === k.kind
                    ? "Thinking\u2026"
                    : list
                      ? `${list.length} found`
                      : "Look"}
                </button>
              </div>

              {isOpen && (
                <div className="border-t border-zinc-100 bg-zinc-50 px-4 py-3">
                  {note && (
                    <p
                      className={`text-[11px] leading-relaxed ${
                        note.length > 80 ? "text-amber-800" : "text-zinc-500"
                      }`}
                    >
                      {note}
                    </p>
                  )}
                  <ul className="space-y-2">
                    {(list ?? []).map((s) => (
                      <li
                        key={s.id}
                        className="rounded-lg border border-zinc-200 bg-white px-3 py-2.5"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-zinc-900">{s.title}</p>
                            <p className="mt-0.5 text-[11px] leading-relaxed text-zinc-500">
                              {s.rationale}
                            </p>
                            {s.mediaCount > 0 && (
                              <p className="mt-0.5 text-[10px] text-zinc-400">
                                {s.mediaCount} photographs move with it
                              </p>
                            )}
                          </div>
                          {applied.has(s.id) ? (
                            <span className="shrink-0 text-[11px] font-medium text-emerald-600">
                              applied
                            </span>
                          ) : (
                            <div className="flex shrink-0 gap-1.5">
                              <button
                                onClick={() => void accept(s)}
                                className="rounded-lg bg-indigo-600 px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-indigo-500"
                              >
                                Apply
                              </button>
                              <button
                                onClick={() =>
                                  setItems((p) => ({
                                    ...p,
                                    [k.kind]: (p[k.kind] ?? []).filter(
                                      (x) => x.id !== s.id,
                                    ),
                                  }))
                                }
                                className="px-1.5 text-[11px] text-zinc-400 hover:text-zinc-700"
                              >
                                No
                              </button>
                            </div>
                          )}
                        </div>
                        <Preview trip={trip} suggestion={s} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Show the photographs a grouping would merge, so the decision is made on evidence. */
function Preview({ trip, suggestion }: { trip: Trip; suggestion: Suggestion }) {
  const openLightbox = useTrip((s) => s.openLightbox);
  if (suggestion.kind !== "group" || suggestion.eventIds.length === 0) return null;

  const byId = new Map(trip.media.map((m) => [m.id, m]));
  const shots = suggestion.eventIds
    .flatMap((id) => trip.events.find((e) => e.id === id)?.media_ids ?? [])
    .map((id) => byId.get(id))
    .filter((m) => m?.thumb_ref)
    .slice(0, 10);
  if (!shots.length) return null;

  return (
    <div className="mt-2 grid grid-cols-10 gap-1">
      {shots.map((m, i) => (
        <button key={m!.id} onClick={() => openLightbox(shots as never, i)}>
          <img
            src={`/${m!.thumb_ref}`}
            alt=""
            loading="lazy"
            className="aspect-square w-full rounded object-cover ring-1 ring-black/5"
          />
        </button>
      ))}
    </div>
  );
}
