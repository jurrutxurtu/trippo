import { create } from "zustand";
import type { CapsuleSummary, IngestReport, JobEvent } from "@/lib/types";

/**
 * Screen-level navigation and trip creation.
 *
 * Kept separate from the trip store: that one is about a single open capsule, this one is
 * about getting to it. Mixing them would mean the explorer re-renders every time a file
 * picker returns.
 */
export type Screen = "library" | "create" | "progress" | "report" | "curate" | "trip";

export interface Draft {
  title: string;
  description: string;
  timeline: string | null;
  gpx: string | null;
  media: string[];
  dateFrom: string;
  dateTo: string;
  enrich: boolean;
  derivatives: boolean;
}

const EMPTY_DRAFT: Draft = {
  title: "",
  description: "",
  timeline: null,
  gpx: null,
  media: [],
  dateFrom: "",
  dateTo: "",
  enrich: true,
  derivatives: true,
};

interface State {
  screen: Screen;
  capsules: CapsuleSummary[];
  workspace: string;
  loadingLibrary: boolean;

  draft: Draft;
  picking: boolean;
  proposing: boolean;
  createError: string | null;

  jobId: string | null;
  jobEvents: JobEvent[];
  jobStatus: "idle" | "running" | "done" | "failed";
  jobError: string | null;
  newCapsuleId: string | null;

  report: IngestReport | null;

  go: (screen: Screen) => void;
  loadLibrary: () => Promise<void>;
  openCapsule: (id: string) => Promise<boolean>;
  deleteCapsule: (id: string) => Promise<void>;

  setDraft: (patch: Partial<Draft>) => void;
  resetDraft: () => void;
  pick: (field: "timeline" | "gpx" | "media") => Promise<void>;
  setPath: (field: "timeline" | "gpx" | "media", value: string) => void;
  proposeDates: () => Promise<void>;
  startBuild: () => Promise<void>;
  loadReport: () => Promise<void>;
}

