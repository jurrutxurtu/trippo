import { useState } from "react";
import { useTrip } from "@/store/trip";

/**
 * Ask for title suggestions for a day.
 *
 * Hidden entirely when no model is configured -- not greyed out. The deterministic title
 * stays the default; a suggestion is only ever applied when the user picks one.
 */
export function TitleSuggester({ dayId, current }: { dayId: string; current: string }) {
  const { aiAvailable, applyOp } = useTrip();
  const [options, setOptions] = useState<string[] | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "empty">("idle");

  if (!aiAvailable) return null;

  const ask = async () => {
    setState("loading");
    setOptions(null);
    try {
      const res = await fetch("/api/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "day_title", day_id: dayId }),
      });
      if (res.status === 204) {
        setState("empty");
        return;
      }
      const data = await res.json();
      if (!data.ok) {
        setState("empty");
        return;
      }
      setOptions([data.value, ...(data.alternatives ?? [])]);
      setState("idle");
    } catch {
      setState("empty");
    }
  };

  return (
    <div className="mt-2">
      <button
        onClick={() => void ask()}
        disabled={state === "loading"}
        className="text-[11px] font-medium text-indigo-600 hover:underline disabled:opacity-50"
      >
        {state === "loading" ? "Thinking\u2026" : "Suggest a title"}
      </button>

      {state === "empty" && (
        <p className="mt-1 text-[11px] text-zinc-400">
          No usable suggestion &mdash; keeping &ldquo;{current}&rdquo;.
        </p>
      )}

      {options && (
        <ul className="mt-1.5 space-y-1">
          {options.map((t) => (
            <li key={t}>
              <button
                onClick={() => {
                  void applyOp("set_day_title", { day_id: dayId, title: t });
                  setOptions(null);
                }}
                className="w-full rounded-lg border border-zinc-200 px-2.5 py-1.5 text-left text-xs text-zinc-800 hover:border-indigo-300 hover:bg-indigo-50"
              >
                {t}
              </button>
            </li>
          ))}
          <li>
            <button
              onClick={() => setOptions(null)}
              className="text-[11px] text-zinc-400 hover:text-zinc-700"
            >
              Keep the current title
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
