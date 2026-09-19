"""Choosing a language model, and falling back when one will not serve.

There is no single provider that is always available: Gemini needs credits on a Cloud
project, Groq's free tier rate-limits, and a key can be restricted or revoked without
warning. Rather than making the user pick, Trippo tries them in order and uses whichever
answers.

Order is deliberate and configurable through `LLM_ORDER`:

  gemini  first when it has credits -- strongest structured output
  groq    a genuinely free tier, so it is the one that usually answers

A provider that fails is demoted for the rest of the process. One dead provider must not
tax every subsequent request.
"""

from __future__ import annotations

import os
from typing import Any

from trippo.ports.llm import LlmResponse, NullProvider

DEFAULT_ORDER = ("gemini", "groq")


def _build(name: str) -> Any | None:
    if name == "gemini" and os.environ.get("GEMINI_API_KEY"):
        from trippo.ai.gemini import GeminiProvider

        return GeminiProvider()
    if name == "groq" and os.environ.get("GROQ_API_KEY"):
        from trippo.ai.groq import GroqProvider

        return GroqProvider()
    return None


class FallbackProvider:
    """Tries each provider in turn and reports which one answered."""

    def __init__(self, providers: list[Any]) -> None:
        self._providers = providers
        self._demoted: list[str] = []
        self.last_error: str | None = None
        self.used: str | None = None
        self.failures = 0

    @property
    def name(self) -> str:
        return self.used or "+".join(p.name for p in self._providers) or "none"

    @property
    def available(self) -> bool:
        return any(p.available for p in self._providers)

    def _ordered(self) -> list[Any]:
        healthy = [p for p in self._providers if p.name not in self._demoted]
        return healthy + [p for p in self._providers if p.name in self._demoted]

    def complete(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> LlmResponse:
        errors: list[str] = []
        for provider in self._ordered():
            if not provider.available:
                continue
            response = provider.complete(system=system, prompt=prompt, schema=schema)
            if response.ok:
                self.used = provider.name
                self.last_error = None
                return response

            errors.append(f"{provider.name}: {response.error}")
            self.failures += 1
            # A provider that just refused will refuse again; stop leading with it.
            if provider.name not in self._demoted and len(self._providers) > 1:
                self._demoted.append(provider.name)

        self.last_error = " \u2014 ".join(errors) if errors else "No model is configured."
        return LlmResponse(ok=False, error=self.last_error)


def provider_from_env() -> Any:
    """The configured chain, or a null provider when nothing is set up."""
    order = [
        n.strip()
        for n in (os.environ.get("LLM_ORDER") or ",".join(DEFAULT_ORDER)).split(",")
        if n.strip()
    ]
    providers = [p for p in (_build(n) for n in order) if p is not None]
    if not providers:
        return NullProvider()
    if len(providers) == 1:
        return providers[0]
    return FallbackProvider(providers)
