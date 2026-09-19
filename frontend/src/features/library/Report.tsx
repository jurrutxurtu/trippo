import { useApp } from "@/store/app";
import { formatDate } from "@/lib/format";

/**
 * The ingestion report, shown BEFORE the itinerary.
 *
 * This is the step that turns "why is day 3 empty?" into "day 3 has no data, and here is
 * why". Presenting an itinerary first and the caveats later gets the order exactly wrong:
 * the reader has already decided the app is broken.
 */
export function Report() {
  const { report, go } = useApp();

  if (!report) {
    return (
      <div className="flex min-h-full items-center justify-center bg-zinc-50">
        <p className="text-sm text-zinc-400">Reading the report&hellip;</p>
      </div>
    );
  }

  const blind = report.coverage.filter(
    (c) => !c.timeline_records && !c.media_count && !c.track_count,
  ).length;

  return (
    <div className="min-h-full bg-zinc-50">
      <div className="mx-auto max-w-4xl px-10 py-12">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          What Trippo found
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Worth a glance before you look at the itinerary.
        </p>

        <section className="mt-8 space-y-3">
          {report.sources.map((s) => (
            <div
              key={s.kind + s.name}
              className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-baseline justify-between">
                <h2 className="text-sm font-semibold capitalize text-zinc-900">
                  {s.kind}
                  <span className="ml-2 font-mono text-[11px] font-normal text-zinc-400">
                    {s.name}
                  </span>
                </h2>
                <span className="rounded bg-zinc-100 px-2 py-0.5 text-[10px] text-zinc-600">
                  {s.format}
                </span>
              </div>
              {s.report && (
                <p className="tnum mt-2 flex flex-wrap gap-x-4 text-[11px] text-zinc-500">
                  {s.report.files_seen > 0 && (
                    <span>
                      {s.report.files_parsed.toLocaleString()} of{" "}
                      {s.report.files_seen.toLocaleString()} files read
                    </span>
                  )}
                  {s.report.records_total > 0 && (
                    <span>
                      {s.report.records_in_window.toLocaleString()} of{" "}
                      {s.report.records_total.toLocaleString()} records in range
                    </span>
                  )}
                  {s.report.skipped.length > 0 && (
                    <span className="text-amber-600">
                      {s.report.skipped.length} skipped
                    </span>
                  )}
                </p>
              )}
              {s.report?.notes.map((n) => (
                <p key={n} className="mt-1 text-[11px] text-zinc-400">
                  {n}
                </p>
              ))}
            </div>
          ))}
        </section>

        {report.degradations.length > 0 && (
          <section className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-5">
            <h2 className="text-sm font-semibold text-amber-900">Worth knowing</h2>
            <ul className="mt-3 space-y-2">
              {report.degradations.map((d) => (
                <li key={d} className="flex gap-2 text-xs leading-relaxed text-amber-900">
                  <span className="shrink-0 text-amber-600">&#9888;</span>
                  {d}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="mt-6 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-zinc-900">Coverage by day</h2>
            <div className="flex items-center gap-3 text-[10px] text-zinc-500">
              <Legend colour="bg-sky-400" label="timeline" />
              <Legend colour="bg-violet-400" label="photos" />
              <Legend colour="bg-emerald-500" label="tracks" />
            </div>
          </div>

          <div className="mt-4 grid grid-cols-7 gap-1.5">
            {report.coverage.map((c) => {
              const isBlind = !c.timeline_records && !c.media_count && !c.track_count;
              return (
                <div
                  key={c.date}
                  title={`${c.date}: ${c.timeline_records} timeline, ${c.media_count} photos, ${c.track_count} tracks`}
                  className={`rounded-lg border px-2 py-1.5 ${
                    isBlind ? "border-amber-200 bg-amber-50" : "border-zinc-200"
                  }`}
                >
                  <div className="text-[10px] text-zinc-500">{formatDate(c.date)}</div>
                  <div className="mt-1 flex gap-0.5">
                    <Bar on={c.timeline_records > 0} colour="bg-sky-400" />
                    <Bar on={c.media_count > 0} colour="bg-violet-400" />
                    <Bar on={c.track_count > 0} colour="bg-emerald-500" />
                  </div>
                </div>
              );
            })}
          </div>

          {blind > 0 && (
            <p className="mt-3 text-[11px] text-zinc-500">
              {blind} {blind === 1 ? "day has" : "days have"} no data at all. That is not a
              bug &mdash; Trippo will show them as unaccounted rather than inventing
              something.
            </p>
          )}
        </section>

        <div className="mt-8 flex justify-end gap-2">
          <button
            onClick={() => go("library")}
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-white"
          >
            Back to trips
          </button>
          <button
            onClick={() => go("trip")}
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-white"
          >
            Just show me the trip
          </button>
          <button
            onClick={() => go("curate")}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500"
          >
            Agree the itinerary &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}

function Bar({ on, colour }: { on: boolean; colour: string }) {
  return <span className={`h-1 flex-1 rounded-sm ${on ? colour : "bg-zinc-200"}`} />;
}

function Legend({ colour, label }: { colour: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`h-1 w-3 rounded-sm ${colour}`} />
      {label}
    </span>
  );
}
