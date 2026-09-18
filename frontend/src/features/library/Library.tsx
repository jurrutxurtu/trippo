import { useEffect } from "react";
import { useApp } from "@/store/app";
import { formatDate } from "@/lib/format";

/** The library: every trip in the workspace. The capsules *are* the index. */
export function Library() {
  const { capsules, workspace, loadingLibrary, loadLibrary, openCapsule, deleteCapsule, go, resetDraft } =
    useApp();

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  return (
    <div className="min-h-full bg-zinc-50">
      <div className="mx-auto max-w-5xl px-10 py-12">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Trips</h1>
            <p className="mt-1 font-mono text-[11px] text-zinc-400">{workspace}</p>
          </div>
          <button
            onClick={() => {
              resetDraft();
              go("create");
            }}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500"
          >
            New trip
          </button>
        </header>

        {loadingLibrary ? (
          <p className="mt-16 text-center text-sm text-zinc-400">Looking&hellip;</p>
        ) : capsules.length === 0 ? (
          <div className="mt-10 rounded-xl border-2 border-dashed border-zinc-300 px-8 py-16 text-center">
            <p className="text-sm font-medium text-zinc-900">No trips yet</p>
            <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-zinc-500">
              Point Trippo at a Google Timeline export, a folder of GPX tracks, or just a
              folder of photographs. Any one of them is enough.
            </p>
            <button
              onClick={() => {
                resetDraft();
                go("create");
              }}
              className="mt-5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              Create your first trip
            </button>
          </div>
        ) : (
          <ul className="mt-8 grid grid-cols-2 gap-4">
            {capsules.map((c) => (
              <li
                key={c.id}
                className="group overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm hover:border-zinc-300"
              >
                <button
                  onClick={() => void openCapsule(c.id)}
                  className="block w-full text-left"
                >
                  <div className="h-36 bg-zinc-100">
                    {c.cover && (
                      <img
                        src={`/${c.cover}`}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    )}
                  </div>
                  <div className="px-4 py-3">
                    <h2 className="truncate text-sm font-semibold text-zinc-900">
                      {c.title}
                    </h2>
                    <p className="mt-0.5 text-[11px] text-zinc-500">
                      {c.start && c.end
                        ? `${formatDate(c.start)} \u2013 ${formatDate(c.end)}`
                        : "No dates"}
                    </p>
                    <p className="tnum mt-2 flex items-center gap-3 text-[11px] text-zinc-400">
                      <span>{c.dayCount} days</span>
                      <span>{c.photoCount.toLocaleString()} photos</span>
                      {c.unaccountedCount > 0 && (
                        <span className="text-amber-600">
                          {c.unaccountedCount} unaccounted
                        </span>
                      )}
                    </p>
                  </div>
                </button>
                <div className="flex justify-end border-t border-zinc-100 px-3 py-1.5 opacity-0 transition group-hover:opacity-100">
                  <button
                    onClick={() => {
                      if (
                        confirm(
                          `Delete "${c.title}"?\n\nOnly the capsule is removed. Your original photographs are untouched.`,
                        )
                      )
                        void deleteCapsule(c.id);
                    }}
                    className="text-[11px] text-zinc-400 hover:text-red-600"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
