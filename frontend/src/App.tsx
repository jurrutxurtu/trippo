import { useEffect } from "react";
import { useTrip } from "@/store/trip";
import { useApp } from "@/store/app";
import { Timeline } from "@/features/explorer/Timeline";
import { MapPane } from "@/features/map/MapPane";
import { Lightbox } from "@/components/Lightbox";
import { OpError } from "@/features/curate/Toolbar";
import { Library } from "@/features/library/Library";
import { CreateTrip } from "@/features/library/CreateTrip";
import { Progress } from "@/features/library/Progress";
import { Report } from "@/features/library/Report";
import { DayRail } from "@/features/curate/DayRail";
import { UnassignedPool } from "@/features/curate/UnassignedPool";

/**
 * Five screens, one shallow state machine: library -> create -> progress -> report -> trip.
 *
 * No router. There are five destinations, none of them deep-linkable in a useful way for a
 * local single-user app, and a router would add a dependency to solve a problem we do not
 * have.
 */
export default function App() {
  const screen = useApp((s) => s.screen);
  return screen === "trip" ? <TripScreen /> : <Shell screen={screen} />;
}

function Shell({ screen }: { screen: string }) {
  return (
    <div className="h-full overflow-y-auto">
      {screen === "library" && <Library />}
      {screen === "create" && <CreateTrip />}
      {screen === "progress" && <Progress />}
      {screen === "report" && <Report />}
    </div>
  );
}

/** The explorer: timeline left, map right, one shared selection. */
function TripScreen() {
  const { load, loading, error, trip, back, scope, lightbox, editing, undo, redo } =
    useTrip();
  const go = useApp((s) => s.go);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // The viewer owns Escape while it is open, so one press does one thing.
      if (e.key === "Escape" && !lightbox && scope !== "trip") back();
      if (!editing) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        void (e.shiftKey ? redo() : undo());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [back, scope, lightbox, editing, undo, redo]);

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
          <p className="text-sm font-medium text-zinc-900">Could not open the capsule</p>
          <p className="mt-2 text-xs leading-relaxed text-zinc-500">{error}</p>
          <button
            onClick={() => go("library")}
            className="mt-4 rounded-lg border border-zinc-300 px-4 py-2 text-xs font-medium text-zinc-700"
          >
            Back to trips
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        {/* The rail earns its width by showing which sources cover which day. */}
        <DayRail trip={trip} />
        <aside className="w-[420px] shrink-0 border-r border-zinc-200">
          <Timeline />
        </aside>
        <main className="min-w-0 flex-1">
          <MapPane />
        </main>
      </div>
      {/* Docked, and only rendered when it has something in it. */}
      <UnassignedPool />
      <Lightbox />
      <OpError />
    </div>
  );
}
