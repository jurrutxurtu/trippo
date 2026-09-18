import { useTrip } from "@/store/trip";
import { useApp } from "@/store/app";

/**
 * Edit-mode chrome: toggle, undo/redo, save, and the review count.
 *
 * Reading and editing are one screen rather than two. A trip is mostly read and
 * occasionally corrected, and making the correction a separate destination means the
 * mistakes get noticed in one place and fixed in another.
 */
export function Toolbar() {
  const {
    editing,
    setEditing,
    canUndo,
    canRedo,
    undo,
    redo,
    dirty,
    save,
    busy,
    review,
  } = useTrip();

  const blocking = review?.filter((f) => f.severity === "blocking").length ?? 0;

  return (
    <div className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-5 py-2">
      <div className="flex items-center gap-2">
        <button
          onClick={() => {
            if (dirty && !confirm("You have unsaved changes. Leave anyway?")) return;
            useApp.getState().go("library");
            void useApp.getState().loadLibrary();
          }}
          className="rounded-lg px-2 py-1.5 text-xs font-medium text-zinc-500 hover:bg-zinc-100"
        >
          &larr; Trips
        </button>
        <button
          onClick={() => setEditing(!editing)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            editing
              ? "bg-indigo-600 text-white hover:bg-indigo-500"
              : "border border-zinc-300 text-zinc-700 hover:bg-zinc-50"
          }`}
        >
          {editing ? "Done editing" : "Edit"}
        </button>
        {blocking > 0 && (
          <span className="flex items-center gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400" />
            {blocking} to resolve
          </span>
        )}
      </div>

      <div className="flex items-center gap-1">
        {editing && (
          <>
            <button
              disabled={!canUndo || busy}
              onClick={() => void undo()}
              className="rounded-lg px-2 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 disabled:opacity-30"
              title="Undo (Ctrl+Z)"
            >
              Undo
            </button>
            <button
              disabled={!canRedo || busy}
              onClick={() => void redo()}
              className="rounded-lg px-2 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 disabled:opacity-30"
              title="Redo (Ctrl+Shift+Z)"
            >
              Redo
            </button>
          </>
        )}
        <button
          disabled={!dirty || busy}
          onClick={() => void save()}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            dirty
              ? "bg-zinc-900 text-white hover:bg-zinc-700"
              : "text-zinc-400"
          }`}
        >
          {dirty ? "Save" : "Saved"}
        </button>
      </div>
    </div>
  );
}

/** A rejected operation is shown, not swallowed -- the server refused for a reason. */
export function OpError() {
  const { opError, dismissOpError } = useTrip();
  if (!opError) return null;
  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-zinc-900 px-4 py-2.5 text-xs text-white shadow-lg">
      {opError}
      <button
        onClick={dismissOpError}
        className="ml-3 text-zinc-400 hover:text-white"
      >
        dismiss
      </button>
    </div>
  );
}
