"""Provider selection and the Groq client.

No real network: an `httpx.MockTransport` stands in for the service, so these tests assert
the things that actually bite -- that a dead provider is skipped rather than fatal, that a
failure is reported in words a person can act on, and that nothing ever raises.
"""

from __future__ import annotations

import json

import httpx
import pytest

from trippo.ai.groq import GroqProvider
from trippo.ai.provider import FallbackProvider, provider_from_env
from trippo.ports.llm import LlmResponse, NullProvider

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


# --------------------------------------------------------------------------- groq


def test_groq_parses_a_structured_reply():
    p = GroqProvider(api_key="k", client=_client(lambda r: _ok({"x": "hello"})))
    assert p.complete(system="s", prompt="p", schema=SCHEMA).data == {"x": "hello"}


def test_groq_asks_for_a_json_schema():
    """Free-tier models follow a schema far better when it is declared, not just described."""
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return _ok({"x": "y"})

    GroqProvider(api_key="k", client=_client(handler)).complete(
        system="s", prompt="p", schema=SCHEMA
    )
    assert seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["schema"] == SCHEMA


def test_groq_retries_in_plain_json_when_a_model_rejects_the_schema():
    modes: list[str] = []

    def handler(request):
        mode = json.loads(request.content)["response_format"]["type"]
        modes.append(mode)
        if mode == "json_schema":
            return httpx.Response(400, json={"error": {"message": "unsupported"}})
        return _ok({"x": "y"})

    p = GroqProvider(api_key="k", client=_client(handler))
    assert p.complete(system="s", prompt="p", schema=SCHEMA).ok
    assert modes == ["json_schema", "json_object"]

    # And it remembers, rather than paying for the rejection on every later call.
    p.complete(system="s", prompt="p", schema=SCHEMA)
    assert modes == ["json_schema", "json_object", "json_object"]


def test_groq_without_a_key_is_unavailable_not_broken():
    p = GroqProvider(api_key="")
    assert not p.available
    assert p.complete(system="s", prompt="p", schema=SCHEMA).ok is False


@pytest.mark.parametrize(
    ("status", "expect"),
    [
        (401, "not valid"),
        (429, "rate limit"),
        (404, "GROQ_MODEL"),
    ],
)
def test_groq_failures_are_explained_in_words(status, expect):
    p = GroqProvider(
        api_key="k",
        client=_client(
            lambda r: httpx.Response(status, json={"error": {"message": "nope"}})
        ),
    )
    response = p.complete(system="s", prompt="p", schema=SCHEMA)
    assert not response.ok
    assert expect in (response.error or "")
    assert p.last_error == response.error


def test_groq_survives_a_network_failure():
    def boom(request):
        raise httpx.ConnectError("no route to host")

    p = GroqProvider(api_key="k", client=_client(boom))
    assert p.complete(system="s", prompt="p", schema=SCHEMA).ok is False


def test_groq_survives_a_reply_that_is_not_json():
    p = GroqProvider(
        api_key="k",
        client=_client(
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": "sorry, no"}}]}
            )
        ),
    )
    assert p.complete(system="s", prompt="p", schema=SCHEMA).ok is False


# ------------------------------------------------------------------------ fallback


class Stub:
    def __init__(self, name: str, ok: bool, available: bool = True) -> None:
        self.name = name
        self.available = available
        self._ok = ok
        self.calls = 0
        self.last_error = None

    def complete(self, **_kw) -> LlmResponse:
        self.calls += 1
        if self._ok:
            return LlmResponse(data={"x": self.name})
        return LlmResponse(ok=False, error=f"{self.name} is out of credits")


def test_the_chain_falls_through_to_the_one_that_answers():
    dead, alive = Stub("gemini", ok=False), Stub("groq", ok=True)
    chain = FallbackProvider([dead, alive])
    assert chain.complete(system="s", prompt="p", schema=SCHEMA).data == {"x": "groq"}
    assert chain.used == "groq"


def test_a_failed_provider_is_demoted_not_retried_first():
    """One dead provider must not tax every subsequent request."""
    dead, alive = Stub("gemini", ok=False), Stub("groq", ok=True)
    chain = FallbackProvider([dead, alive])
    for _ in range(4):
        chain.complete(system="s", prompt="p", schema=SCHEMA)
    assert dead.calls == 1, "the dead provider should be tried once, then demoted"
    assert alive.calls == 4


def test_the_chain_reports_every_reason_when_all_fail():
    chain = FallbackProvider([Stub("gemini", ok=False), Stub("groq", ok=False)])
    response = chain.complete(system="s", prompt="p", schema=SCHEMA)
    assert not response.ok
    assert "gemini" in (response.error or "") and "groq" in (response.error or "")


def test_an_unconfigured_provider_is_skipped():
    absent, alive = Stub("gemini", ok=True, available=False), Stub("groq", ok=True)
    chain = FallbackProvider([absent, alive])
    chain.complete(system="s", prompt="p", schema=SCHEMA)
    assert absent.calls == 0


def test_the_chain_is_unavailable_only_when_nothing_is_configured():
    assert not FallbackProvider([Stub("a", ok=True, available=False)]).available
    assert FallbackProvider([Stub("a", ok=True)]).available


# --------------------------------------------------------------------- selection


def test_no_keys_means_the_null_provider(monkeypatch):
    """The app must be completely usable with nothing configured."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert isinstance(provider_from_env(), NullProvider)


def test_one_key_means_that_provider_alone(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert provider_from_env().name == "groq"


def test_two_keys_are_chained_in_the_configured_order(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a")
    monkeypatch.setenv("GROQ_API_KEY", "b")
    monkeypatch.setenv("LLM_ORDER", "groq,gemini")
    chain = provider_from_env()
    assert isinstance(chain, FallbackProvider)
    assert [p.name for p in chain._providers] == ["groq", "gemini"]
