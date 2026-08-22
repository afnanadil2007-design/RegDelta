"""The single chokepoint for every LLM and vision call in RegDelta.

No other module may instantiate a provider client. This one owns:
provider selection, model pinning, retries with exponential backoff, token
counting, cost accounting, and per-call structured logging carrying the run_id.

Two providers are wired:

* ``anthropic`` — the newer Messages API with ``output_config`` (effort +
  ``json_schema`` structured output) and native vision blocks.
* ``groq`` — Groq's OpenAI-compatible endpoint, driven through the ``openai``
  client with ``base_url`` pointed at Groq. This is the free-tier demo path.

The LangGraph nodes never see any of this — they call ``complete`` /
``complete_vision`` and receive a provider-agnostic :class:`LLMResponse`. All
provider-specific request translation, structured-output shaping, and error
mapping live here.

Retry policy lives here rather than in the provider SDK: both SDKs retry
transient failures on their own, so each is configured with ``max_retries=0``
and this module applies one uniform policy — otherwise the effective retry
count would be the product of the two.
"""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.pricing import estimate_cost_usd
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger("app.ai.gateway")

Role = Literal["user", "assistant"]

# Stable machine codes so the API can distinguish failure modes without parsing
# free text. Surfaced to the analyst as a short reason; the full technical
# detail stays in the logs.
ErrorCode = Literal[
    "missing_api_key",
    "invalid_api_key",
    "rate_limited",
    "timeout",
    "provider_unavailable",
    "invalid_request",
    "parse_error",
    "provider_error",
]

_HUMAN_MESSAGE: dict[str, str] = {
    "missing_api_key": "The LLM provider API key is not configured.",
    "invalid_api_key": "The LLM provider rejected the API key.",
    "rate_limited": "The LLM provider is rate limiting requests.",
    "timeout": "The LLM provider did not respond in time.",
    "provider_unavailable": "The LLM provider is temporarily unavailable.",
    "invalid_request": "The LLM provider rejected the request.",
    "parse_error": "The LLM response could not be parsed.",
    "provider_error": "The LLM provider could not complete the request.",
}


class GatewayError(RuntimeError):
    """A model call that failed. Carries a stable :attr:`code`.

    ``code`` lets callers (and the API error envelope) react to the failure
    mode — a missing key is a configuration problem, a rate limit is transient —
    without string-matching the message.
    """

    def __init__(self, message: str, *, code: ErrorCode = "provider_error") -> None:
        super().__init__(message)
        self.code: ErrorCode = code

    @property
    def human_message(self) -> str:
        """A short, secret-free sentence safe to show an analyst."""
        return _HUMAN_MESSAGE.get(self.code, _HUMAN_MESSAGE["provider_error"])


class TransientProviderError(RuntimeError):
    """Retryable provider failure (rate limit, overload, timeout, connection)."""

    def __init__(self, message: str, *, code: ErrorCode = "provider_unavailable") -> None:
        super().__init__(message)
        self.code: ErrorCode = code


@dataclass
class LLMResponse:
    """One completed model call, with everything needed to account for it."""

    text: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    stop_reason: str | None = None
    # True when the provider declined the request outright; callers must treat
    # this as a refusal rather than an empty answer.
    refused: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class _Normalized:
    """Provider-agnostic call result before cost/latency accounting."""

    text: str
    tokens_in: int
    tokens_out: int
    stop_reason: str | None
    refused: bool


# Groq's gpt-oss reasoning models accept low/medium/high; the shared effort
# scale goes higher, so anything above "high" is clamped down for Groq.
_GROQ_EFFORT: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}

# JSON Schema keywords OpenAI-compatible strict structured outputs reject.
# Stripped from the schema handed to the model; Pydantic still enforces them
# after parsing, so the validation contract is unchanged.
_UNSUPPORTED_STRICT_KEYS = frozenset(
    {
        "default",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "title",
        "examples",
    }
)


