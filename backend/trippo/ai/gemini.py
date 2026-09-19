"""Gemini provider. Optional -- the app is fully usable without it.

Structured output only: a response schema is passed on every call, so the model returns
JSON rather than prose that has to be parsed. Never raises; a failure is a degradation and
the caller falls back to the deterministic result.
"""

from __future__ import annotations

import json
import os
from typing import Any

from trippo.ports.llm import LlmResponse

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        self._key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model
        self._client: Any = None
        self.failures = 0
        #: The last thing that went wrong. Surfaced to the user, because a blocked key
        #: and an empty answer are very different problems that look identical.
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self._key)

    def _ensure(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError:
            return None
        self._client = genai.Client(api_key=self._key)
        return self._client

    def complete(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> LlmResponse:
        if not self.available:
            return LlmResponse(ok=False, error="GEMINI_API_KEY is not set.")
        client = self._ensure()
        if client is None:
            return LlmResponse(
                ok=False, error="google-genai is not installed (pip install '.[ai]')."
            )
        try:
            result = client.models.generate_content(
                model=self._model,
                contents=f"{system}\n\n{prompt}",
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "temperature": 0.4,
                },
            )
            text = (result.text or "").strip()
            if not text:
                self.failures += 1
                self.last_error = "The model returned nothing."
                return LlmResponse(ok=False, error=self.last_error)
            self.last_error = None
            return LlmResponse(data=json.loads(text))
        except Exception as exc:
            self.failures += 1
            self.last_error = _readable(exc)
            return LlmResponse(ok=False, error=self.last_error)


def _readable(exc: Exception) -> str:
    """Turn a provider error into something a person can act on."""
    text = str(exc)
    if "API_KEY_SERVICE_BLOCKED" in text or "are blocked" in text:
        return (
            "Google is blocking this key for the Generative Language API. In Google Cloud "
            "Console, open the key under APIs & Services -> Credentials and either remove "
            "the API restriction or add 'Generative Language API' to it. Check the API is "
            "enabled on the project too."
        )
    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return "GEMINI_API_KEY is not a valid key."
    if "quota" in text.lower() or "RESOURCE_EXHAUSTED" in text:
        return "The model's quota is exhausted. Try again later."
    if "PERMISSION_DENIED" in text:
        return "Permission denied by Google for this key."
    return text[:200]


def provider_from_env() -> Any:
    """Gemini when a key exists, otherwise the null provider."""
    from trippo.ports.llm import NullProvider

    if os.environ.get("GEMINI_API_KEY"):
        return GeminiProvider()
    return NullProvider()
