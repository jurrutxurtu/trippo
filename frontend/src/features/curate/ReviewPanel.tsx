import { useEffect } from "react";
import { useTrip } from "@/store/trip";

/**
 * What is worth checking before calling a trip finished.
 *
 * Almost entirely computed, not generated: unresolved gaps, photographs in the pool,
 * days with nothing on them. Only blocking findings actually stop you.
 */
export function ReviewPanel() {
  const { review, loadReview, selectDay, selectEvent, trip } = useTrip();

  useEffect(() => {
    if (review === null) void loadReview();
  }, [review, loadReview]);

  if (!trip) return null;
  if (review === null) {
    return <p className="px-5 py-8 text-center text-xs text-zinc-400">Checking&hellip;</p>;
  }
  if (review.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <p className="text-sm font-medium text-zinc-900">Nothing to flag</p>
        <p className="mt-1 text-xs text-zinc-500">This trip looks finished.</p>
      </div>
    );
  }

  const tone = {
    blocking: "border-amber-300 bg-amber-50",
    warning: "border-zinc-200 bg-white",
    info: "border-zinc-200 bg-zinc-50",
  } as const;
  const mark = { blocking: "!", warning: "~", info: "\u00b7" } as const;

  return (
    <div className="space-y-2 px-5 py-4">
      {review.map((f, i) => (
        <button
          key={`${f.code}-${i}`}
          onClick={() => {
            if (f.eventId) selectEvent(f.eventId);
            else if (f.dayId) selectDay(f.dayId);
          }}
          className={`block w-full rounded-lg border px-3 py-2.5 text-left ${tone[f.severity]} hover:border-zinc-300`}
        >
          <p className="flex gap-2 text-xs font-medium text-zinc-900">
            <span
              className={
                f.severity === "blocking" ? "text-amber-600" : "text-zinc-400"
              }
            >
              {mark[f.severity]}
            </span>
            {f.message}
          </p>
          {f.action && (
            <p className="mt-1 pl-4 text-[11px] leading-relaxed text-zinc-500">
              {f.action}
            </p>
          )}
        </button>
      ))}
    </div>
  );
}
