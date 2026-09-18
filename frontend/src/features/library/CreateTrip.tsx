import { useState } from "react";
import { useApp } from "@/store/app";

/**
 * Creating a trip.
 *
 * Every source is optional -- a folder of photographs is enough. Paths come from a native
 * dialog opened by the backend, with a paste-a-path fallback for anyone running it
 * elsewhere.
 */
export function CreateTrip() {
  const { draft, setDraft, pick, setPath, picking, proposing, startBuild, createError, go } =
    useApp();
  const hasSource = !!(draft.timeline || draft.gpx || draft.media.length);

  return (
    <div className="min-h-full bg-zinc-50">
      <div className="mx-auto max-w-[1100px] px-10 py-10">
        <header className="mb-8 flex items-baseline justify-between">
          <div>
            <button
              onClick={() => go("library")}
              className="text-[11px] font-medium text-zinc-400 hover:text-zinc-700"
            >
              &larr; All trips
            </button>
            <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-zinc-900">
              New trip
            </h1>
            <p className="mt-1 text-sm text-zinc-500">
              Add whatever you have. Every source is optional.
            </p>
          </div>
        </header>

        <div className="grid grid-cols-12 gap-6">
          <section className="col-span-5 space-y-4">
            <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-zinc-900">Details</h2>

              <label className="mt-5 block">
                <span className="text-xs font-medium text-zinc-600">Title</span>
                <input
                  value={draft.title}
                  onChange={(e) => setDraft({ title: e.target.value })}
                  placeholder="Ireland 2023"
                  className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                />
              </label>

              <label className="mt-4 block">
                <span className="text-xs font-medium text-zinc-600">
                  Description <span className="font-normal text-zinc-400">&middot; optional</span>
                </span>
                <textarea
                  rows={3}
                  value={draft.description}
                  onChange={(e) => setDraft({ description: e.target.value })}
                  placeholder="Three weeks around the island in the van&hellip;"
                  className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                />
              </label>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs font-medium text-zinc-600">From</span>
                  <input
                    type="date"
                    value={draft.dateFrom}
                    onChange={(e) => setDraft({ dateFrom: e.target.value })}
                    className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-zinc-600">To</span>
                  <input
                    type="date"
                    value={draft.dateTo}
                    onChange={(e) => setDraft({ dateTo: e.target.value })}
                    className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  />
                </label>
              </div>
              <p className="mt-2 text-xs text-zinc-500">
                {proposing
                  ? "Reading your photo timestamps\u2026"
                  : draft.dateFrom
                    ? "Proposed from your photographs. Edit if the trip started earlier."
                    : "Leave blank to use everything in the sources."}
              </p>
            </div>

            <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-zinc-900">What to do on import</h2>
              <Toggle
                checked={draft.enrich}
                onChange={(v) => setDraft({ enrich: v })}
                title="Look up place names"
                detail="Sends coordinates to OpenStreetMap. Without this, stops are labelled by latitude. Takes a few minutes the first time."
              />
              <Toggle
                checked={draft.derivatives}
                onChange={(v) => setDraft({ derivatives: v })}
                title="Make thumbnails"
                detail="Needed to see photographs in the app. Roughly a minute per 200 photos; originals are never modified or copied."
              />
              <p className="mt-4 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-500">
                Your originals never leave this machine.
              </p>
            </div>
          </section>

          <section className="col-span-7 space-y-4">
            <SourceCard
              title="Photos and videos"
              hint="A folder. Sub-folders are included."
              value={draft.media.join("  \u00b7  ")}
              onPick={() => void pick("media")}
              onPaste={(v) => setPath("media", v)}
              onClear={() => setDraft({ media: [] })}
              picking={picking}
              multiple
            />
            <SourceCard
              title="GPS tracks"
              hint="A folder of .gpx files from Garmin, Strava, Wikiloc\u2026"
              value={draft.gpx ?? ""}
              onPick={() => void pick("gpx")}
              onPaste={(v) => setPath("gpx", v)}
              onClear={() => setDraft({ gpx: null })}
              picking={picking}
            />
            <SourceCard
              title="Location history"
              hint="The Timeline JSON from a Google Takeout or on-device export."
              value={draft.timeline ?? ""}
              onPick={() => void pick("timeline")}
              onPaste={(v) => setPath("timeline", v)}
              onClear={() => setDraft({ timeline: null })}
              picking={picking}
              file
            />

            {createError && (
              <p className="rounded-lg bg-red-50 px-4 py-3 text-xs text-red-800 ring-1 ring-red-200">
                {createError}
              </p>
            )}

            <div className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
              <p className="text-xs text-zinc-500">
                Nothing is copied or uploaded. Trippo reads your files where they are.
              </p>
              <button
                disabled={!hasSource}
                onClick={() => void startBuild()}
                className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 disabled:bg-zinc-300"
              >
                Build the trip
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  title,
  detail,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  detail: string;
}) {
  return (
    <label className="mt-4 flex items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
      />
      <span className="text-xs leading-relaxed text-zinc-600">
        <span className="font-medium text-zinc-900">{title}</span>
        <br />
        {detail}
      </span>
    </label>
  );
}

function SourceCard({
  title,
  hint,
  value,
  onPick,
  onPaste,
  onClear,
  picking,
  multiple,
  file,
}: {
  title: string;
  hint: string;
  value: string;
  onPick: () => void;
  onPaste: (v: string) => void;
  onClear: () => void;
  picking: boolean;
  multiple?: boolean;
  file?: boolean;
}) {
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-500">
              optional
            </span>
            {value && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                chosen
              </span>
            )}
          </div>
          {value ? (
            <p className="mt-2 break-all font-mono text-[11px] text-zinc-700">{value}</p>
          ) : (
            <p className="mt-1.5 text-xs text-zinc-500">{hint}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={onPick}
            disabled={picking}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            {picking ? "Waiting\u2026" : value && !multiple ? "Change" : `Choose ${file ? "file" : "folder"}\u2026`}
          </button>
          {value && (
            <button
              onClick={onClear}
              className="text-[11px] text-zinc-400 hover:text-zinc-700"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Fallback for a backend running somewhere without a desktop. */}
      {typing ? (
        <div className="mt-3 flex gap-1.5">
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="C:\\Users\\you\\Pictures\\Ireland"
            className="min-w-0 flex-1 rounded-lg border-zinc-300 font-mono text-[11px] focus:border-indigo-500 focus:ring-indigo-500"
          />
          <button
            onClick={() => {
              onPaste(text);
              setText("");
              setTyping(false);
            }}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-[11px] font-medium text-white"
          >
            Use
          </button>
          <button
            onClick={() => setTyping(false)}
            className="px-2 text-[11px] text-zinc-500"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setTyping(true)}
          className="mt-2 text-[11px] text-zinc-400 hover:text-zinc-700"
        >
          or paste a path
        </button>
      )}
    </div>
  );
}