def _openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Pydantic JSON Schema to OpenAI-compatible strict structured output.

    Strict mode has two hard requirements: every object must set
    ``additionalProperties: false`` and list *all* of its properties in
    ``required``. It also rejects validation keywords (``minLength``,
    ``minimum``, ``default`` …). We drop those here — Pydantic re-checks them
    when it validates the returned JSON, so nothing is weakened.
    """

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            cleaned = {k: walk(v) for k, v in node.items() if k not in _UNSUPPORTED_STRICT_KEYS}
            if cleaned.get("type") == "object":
                cleaned["additionalProperties"] = False
                props = cleaned.get("properties")
                if isinstance(props, dict):
                    cleaned["required"] = list(props.keys())
            return cleaned
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(schema)  # type: ignore[return-value]


class LLMGateway:
    """Provider-agnostic client. Construct once and share."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Any = None
        # One gateway is shared across the graph's concurrent obligation workers,
        # which build the client from several threads at once. Without this lock
        # the lazy init below races: threads each construct a client (leaking
        # httpx pools) and can observe a half-assigned one, surfacing as spurious
        # connection errors. Double-checked locking builds it exactly once.
        self._client_lock = threading.Lock()

    def _http_timeout(self) -> Any:
        """Generous timeout: the default 5s connect is too tight under the CPU
        contention of concurrent CPU reranking running alongside these calls."""
        import httpx

        return httpx.Timeout(self.settings.llm_request_timeout_seconds, connect=30.0)

    # --- provider wiring -------------------------------------------------

    def _anthropic(self) -> Any:
        """Lazily build the Anthropic client (import cost is non-trivial)."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    import anthropic

                    if not self.settings.anthropic_api_key:
                        raise GatewayError(
                            "ANTHROPIC_API_KEY is not set.", code="missing_api_key"
                        )
                    self._client = anthropic.Anthropic(
                        api_key=self.settings.anthropic_api_key,
                        max_retries=0,  # this module owns retries; see module docstring
                        timeout=self._http_timeout(),
                    )
        return self._client

    def _groq(self) -> Any:
        """Lazily build the OpenAI client pointed at Groq's endpoint."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from openai import OpenAI

                    if not self.settings.groq_api_key:
                        raise GatewayError(
                            "GROQ_API_KEY is not set.", code="missing_api_key"
                        )
                    self._client = OpenAI(
                        api_key=self.settings.groq_api_key,
                        base_url=self.settings.groq_base_url,
                        max_retries=0,  # this module owns retries; see module docstring
                        timeout=self._http_timeout(),
                    )
        return self._client

    # --- public API ------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Text completion. Pass ``json_schema`` to constrain the output shape."""
        return self._dispatch(
            prompt,
            image_png=None,
            system=system,
            max_tokens=max_tokens,
            model=model or self.settings.llm_model,
            json_schema=json_schema,
        )

    def complete_vision(
        self,
        prompt: str,
        image_png: bytes,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Vision completion over a single PNG (the ingestion fallback path)."""
        return self._dispatch(
            prompt,
            image_png=image_png,
            system=system,
            max_tokens=max_tokens,
            model=self.settings.vision_model,
            json_schema=None,
        )

    # --- internals -------------------------------------------------------

    def _dispatch(
        self,
        prompt: str,
        *,
        image_png: bytes | None,
        system: str | None,
        max_tokens: int | None,
        model: str,
        json_schema: dict[str, Any] | None,
    ) -> LLMResponse:
        provider = self.settings.llm_provider
        started = time.perf_counter()
        try:
            if provider == "anthropic":
                normalized = self._anthropic_with_retry(
                    prompt,
                    image_png=image_png,
                    system=system,
                    max_tokens=max_tokens,
                    model=model,
                    json_schema=json_schema,
                )
            elif provider == "groq":
                normalized = self._groq_with_retry(
                    prompt,
                    image_png=image_png,
                    system=system,
                    max_tokens=max_tokens,
                    model=model,
                    json_schema=json_schema,
                )
            else:  # pragma: no cover - Provider Literal is exhaustive
                raise GatewayError(
                    f"LLM_PROVIDER={provider!r} is not supported.", code="invalid_request"
                )
        except RetryError as exc:
            cause = exc.last_attempt.exception()
            code: ErrorCode = getattr(cause, "code", "provider_unavailable")
            raise GatewayError(
                f"{provider} call failed after {self.settings.llm_max_retries} attempts: {cause}",
                code=code,
            ) from exc

        return self._finalize(normalized, model=model, provider=provider, started=started)

    # --- anthropic -------------------------------------------------------

    def _anthropic_with_retry(self, prompt: str, **kwargs: Any) -> _Normalized:
        retrying = retry(
            stop=stop_after_attempt(self.settings.llm_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type(TransientProviderError),
            reraise=False,
        )
        return retrying(self._call_anthropic)(prompt, **kwargs)

    def _call_anthropic(
        self,
        prompt: str,
        *,
        image_png: bytes | None,
        system: str | None,
        max_tokens: int | None,
        model: str,
        json_schema: dict[str, Any] | None,
    ) -> _Normalized:
        import anthropic

        content: list[dict[str, Any]] = []
        if image_png is not None:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(image_png).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": prompt})

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": self.settings.llm_effort},
        }
        if system:
            params["system"] = system
        if json_schema:
            params["output_config"]["format"] = {
                "type": "json_schema",
                "schema": json_schema,
            }

        try:
            raw = self._anthropic().messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise TransientProviderError(str(exc), code="rate_limited") from exc
        except (anthropic.InternalServerError, anthropic.APIConnectionError) as exc:
            raise TransientProviderError(str(exc), code="provider_unavailable") from exc
        except anthropic.AuthenticationError as exc:
            raise GatewayError(str(exc), code="invalid_api_key") from exc
        except anthropic.APIStatusError as exc:  # other 4xx — not retryable
            raise GatewayError(
                f"provider rejected the request: {exc}", code="invalid_request"
            ) from exc

        refused = raw.stop_reason == "refusal"
        text = (
            ""
            if refused
            else "".join(block.text for block in raw.content if block.type == "text")
        )
        return _Normalized(
            text=text,
            tokens_in=int(getattr(raw.usage, "input_tokens", 0) or 0),
            tokens_out=int(getattr(raw.usage, "output_tokens", 0) or 0),
            stop_reason=raw.stop_reason,
            refused=refused,
        )

    # --- groq (OpenAI-compatible) ---------------------------------------

    def _groq_with_retry(self, prompt: str, **kwargs: Any) -> _Normalized:
        retrying = retry(
            stop=stop_after_attempt(self.settings.llm_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type(TransientProviderError),
            reraise=False,
        )
        return retrying(self._call_groq)(prompt, **kwargs)

    def _call_groq(
        self,
        prompt: str,
        *,
        image_png: bytes | None,
        system: str | None,
        max_tokens: int | None,
        model: str,
        json_schema: dict[str, Any] | None,
    ) -> _Normalized:
        import openai

        user_content: Any
        if image_png is not None:
            data_uri = "data:image/png;base64," + base64.standard_b64encode(image_png).decode(
                "ascii"
            )
            user_content = [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": prompt},
            ]
        else:
            user_content = prompt

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_content})

        params: dict[str, Any] = {
            "model": model,
            "max_completion_tokens": max_tokens or self.settings.llm_max_tokens,
            "messages": messages,
            # gpt-oss models expose reasoning effort; harmless on models that
            # ignore it. Clamp the shared scale to what Groq accepts.
            "reasoning_effort": _GROQ_EFFORT.get(self.settings.llm_effort, "medium"),
        }
        if json_schema:
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": _openai_strict_schema(json_schema),
                    "strict": True,
                },
            }

        try:
            raw = self._groq().chat.completions.create(**params)
        except openai.RateLimitError as exc:
            raise TransientProviderError(str(exc), code="rate_limited") from exc
        except openai.APITimeoutError as exc:
            raise TransientProviderError(str(exc), code="timeout") from exc
        except (openai.APIConnectionError, openai.InternalServerError) as exc:
            # openai flattens transport failures to "Connection error."; keep the
            # underlying cause so the trace shows what actually failed.
            detail = f"{exc} (cause: {exc.__cause__!r})" if exc.__cause__ else str(exc)
            raise TransientProviderError(detail, code="provider_unavailable") from exc
        except openai.AuthenticationError as exc:
            raise GatewayError(str(exc), code="invalid_api_key") from exc
        except openai.APIStatusError as exc:
            # Groq signals token-per-minute / request-size limits as HTTP 413 with
            # body code 'rate_limit_exceeded' (RPM limits come back as 429, caught
            # above). Treat those as retryable rate limits, not a fatal bad request
            # — otherwise a free-tier TPM cap aborts the whole assessment.
            body_code = ""
            body = getattr(exc, "body", None)
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                body_code = body["error"].get("code", "") or ""
            if exc.status_code in (409, 413, 429) or body_code == "rate_limit_exceeded":
                raise TransientProviderError(str(exc), code="rate_limited") from exc
            if body_code == "json_validate_failed":
                # The model produced output that did not satisfy the structured
                # schema (often an empty generation when reasoning used the whole
                # token budget). Retry it — a fresh generation usually validates —
                # and if it never does, it is a per-call output failure that drops
                # one finding, not a fatal request error that aborts the run.
                raise TransientProviderError(str(exc), code="parse_error") from exc
            raise GatewayError(
                f"provider rejected the request: {exc}", code="invalid_request"
            ) from exc

        return self._normalize_openai(raw)

    @staticmethod
    def _normalize_openai(raw: Any) -> _Normalized:
        try:
            choice = raw.choices[0]
            message = choice.message
            finish = choice.finish_reason
        except (AttributeError, IndexError) as exc:
            raise GatewayError(
                f"malformed provider response: {exc}", code="parse_error"
            ) from exc

        # OpenAI-compatible refusal signals: a populated `refusal` field, or a
        # content_filter finish reason. Either means: no usable answer.
        refused = bool(getattr(message, "refusal", None)) or finish == "content_filter"
        text = "" if refused else (message.content or "")

        usage = getattr(raw, "usage", None)
        return _Normalized(
            text=text,
            tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
            stop_reason=finish,
            refused=refused,
        )

    # --- accounting ------------------------------------------------------

    def _finalize(
        self, n: _Normalized, *, model: str, provider: str, started: float
    ) -> LLMResponse:
        latency_ms = int((time.perf_counter() - started) * 1000)

        cost = estimate_cost_usd(model, n.tokens_in, n.tokens_out)
        if cost is None:
            log.warning("gateway.unpriced_model", extra={"model": model})
            cost = 0.0

        log.info(
            "gateway.call",
            extra={
                "provider": provider,
                "model": model,
                "tokens_in": n.tokens_in,
                "tokens_out": n.tokens_out,
                "cost_usd": round(cost, 6),
                "latency_ms": latency_ms,
                "stop_reason": n.stop_reason,
                "refused": n.refused,
            },
        )
        return LLMResponse(
            text=n.text,
            model=model,
            provider=provider,
            tokens_in=n.tokens_in,
            tokens_out=n.tokens_out,
            cost_usd=cost,
            latency_ms=latency_ms,
            stop_reason=n.stop_reason,
            refused=n.refused,
        )
