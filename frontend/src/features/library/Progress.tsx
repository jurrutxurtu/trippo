import { useEffect, useRef } from "react";
import { useApp } from "@/store/app";

const STAGES = [
  ["timeline", "Location history"],
  ["gpx", "GPS tracks"],
  ["media", "Photographs"],
  ["build", "Working out the itinerary"],
  ["enrich", "Place names"],
  ["summits", "Summits"],
  ["thumbnails", "Thumbnails"],
  ["save", "Saving"],
] as const;

/**
 * Live import progress.
 *
 * Ingestion takes minutes, so it says what it is doing rather than spinning. The stage
 * list doubles as an explanation of what Trippo actually does to your files.
 */
export function Progress() {
  const { jobEvents, jobStatus, jobError, go, draft, startBuild } = useApp();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [jobEvents.length]);

  const latest = jobEvents[jobEvents.length - 1];
  const seen = new Set(jobEvents.map((e) => e.stage));
  const activeStage = latest?.stage;

  return (
    <div className="flex min-h-full items-center justify-center bg-zinc-50 px-10 py-12">
      <div className="w-full max-w-2xl">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
          {jobStatus === "failed"
            ? "The import stopped"
            : jobStatus === "done"
              ? "Done"
              : `Building ${draft.title || "your trip"}`}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {jobStatus === "running"
            ? "This takes a few minutes the first time. Thumbnails are the slow part."
            : jobStatus === "failed"
              ? "Nothing was changed on disk beyond a partial capsule."
              : "Opening the report\u2026"}
        </p>

        <ol className="mt-8 space-y-1.5">
          {STAGES.map(([key, label]) => {
            const done = seen.has(key) && activeStage !== key;
            const active = activeStage === key;
            const stageEvents = jobEvents.filter((e) => e.stage === key);
            const last = stageEvents[stageEvents.length - 1];
            const pct =
              last && last.total > 0
                ? Math.min(100, Math.round((last.done / last.total) * 100))
                : null;

            return (
              <li
                key={key}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 ${
                  active ? "bg-white shadow-sm ring-1 ring-indigo-200" : ""
                }`}
              >
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] ${
                    done
                      ? "bg-emerald-500 text-white"
                      : active
                        ? "bg-indigo-600 text-white"
                        : "bg-zinc-200 text-zinc-400"
                  }`}
                >
                  {done ? "\u2713" : active ? "\u2022" : ""}
                </span>
                <span
                  className={`w-52 shrink-0 text-xs ${
                    done || active ? "font-medium text-zinc-900" : "text-zinc-400"
                  }`}
                >
                  {label}
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-zinc-500">
                  {last?.message ?? ""}
                </span>
                {pct !== null && active && (
                  <span className="tnum shrink-0 text-[11px] text-zinc-400">{pct}%</span>
                )}
              </li>
            );
          })}
        </ol>

        <div
          ref={logRef}
          className="mt-6 h-32 overflow-y-auto rounded-lg bg-zinc-900 px-4 py-3 font-mono text-[11px] leading-relaxed text-zinc-400"
        >
          {jobEvents.map((e, i) => (
            <div key={i}>
              <span className="text-zinc-600">{e.stage}</span> {e.message}
            </div>
          ))}
          {jobEvents.length === 0 && <span className="text-zinc-600">starting&hellip;</span>}
        </div>

        {jobStatus === "failed" && (
          <div className="mt-5 rounded-lg bg-red-50 px-4 py-3 ring-1 ring-red-200">
            <p className="text-xs font-medium text-red-900">
              {jobError ?? "The import stopped without saying why."}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-red-800/80">
              The stages above show how far it got. Your photographs and tracks were not
              modified.
            </p>
            <div className="mt-3 flex gap-3">
              <button
                onClick={() => go("create")}
                className="text-xs font-medium text-red-900 underline"
              >
                Back to the form
              </button>
              <button
                onClick={() => void startBuild()}
                className="text-xs font-medium text-red-900 underline"
              >
                Try again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
