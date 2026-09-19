"""Check whether the language model is actually usable.

Configuring an LLM has three independent ways to fail -- no key, a key the service
refuses, and a project with no credits -- and they produce very similar symptoms in a UI
that simply shows nothing. This says which one it is.
"""

from __future__ import annotations

import os

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


def check() -> tuple[bool, list[str]]:
    """Return (usable, lines to print)."""
    key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "")
    out: list[str] = []

    if not key:
        return False, [
            "GEMINI_API_KEY is not set.",
            "  AI suggestions are hidden. Everything else works.",
            "  Get a key at https://aistudio.google.com/apikey and put it in backend/.env",
        ]

    out.append(f"key      : {key[:6]}… ({len(key)} chars)")

    # 1 -- can we list models? Proves the key exists and the API is not blocked.
    try:
        r = httpx.get(f"{BASE}/models?key={key}", timeout=25)
    except httpx.HTTPError as exc:
        return False, [*out, f"network  : cannot reach Google ({exc})"]

    if r.status_code != 200:
        err = r.json().get("error", {}) if r.text else {}
        reason = (err.get("details") or [{}])[0].get("reason", "")
        out.append(f"models   : {r.status_code} {reason}")
        if reason == "API_KEY_SERVICE_BLOCKED":
            out += [
                "",
                "  This key is restricted and the Generative Language API is not allowed.",
                "  Google Cloud Console -> APIs & Services -> Credentials -> your key",
                "  -> API restrictions: remove the restriction, or add",
                "     'Generative Language API'. Check it is enabled on the project too.",
            ]
        elif reason == "API_KEY_INVALID":
            out.append("  The key is not valid. Create a new one at aistudio.google.com/apikey")
        else:
            out.append(f"  {(err.get('message') or '')[:200]}")
        return False, out

    names = [m["name"].split("/")[-1] for m in r.json().get("models", [])]
    out.append(f"models   : {len(names)} available")

    from trippo.ai.gemini import DEFAULT_MODEL

    wanted = model or DEFAULT_MODEL
    if wanted not in names and not wanted.endswith("-latest"):
        flash = [n for n in names if "flash" in n and "preview" not in n][:4]
        out.append(f"model    : {wanted!r} is NOT in the list. Try one of: {', '.join(flash)}")
    else:
        out.append(f"model    : {wanted}")

    # 2 -- can we actually generate? Proves the project has credits.
    try:
        g = httpx.post(
            f"{BASE}/models/{wanted}:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": "Reply with the single word: ok"}]}]},
            timeout=45,
        )
    except httpx.HTTPError as exc:
        return False, [*out, f"generate : failed ({exc})"]

    if g.status_code == 200:
        out.append("generate : works")
        return True, out

    err = g.json().get("error", {}) if g.text else {}
    message = (err.get("message") or "")[:200]
    out.append(f"generate : {g.status_code}")
    if "credits are depleted" in message or g.status_code == 429:
        out += [
            "",
            "  The key is fine; the project has no API credits.",
            "  A Google AI Pro subscription covers the Gemini APP, not the API --",
            "  they are billed separately. Either:",
            "    * add billing or credits at https://aistudio.google.com/",
            "    * or create a key on a project that still has the free tier",
            "",
            "  Trippo stays fully usable meanwhile. Only the four model-driven",
            "  suggestions are hidden; everything deterministic still runs.",
        ]
    elif "no longer available" in message:
        out.append(f"  Google retired that model. Unset GEMINI_MODEL to use {DEFAULT_MODEL}.")
    else:
        out.append(f"  {message}")
    return False, out
