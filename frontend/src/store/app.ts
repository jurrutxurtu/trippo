import { create } from "zustand";
import type { CapsuleSummary, IngestReport, JobEvent } from "@/lib/types";

/**
 * Screen-level navigation and trip creation.
 *
 * Kept separate from the trip store: that one is about a single open capsule, this one is
 * about getting to it. Mixing them would mean the explorer re-renders every time a file
 * picker returns.
 */
export type Screen = "library" | "create" | "progress" | "report" | "trip";

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
    const stream = new EventSource(`/api/jobs/${jobId}/stream`);
    stream.onmessage = (e) => {
      const ev = JSON.parse(e.data) as JobEvent;
      set({ jobEvents: [...get().jobEvents, ev] });
    };
    stream.addEventListener("end", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      stream.close();
      set({
        jobStatus: data.status === "done" ? "done" : "failed",
        jobError: data.error ?? null,
      });
      if (data.status === "done" && data.capsuleId) {
        void (async () => {
          await fetch(`/api/capsules/${encodeURIComponent(data.capsuleId)}/open`, {
            method: "POST",
          });
          await get().loadReport();
          set({ screen: "report" });
        })();
      }
    });
    stream.onerror = () => {
      stream.close();
      // The job may have finished between the last event and the stream closing.
      void fetch(`/api/jobs/${jobId}`)
        .then((r) => r.json())
        .then((j) =>
          set({
            jobStatus: j.status === "done" ? "done" : "failed",
            jobError: j.error ?? null,
          }),
        )
        .catch(() => set({ jobStatus: "failed", jobError: "Lost contact with the server." }));
    };
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
