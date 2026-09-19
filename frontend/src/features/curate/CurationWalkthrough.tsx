import { useEffect, useState } from "react";
import { useTrip } from "@/store/trip";
import { useApp } from "@/store/app";
import type { AgendaItem, Trip } from "@/lib/types";

/**
 * The curation phase: the guided pass between a machine's draft and an agreed trip.
 *
 * Ingestion produces a capsule, but it is a guess until someone has been through it. This
 * walks the things only a person can settle, hardest first, and will not call the trip
 * finished while a genuine question is open.
 *
 * Deliberately one item at a time. A list of forty problems is a chore; a queue of forty
 * decisions with the next one in front of you is a task.
 */
export function CurationWalkthrough() {
  const { trip, applyOp, save, dirty } = useTrip();
  const go = useApp((s) => s.go);
  const [items, setItems] = useState<AgendaItem[] | null>(null);
  const [at, setAt] = useState(0);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    const data = await fetch("/api/curation/agenda").then((r) => r.json());
    setItems(data.items as AgendaItem[]);
  };

  useEffect(() => {
    void reload();
  }, []);

  if (!trip || items === null) {
    return <Centered>Working out what needs deciding&hellip;</Centered>;
  }

  const live = items.filter((i) => !dismissed.has(i.id));
  const decide = live.filter((i) => i.kind === "decide");
  const done = items.length - live.length;
  const current = live[Math.min(at, live.length - 1)];

  const run = async (op: string | null, payload: Record<string, unknown>, id: string) => {
    setBusy(true);
    if (op) await applyOp(op, payload);
    setDismissed((prev) => new Set(prev).add(id));
    await reload();
    setBusy(false);
  };

  const finish = async () => {
    setBusy(true);
    await applyOp("finalise", {});
    await save();
    setBusy(false);
    go("trip");
  };

  if (live.length === 0) {
    return (
      <Centered>
        <div className="max-w-md text-center">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
            Nothing left to decide
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-500">
            {trip.title} is ready. You can still change anything later &mdash; finishing
            just records that you have been through it.
          </p>
          <button
            onClick={() => void finish()}
            disabled={busy}
            className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500"
          >
            Finish and open the trip
          </button>
        </div>
      </Centered>
    );
  }

  return (
    <div className="min-h-full bg-zinc-50">
      <div className="mx-auto max-w-3xl px-10 py-10">
        <header>
          <div className="flex items-baseline justify-between">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
                Agree the itinerary
              </h1>
              <p className="mt-1 text-sm text-zinc-500">
                {trip.title} &middot; Trippo has made a draft. You decide what it means.
              </p>
            </div>
            <button
              onClick={() => go("trip")}
              className="text-[11px] font-medium text-zinc-400 hover:text-zinc-700"
            >
              Skip to the trip &rarr;
            </button>
          </div>

          <div className="mt-5">
            <div className="flex items-center justify-between text-[11px] text-zinc-500">
              <span>
                {done} settled &middot; {live.length} to go
              </span>
              {decide.length > 0 && (
                <span className="text-amber-700">
                  {decide.length} need an answer before finishing
                </span>
              )}
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-zinc-200">
              <div
                className="h-full rounded-full bg-indigo-600 transition-all"
                style={{
                  width: `${items.length ? (done / items.length) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        </header>

        {current && (
          <Card
            key={current.id}
            item={current}
            trip={trip}
            busy={busy}
            onAction={run}
            onSkip={() => setAt((i) => Math.min(i + 1, live.length - 1))}
            canSkip={live.length > 1}
          />
        )}

        <Remaining items={live} current={current} onJump={(i) => setAt(i)} />

        <div className="mt-8 flex items-center justify-between border-t border-zinc-200 pt-5">
          <span className="text-[11px] text-zinc-500">
            {dirty ? "Unsaved changes" : "Everything saved"}
          </span>
          <button
            onClick={() => void finish()}
            disabled={busy || decide.length > 0}
            title={
              decide.length
                ? "Answer the questions above first"
                : "Record that you have been through it"
            }
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 disabled:bg-zinc-300"
          >
            Finish curating
          </button>
        </div>
      </div>
    </div>
  );
}

function Card({
  item,
  trip,
  busy,
  onAction,
  onSkip,
  canSkip,
}: {
  item: AgendaItem;
  trip: Trip;
  busy: boolean;
  onAction: (op: string | null, payload: Record<string, unknown>, id: string) => void;
  onSkip: () => void;
  canSkip: boolean;
}) {
  const tone =
    item.kind === "decide"
      ? "border-amber-300 bg-amber-50"
      : "border-zinc-200 bg-white";
  const label =
    item.kind === "decide" ? "Only you know" : item.kind === "check" ? "Worth a look" : "Optional";

  return (
    <section className={`mt-6 rounded-xl border p-6 shadow-sm ${tone}`}>
      <span
        className={`text-[10px] font-semibold uppercase tracking-wide ${
          item.kind === "decide" ? "text-amber-700" : "text-zinc-400"
        }`}
      >
        {label}
      </span>
      <h2 className="mt-1.5 text-lg font-semibold tracking-tight text-zinc-900">
        {item.title}
      </h2>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-zinc-600">{item.detail}</p>

      {item.eventId && <Photos trip={trip} eventId={item.eventId} />}

      {item.code === "day_title" && item.dayId && (
        <TitleField dayId={item.dayId} onDone={() => onAction(null, {}, item.id)} />
      )}
      {item.code === "contested_place" && item.eventId && (
        <NameField
          eventId={item.eventId}
          current={item.title}
          onDone={() => onAction(null, {}, item.id)}
        />
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {item.actions.map((a) => (
          <button
            key={a.label}
            disabled={busy}
            onClick={() => onAction(a.op, a.payload, item.id)}
            className={
              a.dismiss
                ? "px-2 text-xs font-medium text-zinc-500 underline underline-offset-2"
                : "rounded-lg bg-white px-3 py-2 text-xs font-medium text-zinc-900 shadow-sm ring-1 ring-zinc-300 hover:bg-zinc-50"
            }
          >
            {a.label}
          </button>
        ))}
        {item.kind !== "decide" && (
          <button
            disabled={busy}
            onClick={() => onAction(null, {}, item.id)}
            className="rounded-lg bg-zinc-900 px-3 py-2 text-xs font-medium text-white hover:bg-zinc-700"
          >
            Looks right
          </button>
        )}
        {canSkip && (
          <button
            onClick={onSkip}
            className="px-2 text-xs text-zinc-400 hover:text-zinc-700"
          >
            Later
          </button>
        )}
      </div>
    </section>
  );
}

function Photos({ trip, eventId }: { trip: Trip; eventId: string }) {
  const openLightbox = useTrip((s) => s.openLightbox);
  const event = trip.events.find((e) => e.id === eventId);
  if (!event) return null;
  const byId = new Map(trip.media.map((m) => [m.id, m]));
  const shots = (event.selected_media_ids.length
    ? event.selected_media_ids
    : event.media_ids
  )
    .map((id) => byId.get(id))
    .filter((m) => m?.thumb_ref)
    .slice(0, 8);
  if (!shots.length) return null;

  const all = event.media_ids.map((id) => byId.get(id)).filter((m) => m?.thumb_ref);

  return (
    <div className="mt-4 grid grid-cols-8 gap-1.5">
      {shots.map((m, i) => (
        <button key={m!.id} onClick={() => openLightbox(all as never, i)}>
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

function TitleField({ dayId, onDone }: { dayId: string; onDone: () => void }) {
  const { applyOp, trip } = useTrip();
  const day = trip?.days.find((d) => d.id === dayId);
  const [text, setText] = useState(day?.title ?? "");
  return (
    <div className="mt-4 flex gap-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="min-w-0 flex-1 rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
      />
      <button
        onClick={async () => {
          if (text.trim() && text !== day?.title)
            await applyOp("set_day_title", { day_id: dayId, title: text.trim() });
          onDone();
        }}
        className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500"
      >
        Use this
      </button>
    </div>
  );
}

function NameField({
  eventId,
  current,
  onDone,
}: {
  eventId: string;
  current: string;
  onDone: () => void;
}) {
  const applyOp = useTrip((s) => s.applyOp);
  const [text, setText] = useState(current);
  return (
    <div className="mt-4 flex gap-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="min-w-0 flex-1 rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
      />
      <button
        onClick={async () => {
          if (text.trim() && text !== current)
            await applyOp("rename_event", { event_id: eventId, name: text.trim() });
          onDone();
        }}
        className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500"
      >
        Rename
      </button>
    </div>
  );
}

function Remaining({
  items,
  current,
  onJump,
}: {
  items: AgendaItem[];
  current?: AgendaItem;
  onJump: (i: number) => void;
}) {
  if (items.length < 2) return null;
  return (
    <div className="mt-6">
      <p className="text-[10px] uppercase tracking-wide text-zinc-400">Still to go</p>
      <ul className="mt-2 divide-y divide-zinc-100 rounded-lg border border-zinc-200 bg-white">
        {items.slice(0, 12).map((i, idx) => (
          <li key={i.id}>
            <button
              onClick={() => onJump(idx)}
              className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs hover:bg-zinc-50 ${
                i.id === current?.id ? "bg-indigo-50" : ""
              }`}
            >
              <span
                className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                  i.kind === "decide"
                    ? "bg-amber-400"
                    : i.kind === "check"
                      ? "bg-zinc-400"
                      : "bg-zinc-200"
                }`}
              />
              <span className="min-w-0 flex-1 truncate text-zinc-700">{i.title}</span>
              {i.mediaCount > 0 && (
                <span className="shrink-0 text-[10px] text-zinc-400">
                  {i.mediaCount} photos
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {items.length > 12 && (
        <p className="mt-1.5 text-[10px] text-zinc-400">
          and {items.length - 12} more
        </p>
      )}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center bg-zinc-50 px-10">
      <div className="text-sm text-zinc-400">{children}</div>
    </div>
  );
}
