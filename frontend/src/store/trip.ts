import { create } from "zustand";
import type { Trip, TripEvent, TrackGeometry, Day, MediaAsset, Finding } from "@/lib/types";
import { ACTIVITY_TYPES } from "@/lib/types";

/**
 * The scope machine: `trip -> day -> activity`.
 *
 * One piece of state drives both panes. Selection moves the map; clicking the map moves
 * the selection. Keeping it in a single store -- rather than two sets of hover handlers --
 * is what stops the timeline and the map disagreeing about what is selected.
 */
export type Scope = "trip" | "day" | "activity";

interface State {
  trip: Trip | null;
  loading: boolean;
  error: string | null;

  scope: Scope;
  dayId: string | null;
  eventId: string | null;

  /** Index into the selected activity's profile, shared by the chart and the map. */
  cursorIndex: number | null;
  trackGeometry: Record<string, TrackGeometry>;
  hoveredMediaId: string | null;
  /** Open photo viewer. items is the set being browsed, not the whole trip. */
  lightbox: { items: MediaAsset[]; index: number } | null;
  /** Events whose full photo set the user has revealed, beyond the suggested selection. */
  expandedPhotos: Set<string>;

  /** Curation state. The server validates every operation and can reject it. */
  canUndo: boolean;
  canRedo: boolean;
  dirty: boolean;
  busy: boolean;
  opError: string | null;
  editing: boolean;
  review: Finding[] | null;
  aiAvailable: boolean;

  load: () => Promise<void>;
  applyOp: (op: string, payload: Record<string, unknown>) => Promise<boolean>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  save: () => Promise<void>;
  setEditing: (on: boolean) => void;
  loadReview: () => Promise<void>;
  dismissOpError: () => void;
  selectDay: (dayId: string | null) => void;
  selectEvent: (eventId: string | null) => void;
  back: () => void;
  setCursor: (i: number | null) => void;
  setHoveredMedia: (id: string | null) => void;
  loadTrack: (trackId: string) => Promise<void>;
  openLightbox: (items: MediaAsset[], index: number) => void;
  closeLightbox: () => void;
  stepLightbox: (delta: number) => void;
  toggleExpandedPhotos: (eventId: string) => void;
}

/** The server returns the whole trip plus what undo can do; mirror it verbatim. */
function applyServerState(
  set: (partial: Partial<State>) => void,
  data: { trip: Trip; canUndo: boolean; canRedo: boolean; dirty: boolean },
): void {
  set({
    trip: data.trip,
    canUndo: data.canUndo,
    canRedo: data.canRedo,
    dirty: data.dirty,
    busy: false,
    // Findings are derived from the trip, so they are stale the moment it changes.
    review: null,
  });
}

