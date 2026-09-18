"""LLM port. The app must be fully usable without one.

`NullProvider` is installed when no key is configured, and every AI affordance is then
hidden rather than greyed out (`docs/technical/ai-integration.md`).

Providers return structured data, never prose to be parsed. Output is validated against
the facts it was given before it reaches the user -- see `ai/validators.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class LlmResponse:
    data: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    error: str | None = None


@runtime_checkable
class Llm(Protocol):
    name: str
    available: bool

    def complete(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> LlmResponse:
        """Return structured output matching `schema`.

        Must never raise: a provider failure is a degradation, and the caller falls back
        to the deterministic result.
        """
        ...


class NullProvider:
    """No key configured. Every call reports unavailable; nothing breaks."""

    name = "none"
    available = False

    def complete(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> LlmResponse:
        return LlmResponse(ok=False, error="No language model is configured.")
