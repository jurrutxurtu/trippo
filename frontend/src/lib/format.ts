import type { Day, EventType, TripEvent } from "./types";

/** Event types get an icon and a MUTED colour. Saturated colour means status. */
export const TYPE_META: Record<EventType, { icon: string; dot: string; label: string }> = {
  drive: { icon: "\u{1F697}", dot: "bg-zinc-300", label: "Drive" },
  stop: { icon: "\u{1F4CD}", dot: "bg-zinc-300", label: "Stop" },
  visit: { icon: "\u{1F3DB}", dot: "bg-sky-300", label: "Visit" },
  overnight: { icon: "\u{1F303}", dot: "bg-violet-300", label: "Overnight" },
  hike: { icon: "\u26F0", dot: "bg-emerald-400", label: "Hike" },
  walk: { icon: "\u{1F6B6}", dot: "bg-teal-300", label: "Walk" },
  bike: { icon: "\u{1F6B2}", dot: "bg-lime-300", label: "Bike" },
  flight: { icon: "\u2708", dot: "bg-fuchsia-300", label: "Flight" },
  ferry: { icon: "\u26F4", dot: "bg-cyan-300", label: "Ferry" },
  unknown: { icon: "\u2757", dot: "bg-amber-400", label: "Unaccounted" },
};

export function km(metres: number, digits = 0): string {
  return `${(metres / 1000).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} km`;
}

export function duration(seconds: number): string {
  const mins = seconds / 60;
  if (mins < 90) return `${Math.round(mins)} min`;
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  return m ? `${h}h ${m}m` : `${h}h`;
}

/**
 * Wall-clock time at the place it happened.
 *
 * Always local to the location, never to the machine reading it: a ferry leaving Rosslare
 * at 21:00 should say 21:00 in Bilbao too.
 */
export function localTime(iso: string, offsetMinutes: number | null): string {
  const t = new Date(iso).getTime() + (offsetMinutes ?? 0) * 60_000;
  return new Date(t).toISOString().slice(11, 16);
}

export function localDate(iso: string, offsetMinutes: number | null): Date {
  return new Date(new Date(iso).getTime() + (offsetMinutes ?? 0) * 60_000);
}

export function formatDate(iso: string, style: "short" | "long" = "short"): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", {
    weekday: style === "long" ? "long" : "short",
    day: "numeric",
    month: style === "long" ? "long" : "short",
    timeZone: "UTC",
  });
}

export function eventName(e: TripEvent): string {
  return e.title || e.place?.name || TYPE_META[e.type].label;
}

/** A coordinate label is not a name. Used to decide when to show a place as resolved. */
export function isResolved(e: TripEvent): boolean {
  return !!e.place && e.place.source !== "coords";
}

/** Contested: the geocoder had two close candidates and picked one. */
export function isContested(e: TripEvent): boolean {
  return (
    !!e.place &&
    (e.place.source === "osm" || e.place.source === "nominatim") &&
    e.place.confidence < 0.9
  );
}

export function dayDistance(day: Day): number {
  return Object.values(day.stats.distance_by_mode_m).reduce((a, b) => a + b, 0);
}
