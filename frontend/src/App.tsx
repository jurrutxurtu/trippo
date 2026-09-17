import { useEffect } from "react";
import { useTrip } from "@/store/trip";
import { Timeline } from "@/features/explorer/Timeline";
import { MapPane } from "@/features/map/MapPane";
import { Lightbox } from "@/components/Lightbox";

/**
 * The capsule explorer: timeline left, map right, one shared selection.
 *
 * Deliberately not a scrolling article. A finished trip is something you navigate --
 * see docs/product/ux-flows.md §"Capsule explorer".
 */
export default function App() {
  const { load, loading, error, trip, back, scope, lightbox } = useTrip();

  useEffect(() => {
    void load();
  }, [load]);

  // Escape walks back up the scope machine: activity -> day -> trip.
  // The viewer owns Escape while it is open, so one press does one thing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !lightbox && scope !== "trip") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [back, scope, lightbox]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-50">
        <p className="text-sm text-zinc-400">Loading the capsule&hellip;</p>
      </div>
    );
  }

  if (error || !trip) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-50">
        <div className="max-w-md rounded-xl border border-zinc-200 bg-white p-6 text-center shadow-sm">
          <p className="text-sm font-medium text-zinc-900">No capsule is loaded</p>
          <p className="mt-2 text-xs leading-relaxed text-zinc-500">{error}</p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-zinc-900 px-3 py-2 text-left text-[11px] text-zinc-200">
            python -m trippo.cli serve ./Ireland.capsule
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <aside className="w-[440px] shrink-0 border-r border-zinc-200">
        <Timeline />
      </aside>
      <main className="min-w-0 flex-1">
        <MapPane />
      </main>
      <Lightbox />
    </div>
  );
}
