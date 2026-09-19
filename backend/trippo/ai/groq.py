"""Groq provider -- an OpenAI-compatible endpoint with a usable free tier.

Exists because the Gemini API is billed separately from a Google AI Pro subscription, and
a project without credits returns 429 for every model. A travel journal should not need a
prepayment to suggest a day title.

Structured output uses Groq's `json_schema` response format, which the hosted models
honour properly -- verified against `openai/gpt-oss-120b`, `openai/gpt-oss-20b` and
`qwen/qwen3.8-27b`. Falls back to `json_object` if a model rejects the schema.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from trippo.ports.llm import LlmResponse

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

#: Strongest model on the free tier at the time of writing. Override with GROQ_MODEL.
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self._model = model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
        self._client = client or httpx.Client(timeout=60.0)
        #: Set once a model rejects json_schema, so we stop paying for the round trip.
        self._schema_unsupported = False
        self.failures = 0
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self._key)

    def complete(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> LlmResponse:
        if not self.available:
            return LlmResponse(ok=False, error="GROQ_API_KEY is not set.")

        # The schema goes in the prompt as well as the response_format: smaller models
        # follow it far more reliably when they can read it.
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": f"{system}\nReply with JSON only."},
                {
                    "role": "user",
                    "content": f"{prompt}\n\nJSON schema:\n{json.dumps(schema)}",
                },
            ],
            "temperature": 0.4,
            "response_format": (
                {"type": "json_object"}
                if self._schema_unsupported
                else {
                    "type": "json_schema",
                    "json_schema": {"name": "response", "schema": schema},
                }
            ),
        }

        try:
            r = self._client.post(
                ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except (httpx.HTTPError, OSError) as exc:
            self.failures += 1
            self.last_error = f"Could not reach Groq ({exc})."
            return LlmResponse(ok=False, error=self.last_error)

        if r.status_code == 400 and not self._schema_unsupported:
            # This model does not do json_schema. Remember, and retry once in plain
            # JSON mode rather than losing the request.
            self._schema_unsupported = True
            return self.complete(system=system, prompt=prompt, schema=schema)

        if r.status_code != 200:
            self.failures += 1
            self.last_error = _readable(r)
            return LlmResponse(ok=False, error=self.last_error)

        try:
            text = r.json()["choices"][0]["message"]["content"].strip()
            self.last_error = None
            return LlmResponse(data=json.loads(text))
        except (KeyError, IndexError, ValueError) as exc:
            self.failures += 1
            self.last_error = f"Groq returned something unreadable ({exc})."
            return LlmResponse(ok=False, error=self.last_error)


def _readable(r: httpx.Response) -> str:
    """Turn a Groq error into something a person can act on."""
    try:
        message = (r.json().get("error") or {}).get("message", "")
    except ValueError:
        message = r.text[:200]

    if r.status_code == 401:
        return "GROQ_API_KEY is not valid. Get one free at console.groq.com/keys"
    if r.status_code == 429:
        return (
            "Groq's free-tier rate limit is reached. It resets within a minute; "
            "try again shortly."
        )
    if r.status_code == 404 or "decommissioned" in message or "does not exist" in message:
        return (
            f"Groq no longer serves {DEFAULT_MODEL!r}. Set GROQ_MODEL to a current one "
            "from console.groq.com/docs/models"
        )
    return message[:200] or f"Groq returned {r.status_code}."
