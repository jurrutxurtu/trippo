import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useTrip } from "@/store/trip";
import { TYPE_META, duration, km } from "@/lib/format";
import type { TripEvent } from "@/lib/types";
import { PhotoStrip } from "@/components/PhotoStrip";

/**
 * Activity detail: telemetry, the summits crossed, and the elevation profile.
 *
 * The chart and the map share ONE cursor index in the store. Hovering the chart moves the
 * marker on the map; the same index would move the chart from a map hover. Two independent
 * hover handlers would drift apart -- this cannot.
 */
export function ActivityPanel({ event }: { event: TripEvent }) {
  const { trackGeometry, setCursor, back } = useTrip();
  const trackId = event.track_ids[0];
  const geom = trackId ? trackGeometry[trackId] : undefined;
  const detail = event.detail.kind === "activity" ? event.detail : null;
  const stats = detail?.stats;

  return (
    <div>
      <div className="sticky top-0 z-10 border-b border-zinc-200 bg-white px-6 py-4">
        <button
          onClick={back}
          className="text-[11px] font-medium text-zinc-400 hover:text-zinc-700"
        >
          &larr; Back to the day
        </button>
        <h2 className="mt-1.5 flex items-center gap-2 text-lg font-semibold tracking-tight text-zinc-900">
          <span>{TYPE_META[event.type].icon}</span>
          {event.title ?? event.place?.name}
        </h2>
      </div>

      {stats && (
        <div className="grid grid-cols-3 gap-px border-b border-zinc-200 bg-zinc-200">
          <Metric value={km(stats.distance_m, 1)} label="distance" />
          <Metric value={`+${Math.round(stats.ascent_m)} m`} label="ascent" accent />
          <Metric
            value={stats.max_ele_m ? `${Math.round(stats.max_ele_m)} m` : "\u2014"}
            label="highest"
          />
          <Metric value={duration(stats.moving_time_s)} label="moving" />
          <Metric value={`\u2212${Math.round(stats.descent_m)} m`} label="descent" />
          <Metric
            value={stats.avg_hr ? `${Math.round(stats.avg_hr)} bpm` : "\u2014"}
            label="avg heart rate"
          />
        </div>
      )}

      {detail && detail.highlights.length > 0 && (
        <div className="border-b border-zinc-200 px-6 py-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            Passed through
          </h3>
          <ul className="mt-2.5 space-y-1.5">
            {detail.highlights.map((h) => (
              <li key={`${h.name}-${h.offset_m}`} className="flex items-baseline gap-2">
                <span className="text-xs">
                  {h.kind === "natural=peak" ? "\u26F0" : h.kind.includes("water") ? "\u{1F4A7}" : "\u21F1"}
                </span>
                <span className="flex-1 truncate text-xs text-zinc-900">{h.name}</span>
                {h.ele_m != null && (
                  <span className="tnum shrink-0 text-[11px] font-medium text-emerald-700">
                    {Math.round(h.ele_m)} m
                  </span>
                )}
                <span className="tnum shrink-0 text-[11px] text-zinc-400">
                  {(h.offset_m / 1000).toFixed(1)} km
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {geom ? (
        <Profile
          profile={geom.profile}
          threshold={stats?.elevation_threshold_m ?? 0}
          onCursor={setCursor}
        />
      ) : (
        <p className="px-6 py-8 text-center text-xs text-zinc-400">
          Loading the elevation profile&hellip;
        </p>
      )}

      <ActivityPhotos event={event} />
    </div>
  );
}

function Metric({
  value,
  label,
  accent,
}: {
  value: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-white px-4 py-3">
      <div
        className={`tnum text-base font-semibold tracking-tight ${
          accent ? "text-emerald-700" : "text-zinc-900"
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wide text-zinc-400">{label}</div>
    </div>
  );
}

function Profile({
  profile,
  threshold,
  onCursor,
}: {
  profile: { d: number; ele: number }[];
  threshold: number;
  onCursor: (i: number | null) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<uPlot | null>(null);

  const data = useMemo<uPlot.AlignedData>(
    () => [
      profile.map((p) => p.d / 1000),
      profile.map((p) => p.ele),
    ],
    [profile],
  );

  useEffect(() => {
    if (!host.current || profile.length === 0) return;
    const width = host.current.clientWidth;

    const opts: uPlot.Options = {
      width,
      height: 150,
      padding: [8, 8, 0, 0],
      cursor: {
        y: false,
        points: { size: 7 },
      },
      legend: { show: false },
      scales: { x: { time: false } },
      axes: [
        {
          stroke: "#a1a1aa",
          grid: { stroke: "#f4f4f5" },
          ticks: { stroke: "#e4e4e7" },
          size: 28,
          values: (_u, vals) => vals.map((v) => `${v.toFixed(0)}`),
          font: "10px ui-sans-serif, system-ui",
        },
        {
          stroke: "#a1a1aa",
          grid: { stroke: "#f4f4f5" },
          ticks: { stroke: "#e4e4e7" },
          size: 38,
          font: "10px ui-sans-serif, system-ui",
        },
      ],
      series: [
        {},
        {
          stroke: "#0f9d76",
          width: 1.5,
          fill: "rgba(15,157,118,0.12)",
        },
      ],
      hooks: {
        // The single source of truth for "where on the route are we looking?".
        setCursor: [(u) => onCursor(u.cursor.idx ?? null)],
      },
    };

    chart.current = new uPlot(opts, data, host.current);
    const onResize = () =>
      chart.current?.setSize({ width: host.current!.clientWidth, height: 150 });
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.current?.destroy();
      chart.current = null;
    };
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className="border-b border-zinc-200 px-6 py-4"
      onMouseLeave={() => onCursor(null)}
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
          Elevation
        </h3>
        <span className="text-[10px] text-zinc-400">
          gain counted above {Math.round(threshold)} m steps
        </span>
      </div>
      <div ref={host} className="mt-2" />
      <p className="mt-1 text-center text-[10px] text-zinc-400">kilometres</p>
    </div>
  );
}

function ActivityPhotos({ event }: { event: TripEvent }) {
  const trip = useTrip((s) => s.trip);
  if (!trip || event.media_ids.length === 0) return null;
  return (
    <div className="px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
        Photographs{" "}
        <span className="font-normal text-zinc-400">{event.media_ids.length}</span>
      </h3>
      <PhotoStrip trip={trip} event={event} columns={4} />
    </div>
  );
}