export const useTrip = create<State>((set, get) => ({
  trip: null,
  loading: true,
  error: null,
  scope: "trip",
  dayId: null,
  eventId: null,
  cursorIndex: null,
  trackGeometry: {},
  hoveredMediaId: null,
  lightbox: null,
  expandedPhotos: new Set<string>(),
  canUndo: false,
  canRedo: false,
  dirty: false,
  busy: false,
  opError: null,
  editing: false,
  review: null,
  aiAvailable: false,

  async load() {
    set({ loading: true, error: null });
    try {
      const res = await fetch("/api/trip");
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      set({ trip: (await res.json()) as Trip, loading: false });
      const health = await fetch("/api/health").then((r) => r.json());
      set({ aiAvailable: !!health.aiAvailable });
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : String(e),
        loading: false,
      });
    }
  },

  /**
   * Apply one curation operation.
   *
   * The server is the authority: it applies, re-derives, checks invariants and returns
   * the whole trip. The client never mutates the capsule itself, so it cannot drift from
   * what is on disk, nor reach a state the backend would reject.
   */
  async applyOp(op, payload) {
    set({ busy: true, opError: null });
    try {
      const res = await fetch("/api/ops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ op, payload }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        set({
          opError: body.detail ?? `${res.status} ${res.statusText}`,
          busy: false,
        });
        return false;
      }
      applyServerState(set, await res.json());
      return true;
    } catch (e) {
      set({ opError: e instanceof Error ? e.message : String(e), busy: false });
      return false;
    }
  },

  async undo() {
    const res = await fetch("/api/undo", { method: "POST" });
    if (res.ok) applyServerState(set, await res.json());
  },

  async redo() {
    const res = await fetch("/api/redo", { method: "POST" });
    if (res.ok) applyServerState(set, await res.json());
  },

  async save() {
    const res = await fetch("/api/save", { method: "POST" });
    if (res.ok) set({ dirty: false });
  },

  setEditing(on) {
    set({ editing: on });
  },

  async loadReview() {
    const res = await fetch("/api/review");
    if (!res.ok) return;
    const data = await res.json();
    set({ review: data.findings as Finding[] });
  },

  dismissOpError() {
    set({ opError: null });
  },

  selectDay(dayId) {
    if (dayId === null) {
      set({ scope: "trip", dayId: null, eventId: null, cursorIndex: null });
      return;
    }
    set({ scope: "day", dayId, eventId: null, cursorIndex: null });
  },

  selectEvent(eventId) {
    const { trip } = get();
    if (!eventId || !trip) {
      set({ eventId: null, cursorIndex: null });
      return;
    }
    const event = trip.events.find((e) => e.id === eventId);
    if (!event) return;

    // Opening a track-bearing activity drops into the deepest scope; anything else stays
    // at day level, because a visit has nothing extra to show on its own.
    const isActivity = ACTIVITY_TYPES.has(event.type) && event.track_ids.length > 0;
    set({
      eventId,
      dayId: event.day_id ?? get().dayId,
      scope: isActivity ? "activity" : "day",
      cursorIndex: null,
    });
    if (isActivity && event.track_ids[0]) void get().loadTrack(event.track_ids[0]);
  },

  back() {
    const { scope } = get();
    if (scope === "activity") set({ scope: "day", eventId: null, cursorIndex: null });
    else if (scope === "day") set({ scope: "trip", dayId: null, eventId: null });
  },

  setCursor(i) {
    set({ cursorIndex: i });
  },

  setHoveredMedia(id) {
    set({ hoveredMediaId: id });
  },

  openLightbox(items, index) {
    if (items.length) set({ lightbox: { items, index } });
  },

  closeLightbox() {
    set({ lightbox: null });
  },

  stepLightbox(delta) {
    const lb = get().lightbox;
    if (!lb) return;
    const n = lb.items.length;
    set({ lightbox: { ...lb, index: (lb.index + delta + n) % n } });
  },

  toggleExpandedPhotos(eventId) {
    const next = new Set(get().expandedPhotos);
    if (next.has(eventId)) next.delete(eventId);
    else next.add(eventId);
    set({ expandedPhotos: next });
  },

  async loadTrack(trackId) {
    if (get().trackGeometry[trackId]) return;
    try {
      const res = await fetch(`/api/tracks/${trackId}`);
      if (!res.ok) return;
      const geom = (await res.json()) as TrackGeometry;
      set((s) => ({ trackGeometry: { ...s.trackGeometry, [trackId]: geom } }));
    } catch {
      // A missing profile degrades to "no chart", never to a broken page.
    }
  },
}));

// --------------------------------------------------------------------- selectors

export function selectedDay(s: State): Day | null {
  if (!s.trip || !s.dayId) return null;
  return s.trip.days.find((d) => d.id === s.dayId) ?? null;
}

export function selectedEvent(s: State): TripEvent | null {
  if (!s.trip || !s.eventId) return null;
  return s.trip.events.find((e) => e.id === s.eventId) ?? null;
}

export function dayEvents(trip: Trip, day: Day): TripEvent[] {
  const byId = new Map(trip.events.map((e) => [e.id, e]));
  return day.event_ids
    .map((id) => byId.get(id))
    .filter((e): e is TripEvent => !!e && e.status === "active");
}

/**
 * Photographs for an event, honouring the suggested selection.
 *
 * An event can own 87 photographs. The selection is a small, well-spread subset chosen by
 * the backend; the rest appear when the user expands. Nothing is hidden permanently.
 */
export function eventPhotos(
  trip: Trip,
  event: TripEvent,
  expanded: boolean,
): { shown: MediaAsset[]; all: MediaAsset[]; hidden: number } {
  const byId = new Map(trip.media.map((m) => [m.id, m]));
  const all = event.media_ids
    .map((id) => byId.get(id))
    .filter((m): m is MediaAsset => !!m && !!m.thumb_ref);

  if (expanded || event.selected_media_ids.length === 0) {
    return { shown: all, all, hidden: 0 };
  }
  const selected = new Set(event.selected_media_ids);
  const shown = all.filter((m) => selected.has(m.id));
  return { shown, all, hidden: all.length - shown.length };
}

export function spanningEvents(trip: Trip, day: Day): TripEvent[] {
  const byId = new Map(trip.events.map((e) => [e.id, e]));
  return day.spanning_event_ids
    .map((id) => byId.get(id))
    .filter((e): e is TripEvent => !!e && e.status === "active");
}