export const useApp = create<State>((set, get) => ({
  screen: "library",
  capsules: [],
  workspace: "",
  loadingLibrary: true,

  draft: { ...EMPTY_DRAFT },
  picking: false,
  proposing: false,
  createError: null,

  jobId: null,
  jobEvents: [],
  jobStatus: "idle",
  jobError: null,
  newCapsuleId: null,

  report: null,

  go(screen) {
    set({ screen });
  },

  async loadLibrary() {
    set({ loadingLibrary: true });
    try {
      const data = await fetch("/api/capsules").then((r) => r.json());
      set({
        capsules: data.capsules ?? [],
        workspace: data.workspace ?? "",
        loadingLibrary: false,
      });
    } catch {
      set({ loadingLibrary: false });
    }
  },

  async openCapsule(id) {
    const res = await fetch(`/api/capsules/${encodeURIComponent(id)}/open`, {
      method: "POST",
    });
    if (!res.ok) return false;
    set({ screen: "trip", report: null });
    return true;
  },

  async deleteCapsule(id) {
    await fetch(`/api/capsules/${encodeURIComponent(id)}`, { method: "DELETE" });
    await get().loadLibrary();
  },

  setDraft(patch) {
    set({ draft: { ...get().draft, ...patch }, createError: null });
  },

  resetDraft() {
    set({ draft: { ...EMPTY_DRAFT }, createError: null, jobEvents: [] });
  },

  /**
   * Ask the backend to open a native folder dialog.
   *
   * The backend runs on this machine, so the dialog appears on the user's desktop and
   * returns a real path. A browser cannot do this, and uploading 8 GB to work around it
   * would defeat the point.
   */
  async pick(field) {
    set({ picking: true });
    try {
      const titles = {
        timeline: "Choose your Google Timeline JSON",
        gpx: "Choose the folder with your GPX tracks",
        media: "Choose the folder with your photographs",
      };
      const res = await fetch("/api/browse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: field === "timeline" ? "file" : "folder",
          title: titles[field],
        }),
      });
      const { path } = await res.json();
      if (path) get().setPath(field, path);
      if (path && field === "media") void get().proposeDates();
    } finally {
      set({ picking: false });
    }
  },

  setPath(field, value) {
    const v = value.trim();
    if (field === "media") {
      const media = v ? [...new Set([...get().draft.media, v])] : get().draft.media;
      set({ draft: { ...get().draft, media }, createError: null });
    } else {
      set({ draft: { ...get().draft, [field]: v || null }, createError: null });
    }
  },

  /** Nobody remembers exactly when they left; the photographs do. */
  async proposeDates() {
    const { media, dateFrom, dateTo } = get().draft;
    if (!media.length || (dateFrom && dateTo)) return;
    set({ proposing: true });
    try {
      const res = await fetch("/api/propose-dates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ media }),
      });
      const { start, end } = await res.json();
      if (start && end)
        set({ draft: { ...get().draft, dateFrom: start, dateTo: end } });
    } finally {
      set({ proposing: false });
    }
  },

  async startBuild() {
    const d = get().draft;
    if (!d.timeline && !d.gpx && !d.media.length) {
      set({ createError: "Add at least one source." });
      return;
    }
    set({ createError: null });

    const res = await fetch("/api/capsules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: d.title.trim() || "Untitled trip",
        description: d.description.trim() || null,
        timeline: d.timeline,
        gpx: d.gpx,
        media: d.media,
        date_from: d.dateFrom || null,
        date_to: d.dateTo || null,
        enrich: d.enrich,
        derivatives: d.derivatives,
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      set({ createError: body.detail ?? "Could not start the import." });
      return;
    }

    const { jobId, capsuleId } = await res.json();
    set({
      jobId,
      newCapsuleId: capsuleId,
      jobEvents: [],
      jobStatus: "running",
      jobError: null,
      screen: "progress",
    });

    // Server-sent events: a seven-minute spinner tells the user nothing.
    //
    // The stream is for liveness only. It is NEVER the source of truth about whether the
    // job succeeded -- a dropped connection says nothing about a thread that is still
    // working, and treating it as failure is what made a healthy import look broken.
    // Authority lives in GET /api/jobs/{id}, which is polled to the end regardless.
    const stream = new EventSource(`/api/jobs/${jobId}/stream`);
    stream.onmessage = (e) => {
      const ev = JSON.parse(e.data) as JobEvent;
      set({ jobEvents: [...get().jobEvents, ev] });
    };
    stream.addEventListener("end", () => stream.close());
    stream.onerror = () => stream.close();

    void pollUntilDone(jobId, set, get);
  },

  async loadReport() {
    try {
      const report = (await fetch("/api/report").then((r) => r.json())) as IngestReport;
      set({ report });
    } catch {
      set({ report: null });
    }
  },
}));

/**
 * Follow a job to completion, whatever the stream does.
 *
 * Polls slowly -- this runs for minutes, and the SSE stream is already carrying the
 * detail. Only a job the server itself reports as failed is a failure.
 */
async function pollUntilDone(
  jobId: string,
  set: (partial: Partial<State>) => void,
  get: () => State,
): Promise<void> {
  const started = Date.now();
  const LIMIT_MS = 60 * 60 * 1000; // an hour is longer than any real import
  let missed = 0;

  while (Date.now() - started < LIMIT_MS) {
    await new Promise((r) => setTimeout(r, 2000));
    let job: { status: string; error: string | null; capsuleId: string | null; events: JobEvent[] };
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error(String(res.status));
      job = await res.json();
      missed = 0;
    } catch {
      // The backend may be briefly busy. Only give up once it is properly gone.
      if (++missed >= 10) {
        set({ jobStatus: "failed", jobError: "Lost contact with the backend." });
        return;
      }
      continue;
    }

    // The stream may have dropped; the poll response still carries every event.
    if (job.events.length > get().jobEvents.length) set({ jobEvents: job.events });
    if (job.status === "running") continue;

    if (job.status === "done" && job.capsuleId) {
      await fetch(`/api/capsules/${encodeURIComponent(job.capsuleId)}/open`, {
        method: "POST",
      });
      set({ jobStatus: "done", jobError: null });
      await get().loadReport();
      set({ screen: "report" });
    } else {
      set({
        jobStatus: "failed",
        jobError: job.error ?? "The import stopped without saying why.",
      });
    }
    return;
  }
  set({ jobStatus: "failed", jobError: "The import took longer than an hour." });
}
