import { useState, useRef } from "react";
import { useApp } from "@/store/app";
import { preprocessAndUpload, PreprocessProgress } from "@/lib/preprocessor";

/**
 * Creating a trip.
 *
 * Supports both:
 * 1. Web / Remote mode: selects photos, GPX and Timeline directly in the browser,
 *    extracts EXIF and generates WebP thumbnails locally, and uploads a lightweight bundle.
 * 2. Local-first mode: reads local file paths directly via backend file picker or manual paste.
 */
export function CreateTrip() {
  const {
    draft,
    setDraft,
    pick,
    setPath,
    picking,
    proposing,
    startBuild,
    watchJob,
    createError,
    go,
  } = useApp();

  // Browser-selected files
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [gpxFiles, setGpxFiles] = useState<File[]>([]);
  const [timelineFile, setTimelineFile] = useState<File | null>(null);

  // Preprocessing state
  const [preprogress, setPreprogress] = useState<PreprocessProgress | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const hasBrowserSource = mediaFiles.length > 0 || gpxFiles.length > 0 || timelineFile !== null;
  const hasLocalSource = !!(draft.timeline || draft.gpx || draft.media.length);
  const hasSource = hasBrowserSource || hasLocalSource;

  // Auto-detect dates from selected media files
  const handleSelectMedia = (files: File[]) => {
    setMediaFiles(files);
    setLocalError(null);

    // Try guessing date range from file dates or names
    if (!draft.dateFrom || !draft.dateTo) {
      const dates: Date[] = [];
      const sample = files.slice(0, 150);
      for (const f of sample) {
        if (f.lastModified) {
          dates.push(new Date(f.lastModified));
        }
      }
      if (dates.length > 0) {
        dates.sort((a, b) => a.getTime() - b.getTime());
        const first = dates[0];
        const last = dates[dates.length - 1];
        if (first && last) {
          const start = first.toISOString().split("T")[0];
          const end = last.toISOString().split("T")[0];
          setDraft({ dateFrom: start, dateTo: end });
        }
      }
    }
  };

  const handleBuild = async () => {
    setLocalError(null);
    if (!hasSource) {
      setLocalError("Add at least one source (photos, GPX tracks, or timeline).");
      return;
    }

    // If files were selected via browser file picker, run client preprocessor
    if (hasBrowserSource) {
      try {
        const { jobId, capsuleId } = await preprocessAndUpload({
          title: draft.title.trim() || "Untitled trip",
          description: draft.description.trim() || null,
          dateFrom: draft.dateFrom || null,
          dateTo: draft.dateTo || null,
          enrich: draft.enrich,
          timelineFile,
          gpxFiles,
          mediaFiles,
          onProgress: (p) => setPreprogress(p),
        });

        watchJob(jobId, capsuleId);
      } catch (err: unknown) {
        setPreprogress(null);
        setLocalError(err instanceof Error ? err.message : "Failed to process and upload trip.");
      }
    } else {
      // Fallback to local desktop backend build
      await startBuild();
    }
  };

  return (
    <div className="min-h-full bg-zinc-50">
      <div className="mx-auto max-w-[1100px] px-10 py-10">
        <header className="mb-8 flex items-baseline justify-between">
          <div>
            <button
              onClick={() => go("library")}
              className="text-[11px] font-medium text-zinc-400 hover:text-zinc-700"
            >
              &larr; All trips
            </button>
            <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-zinc-900">
              New trip
            </h1>
            <p className="mt-1 text-sm text-zinc-500">
              Add whatever you have. Every source is optional.
            </p>
          </div>
        </header>

        <div className="grid grid-cols-12 gap-6">
          <section className="col-span-5 space-y-4">
            <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-zinc-900">Details</h2>

              <label className="mt-5 block">
                <span className="text-xs font-medium text-zinc-600">Title</span>
                <input
                  value={draft.title}
                  onChange={(e) => setDraft({ title: e.target.value })}
                  placeholder="Ireland 2023"
                  className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                />
              </label>

              <label className="mt-4 block">
                <span className="text-xs font-medium text-zinc-600">
                  Description <span className="font-normal text-zinc-400">&middot; optional</span>
                </span>
                <textarea
                  rows={3}
                  value={draft.description}
                  onChange={(e) => setDraft({ description: e.target.value })}
                  placeholder="Three weeks around the island in the van&hellip;"
                  className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                />
              </label>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs font-medium text-zinc-600">From</span>
                  <input
                    type="date"
                    value={draft.dateFrom}
                    onChange={(e) => setDraft({ dateFrom: e.target.value })}
                    className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-zinc-600">To</span>
                  <input
                    type="date"
                    value={draft.dateTo}
                    onChange={(e) => setDraft({ dateTo: e.target.value })}
                    className="mt-1.5 block w-full rounded-lg border-zinc-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  />
                </label>
              </div>
              <p className="mt-2 text-xs text-zinc-500">
                {proposing
                  ? "Reading your photo timestamps\u2026"
                  : draft.dateFrom
                    ? "Proposed from your photographs. Edit if the trip started earlier."
                    : "Leave blank to use everything in the sources."}
              </p>
            </div>

            <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-zinc-900">What to do on import</h2>
              <Toggle
                checked={draft.enrich}
                onChange={(v) => setDraft({ enrich: v })}
                title="Look up place names"
                detail="Sends coordinates to OpenStreetMap. Without this, stops are labelled by latitude. Takes a few minutes the first time."
              />
              <Toggle
                checked={draft.derivatives}
                onChange={(v) => setDraft({ derivatives: v })}
                title="Make thumbnails"
                detail="Needed to see photographs in the app. Original files are never modified."
              />
              <p className="mt-4 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-500">
                Original raw files are never uploaded; only lightweight metadata and thumbnails are sent to the cloud.
              </p>
            </div>
          </section>

          <section className="col-span-7 space-y-4">
            <SourceCard
              title="Photos and videos"
              hint="A folder. Sub-folders are included."
              value={
                mediaFiles.length > 0
                  ? `${mediaFiles.length} file(s) selected in browser`
                  : draft.media.join("  \u00b7  ")
              }
              fileCount={mediaFiles.length}
              isFolder
              onSelectFiles={handleSelectMedia}
              onServerPick={() => void pick("media")}
              onPaste={(v) => setPath("media", v)}
              onClear={() => {
                setMediaFiles([]);
                setDraft({ media: [] });
              }}
              picking={picking}
              multiple
            />

            <SourceCard
              title="GPS tracks"
              hint="One or more .gpx files from Garmin, Strava, Wikiloc&hellip;"
              value={
                gpxFiles.length > 0
                  ? `${gpxFiles.length} GPX track(s) selected in browser`
                  : draft.gpx ?? ""
              }
              fileCount={gpxFiles.length}
              accept=".gpx"
              onSelectFiles={(files) => setGpxFiles(files)}
              onServerPick={() => void pick("gpx")}
              onPaste={(v) => setPath("gpx", v)}
              onClear={() => {
                setGpxFiles([]);
                setDraft({ gpx: null });
              }}
              picking={picking}
            />

            <SourceCard
              title="Location history"
              hint="The Timeline JSON from a Google Takeout or on-device export."
              value={
                timelineFile
                  ? `${timelineFile.name} selected in browser`
                  : draft.timeline ?? ""
              }
              fileCount={timelineFile ? 1 : 0}
              file
              accept=".json"
              onSelectFiles={(files) => setTimelineFile(files[0] ?? null)}
              onServerPick={() => void pick("timeline")}
              onPaste={(v) => setPath("timeline", v)}
              onClear={() => {
                setTimelineFile(null);
                setDraft({ timeline: null });
              }}
              picking={picking}
            />

            {(localError || createError) && (
              <p className="rounded-lg bg-red-50 px-4 py-3 text-xs text-red-800 ring-1 ring-red-200">
                {localError || createError}
              </p>
            )}

            <div className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
              <p className="text-xs text-zinc-500">
                {hasBrowserSource
                  ? "Photos will be resized and optimized locally before uploading."
                  : "Nothing is copied or uploaded. Trippo reads your files where they are."}
              </p>
              <button
                disabled={!hasSource || preprogress !== null}
                onClick={() => void handleBuild()}
                className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 disabled:bg-zinc-300"
              >
                {preprogress !== null ? "Processing\u2026" : "Build the trip"}
              </button>
            </div>
          </section>
        </div>
      </div>

      {/* Preprocessing & Upload Progress Modal */}
      {preprogress && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-900">Preparing your trip</h3>
              <span className="text-xs font-mono font-medium text-indigo-600">
                {preprogress.total > 0
                  ? `${Math.min(100, Math.round((preprogress.current / preprogress.total) * 100))}%`
                  : ""}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
              <div
                className="h-full bg-indigo-600 transition-all duration-200"
                style={{
                  width: `${
                    preprogress.total > 0
                      ? Math.min(100, Math.round((preprogress.current / preprogress.total) * 100))
                      : 10
                  }%`,
                }}
              />
            </div>
            <p className="text-xs text-zinc-700 font-medium">{preprogress.message}</p>
            <p className="text-[11px] leading-relaxed text-zinc-400">
              Photos are processed locally in your browser. Original files stay on your machine.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  title,
  detail,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  detail: string;
}) {
  return (
    <label className="mt-4 flex items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
      />
      <span className="text-xs leading-relaxed text-zinc-600">
        <span className="font-medium text-zinc-900">{title}</span>
        <br />
        {detail}
      </span>
    </label>
  );
}

function SourceCard({
  title,
  hint,
  value,
  fileCount = 0,
  onSelectFiles,
  onServerPick,
  onPaste,
  onClear,
  picking,
  multiple,
  file,
  isFolder,
  accept,
}: {
  title: string;
  hint: string;
  value: string;
  fileCount?: number;
  onSelectFiles?: (files: File[]) => void;
  onServerPick?: () => void;
  onPaste: (v: string) => void;
  onClear: () => void;
  picking: boolean;
  multiple?: boolean;
  file?: boolean;
  isFolder?: boolean;
  accept?: string;
}) {
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onSelectFiles?.(Array.from(e.target.files));
    }
  };

  const handleClickChoose = () => {
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.click();
    } else if (onServerPick) {
      onServerPick();
    }
  };

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
      {/* Hidden file input for browser file selection */}
      <input
        ref={inputRef}
        type="file"
        multiple={multiple || isFolder}
        accept={accept}
        {...(isFolder ? ({ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>) : {})}
        onChange={handleFileChange}
        className="hidden"
      />

      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-500">
              optional
            </span>
            {(value || fileCount > 0) && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                chosen
              </span>
            )}
          </div>
          {value ? (
            <p className="mt-2 break-all font-mono text-[11px] text-zinc-700">{value}</p>
          ) : (
            <p className="mt-1.5 text-xs text-zinc-500">{hint}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={handleClickChoose}
            disabled={picking}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            {picking
              ? "Waiting\u2026"
              : value && !multiple
                ? "Change"
                : `Choose ${isFolder ? "folder" : file ? "file" : "files"}\u2026`}
          </button>
          {value && (
            <button
              onClick={onClear}
              className="text-[11px] text-zinc-400 hover:text-zinc-700"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Fallback for typing a path manually */}
      {typing ? (
        <div className="mt-3 flex gap-1.5">
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="C:\\Users\\you\\Pictures\\Ireland"
            className="min-w-0 flex-1 rounded-lg border-zinc-300 font-mono text-[11px] focus:border-indigo-500 focus:ring-indigo-500"
          />
          <button
            onClick={() => {
              onPaste(text);
              setText("");
              setTyping(false);
            }}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-[11px] font-medium text-white"
          >
            Use
          </button>
          <button
            onClick={() => setTyping(false)}
            className="px-2 text-[11px] text-zinc-500"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={() => setTyping(true)}
            className="text-[11px] text-zinc-400 hover:text-zinc-700"
          >
            or paste a local path
          </button>
          {onServerPick && (
            <button
              onClick={onServerPick}
              className="text-[11px] text-zinc-400 hover:text-zinc-700"
            >
              &middot; pick on desktop server
            </button>
          )}
        </div>
      )}
    </div>
  );
}
