"""Is a language model actually usable?

Configuring an LLM has several independent ways to fail -- no key, a key the service
refuses, a project with no credits, a retired model -- and they all look the same in a UI
that simply shows nothing. This says which one it is, for every provider in the chain.
"""

from __future__ import annotations

import os

import httpx

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_BASE = "https://api.groq.com/openai/v1"

PROBE = {"contents": [{"parts": [{"text": "Reply with the single word: ok"}]}]}


def check() -> tuple[bool, list[str]]:
    """Return (any provider usable, lines to print)."""
    from trippo.ai.provider import DEFAULT_ORDER

    order = [
        n.strip()
        for n in (os.environ.get("LLM_ORDER") or ",".join(DEFAULT_ORDER)).split(",")
        if n.strip()
    ]

    out: list[str] = [f"order    : {' \u2192 '.join(order)}", ""]
    usable = False

    for name in order:
        ok, lines = _check_one(name)
        usable = usable or ok
        out.extend(lines)
        out.append("")

    if not usable:
        out += [
            "No provider can answer, so AI suggestions are hidden.",
            "Everything deterministic still works -- including 'hide passing-through",
            "stops', which needs no model at all.",
        ]
    return usable, out


def _check_one(name: str) -> tuple[bool, list[str]]:
    if name == "gemini":
        return _gemini()
    if name == "groq":
        return _groq()
    return False, [f"{name:<8} : unknown provider"]


# --------------------------------------------------------------------------- gemini


def _gemini() -> tuple[bool, list[str]]:
    from trippo.ai.gemini import DEFAULT_MODEL

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return False, ["gemini   : no key (GEMINI_API_KEY)"]

    out = [f"gemini   : key {key[:6]}\u2026 ({len(key)} chars)"]
    try:
        r = httpx.get(f"{GEMINI_BASE}/models?key={key}", timeout=25)
    except httpx.HTTPError as exc:
        return False, [*out, f"           cannot reach Google ({exc})"]

    if r.status_code != 200:
        err = r.json().get("error", {}) if r.text else {}
        reason = (err.get("details") or [{}])[0].get("reason", "")
        out.append(f"           listing {r.status_code} {reason}")
        if reason == "API_KEY_SERVICE_BLOCKED":
            out += [
                "           The key is restricted and this API is not allowed.",
                "           Cloud Console -> Credentials -> the key -> API restrictions",
            ]
        elif reason == "API_KEY_INVALID":
            out.append("           Not a valid key. aistudio.google.com/apikey")
        return False, out

    model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    try:
        g = httpx.post(
            f"{GEMINI_BASE}/models/{model}:generateContent?key={key}",
            json=PROBE,
            timeout=45,
        )
    except httpx.HTTPError as exc:
        return False, [*out, f"           generate failed ({exc})"]

    if g.status_code == 200:
        return True, [*out, f"           {model} works"]

    message = ((g.json().get("error") or {}).get("message") or "")[:160]
    out.append(f"           generate {g.status_code}")
    if "credits are depleted" in message or g.status_code == 429:
        out += [
            "           No API credits on this project.",
            "           A Google AI Pro subscription covers the Gemini APP, not the",
            "           API -- they are billed separately.",
        ]
    elif "no longer available" in message:
        out.append(
            f"           Google retired that model; unset GEMINI_MODEL ({DEFAULT_MODEL})."
        )
    else:
        out.append(f"           {message}")
    return False, out


# --------------------------------------------------------------------------- groq


def _groq() -> tuple[bool, list[str]]:
    from trippo.ai.groq import DEFAULT_MODEL

    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return False, [
            "groq     : no key (GROQ_API_KEY)",
            "           Free, no card needed: console.groq.com/keys",
        ]

    out = [f"groq     : key {key[:8]}\u2026 ({len(key)} chars)"]
    model = os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
    try:
        r = httpx.post(
            f"{GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with the word ok"}],
                "max_tokens": 8,
            },
            timeout=45,
        )
    except httpx.HTTPError as exc:
        return False, [*out, f"           cannot reach Groq ({exc})"]

    if r.status_code == 200:
        return True, [*out, f"           {model} works"]

    try:
        message = ((r.json().get("error") or {}).get("message") or "")[:160]
    except ValueError:
        message = r.text[:160]
    out.append(f"           {r.status_code} {message}")
    if r.status_code == 401:
        out.append("           Not a valid key. console.groq.com/keys")
    elif r.status_code == 429:
        out.append("           Free-tier rate limit; it resets within a minute.")
    elif r.status_code == 404:
        out.append("           Set GROQ_MODEL from console.groq.com/docs/models")
    return False, out
