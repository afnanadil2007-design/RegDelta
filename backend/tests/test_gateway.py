"""LLM gateway tests — provider translation, parsing, and error mapping.

Every provider call is mocked at the client boundary, so this suite never
touches the network and needs no API key. It covers both wired providers
(``anthropic`` and ``groq``) and the failure taxonomy the API surfaces.
"""

from __future__ import annotations

import types

import httpx
import openai
import pytest

from app.ai.extraction.schemas import JudgedImpact, json_schema_for
from app.ai.gateway import (
    GatewayError,
    LLMGateway,
    _openai_strict_schema,
)
from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base = {
        "_env_file": None,
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "gsk-test",
        "LLM_MODEL": "openai/gpt-oss-20b",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# --- strict schema adapter ----------------------------------------------


def test_strict_schema_requires_all_properties_and_bans_extras() -> None:
    schema = json_schema_for(JudgedImpact)
    strict = _openai_strict_schema(schema)

    assert strict["additionalProperties"] is False
    # OpenAI strict mode: every property must be listed in `required`.
    assert set(strict["required"]) == set(strict["properties"].keys())


def test_strict_schema_strips_unsupported_validation_keywords() -> None:
    schema = json_schema_for(JudgedImpact)
    strict = _openai_strict_schema(schema)
    # `rationale` carries min_length in Pydantic; strict mode rejects minLength,
    # so it must be gone (Pydantic still enforces it after parsing).
    assert "minLength" not in strict["properties"]["rationale"]
    assert "minimum" not in strict["properties"]["confidence"]


# --- groq success path ---------------------------------------------------


def _fake_openai_response(content: str, *, prompt_tokens=11, completion_tokens=7, refusal=None):
    message = types.SimpleNamespace(content=content, refusal=refusal)
    choice = types.SimpleNamespace(message=message, finish_reason="stop")
    usage = types.SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return types.SimpleNamespace(choices=[choice], usage=usage)


class _FakeCompletions:
    def __init__(self, response, sink: dict) -> None:
        self._response = response
        self._sink = sink

    def create(self, **params):
        self._sink.update(params)
        return self._response


class _FakeGroqClient:
    def __init__(self, response, sink: dict) -> None:
        self.chat = types.SimpleNamespace(completions=_FakeCompletions(response, sink))


def test_groq_translates_request_and_parses_response(monkeypatch) -> None:
    gw = LLMGateway(_settings(LLM_EFFORT="max"))
    sink: dict = {}
    response = _fake_openai_response('{"ok": true}', prompt_tokens=100, completion_tokens=20)
    monkeypatch.setattr(gw, "_groq", lambda: _FakeGroqClient(response, sink))

    out = gw.complete("hello", json_schema=json_schema_for(JudgedImpact))

    assert out.provider == "groq"
    assert out.text == '{"ok": true}'
    assert out.tokens_in == 100 and out.tokens_out == 20
    # Cost is the list-price estimate for the model, non-zero.
    assert out.cost_usd > 0
    # Structured output was requested as a strict json_schema.
    assert sink["response_format"]["type"] == "json_schema"
    assert sink["response_format"]["json_schema"]["strict"] is True
    # "max" effort is clamped to what Groq accepts.
    assert sink["reasoning_effort"] == "high"
    assert sink["model"] == "openai/gpt-oss-20b"


def test_groq_refusal_is_reported_not_returned_as_text(monkeypatch) -> None:
    gw = LLMGateway(_settings())
    sink: dict = {}
    response = _fake_openai_response("", refusal="I can't help with that")
    monkeypatch.setattr(gw, "_groq", lambda: _FakeGroqClient(response, sink))

    out = gw.complete("hello")
    assert out.refused is True
    assert out.text == ""


# --- error mapping -------------------------------------------------------


def _resp(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.groq.com/openai/v1"))


class _RaisingCompletions:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create(self, **params):
        raise self._exc


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self.chat = types.SimpleNamespace(completions=_RaisingCompletions(exc))


def test_missing_groq_key_is_a_config_error() -> None:
    # A blank key never reaches the client — Settings validation forbids the
    # empty string, so construct the gateway with a placeholder then clear it.
    gw = LLMGateway(_settings())
    gw.settings.groq_api_key = None
    with pytest.raises(GatewayError) as exc:
        gw.complete("hi")
    assert exc.value.code == "missing_api_key"


def test_invalid_key_maps_to_invalid_api_key(monkeypatch) -> None:
    gw = LLMGateway(_settings())
    err = openai.AuthenticationError("bad key", response=_resp(401), body=None)
    monkeypatch.setattr(gw, "_groq", lambda: _RaisingClient(err))
    with pytest.raises(GatewayError) as exc:
        gw.complete("hi")
    assert exc.value.code == "invalid_api_key"
    assert "key" in exc.value.human_message.lower()


def test_rate_limit_is_retried_then_surfaced(monkeypatch) -> None:
    gw = LLMGateway(_settings(LLM_MAX_RETRIES=2))
    err = openai.RateLimitError("slow down", response=_resp(429), body=None)
    client = _RaisingClient(err)
    calls = {"n": 0}
    original = client.chat.completions.create

    def counting(**params):
        calls["n"] += 1
        return original(**params)

    client.chat.completions.create = counting  # type: ignore[assignment]
    monkeypatch.setattr(gw, "_groq", lambda: client)

    with pytest.raises(GatewayError) as exc:
        gw.complete("hi")
    assert exc.value.code == "rate_limited"
    # Retried up to the configured budget, not just once.
    assert calls["n"] == 2


def test_bad_request_maps_to_invalid_request(monkeypatch) -> None:
    gw = LLMGateway(_settings())
    err = openai.BadRequestError("schema unsupported", response=_resp(400), body=None)
    monkeypatch.setattr(gw, "_groq", lambda: _RaisingClient(err))
    with pytest.raises(GatewayError) as exc:
        gw.complete("hi")
    assert exc.value.code == "invalid_request"


# --- anthropic path ------------------------------------------------------


def _fake_anthropic_response(text: str):
    block = types.SimpleNamespace(type="text", text=text)
    usage = types.SimpleNamespace(input_tokens=42, output_tokens=8)
    return types.SimpleNamespace(content=[block], usage=usage, stop_reason="end_turn")


class _FakeMessages:
    def __init__(self, response, sink: dict) -> None:
        self._response = response
        self._sink = sink

    def create(self, **params):
        self._sink.update(params)
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response, sink: dict) -> None:
        self.messages = _FakeMessages(response, sink)


def test_anthropic_path_uses_output_config(monkeypatch) -> None:
    gw = LLMGateway(
        _settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-x", LLM_MODEL="claude-opus-5")
    )
    sink: dict = {}
    monkeypatch.setattr(
        gw, "_anthropic", lambda: _FakeAnthropicClient(_fake_anthropic_response("hi there"), sink)
    )
    out = gw.complete("hello", json_schema=json_schema_for(JudgedImpact))
    assert out.provider == "anthropic"
    assert out.text == "hi there"
    assert out.tokens_in == 42 and out.tokens_out == 8
    # Structured output rides on Anthropic's output_config.format, not response_format.
    assert sink["output_config"]["format"]["type"] == "json_schema"


# --- cost accounting and concurrency ------------------------------------------


def test_an_unpriced_model_has_unknown_cost_not_zero(monkeypatch) -> None:
    gw = LLMGateway(_settings(LLM_MODEL="some/unlisted-model"))
    monkeypatch.setattr(gw, "_groq", lambda: _FakeGroqClient(_fake_openai_response("{}"), {}))
    out = gw.complete("hello")
    assert out.cost_usd is None


def test_concurrent_calls_are_bounded_by_the_configured_limit(monkeypatch) -> None:
    import threading
    import time

    gw = LLMGateway(_settings(LLM_MAX_CONCURRENCY=2))
    active = 0
    peak = 0
    lock = threading.Lock()

    class _SlowCompletions:
        def create(self, **_params):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return _fake_openai_response("{}")

    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_SlowCompletions()))
    monkeypatch.setattr(gw, "_groq", lambda: client)

    threads = [threading.Thread(target=gw.complete, args=("x",)) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak == 2


# --- obligation extraction through the gateway ---------------------------------

PARAGRAPH = "2.2 Stock brokers shall report short-collection of margin to the exchange by T+1 day."


def _extract_with(monkeypatch, *outputs: str):
    from app.ai.extraction.obligations import extract_from_paragraph

    gw = LLMGateway(_settings())
    responses = iter(outputs)

    class _Sequence:
        def create(self, **_params):
            return _fake_openai_response(next(responses))

    monkeypatch.setattr(
        gw,
        "_groq",
        lambda: types.SimpleNamespace(chat=types.SimpleNamespace(completions=_Sequence())),
    )
    return extract_from_paragraph(gw, PARAGRAPH, paragraph_char_start=200)


def _obligation_json(text: str) -> str:
    import json

    return json.dumps({"obligations": [{"text": text, "actor": "Stock brokers"}]})


def test_extraction_resolves_spans_into_full_text_coordinates(monkeypatch) -> None:
    quote = "Stock brokers shall report short-collection of margin"
    outcome = _extract_with(monkeypatch, _obligation_json(quote))
    (candidate,) = outcome.candidates
    assert candidate.span.char_start == 200 + PARAGRAPH.index(quote)
    assert candidate.extracted.confidence is None, "no confidence given, none invented"
    assert not outcome.failed and not outcome.repaired


def test_malformed_output_gets_one_repair(monkeypatch) -> None:
    good = _obligation_json("Stock brokers shall report short-collection of margin")
    outcome = _extract_with(monkeypatch, "{not json", good)
    assert outcome.repaired and not outcome.failed
    assert len(outcome.candidates) == 1


def test_fenced_json_is_accepted(monkeypatch) -> None:
    fenced = "```json\n" + _obligation_json("Stock brokers shall report short-collection") + "\n```"
    assert len(_extract_with(monkeypatch, fenced).candidates) == 1


def test_a_second_malformed_output_is_an_explicit_failure(monkeypatch) -> None:
    outcome = _extract_with(monkeypatch, "{not json", "[still not an object]")
    assert outcome.failed
    assert outcome.candidates == []
    assert "schema violation after repair" in (outcome.failure_reason or "")


def test_an_unresolvable_quote_is_dropped_and_counted(monkeypatch) -> None:
    outcome = _extract_with(monkeypatch, _obligation_json("Brokers may waive all margin entirely"))
    assert outcome.candidates == []
    assert outcome.dropped_unresolvable == 1
    assert not outcome.failed


def test_an_empty_answer_is_valid(monkeypatch) -> None:
    outcome = _extract_with(monkeypatch, '{"obligations": []}')
    assert outcome.candidates == [] and not outcome.failed


def test_extraction_cost_stays_unknown_once_a_call_is_unpriced(monkeypatch) -> None:
    from app.ai.extraction.obligations import extract_from_paragraph

    gw = LLMGateway(_settings(LLM_MODEL="some/unlisted-model"))
    monkeypatch.setattr(
        gw,
        "_groq",
        lambda: _FakeGroqClient(_fake_openai_response('{"obligations": []}'), {}),
    )
    outcome = extract_from_paragraph(gw, PARAGRAPH, 0)
    assert outcome.cost_usd is None
