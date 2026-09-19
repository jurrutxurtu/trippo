"""Environment and secrets.

Keys are read from the process environment, falling back to a `.env` file beside the
backend. Nothing is ever written to a capsule: an exported trip must not carry someone's
API quota with it (ADR-0001).
"""

from __future__ import annotations

import os
from pathlib import Path

#: Searched in order; the first file found wins. Values already in the environment are
#: never overwritten, so `MAPTILER_KEY=... just serve` still beats the file.
CANDIDATES = (
    Path.cwd() / ".env",
    Path(__file__).resolve().parents[2] / ".env",  # backend/.env
    Path.home() / ".trippo" / ".env",
)

KNOWN_KEYS = ("MAPTILER_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "GOOGLE_PLACES_API_KEY")


def load_env(verbose: bool = False) -> dict[str, bool]:
    """Populate the environment from the first `.env` found. Returns which keys are set."""
    for path in CANDIDATES:
        if path.is_file():
            _read_into_environ(path)
            if verbose:
                print(f"[env]      read {path}")
            break

    present = {k: bool(os.environ.get(k)) for k in KNOWN_KEYS}
    return present


def _read_into_environ(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        # An explicit environment variable always beats the file.
        if key and value and key not in os.environ:
            os.environ[key] = value


def describe(present: dict[str, bool]) -> str:
    bits = []
    for key, ok in present.items():
        label = key.replace("_API_KEY", "").replace("_KEY", "").lower()
        bits.append(f"{label} {'on' if ok else 'off'}")
    return " \u00b7 ".join(bits)
