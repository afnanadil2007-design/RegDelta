"""Model pricing, in USD per million tokens.

Sources: Anthropic's and Groq's published API list prices. These drive an
*estimated* API cost — list price × token count — not a billed amount; a Groq
free-tier run costs nothing while still showing a non-zero estimate here, which
is the honest way to report "what this would cost at list price". A model with
no entry yields a cost of 0.0 and a warning rather than a wrong number, so an
unpriced model is visible in the logs instead of silently skewing the report.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens."""

    input_per_mtok: float
    output_per_mtok: float


PRICING: dict[str, ModelPrice] = {
    # Anthropic (list price).
    "claude-opus-5": ModelPrice(5.00, 25.00),
    "claude-opus-4-8": ModelPrice(5.00, 25.00),
    "claude-opus-4-7": ModelPrice(5.00, 25.00),
    "claude-opus-4-6": ModelPrice(5.00, 25.00),
    "claude-sonnet-5": ModelPrice(3.00, 15.00),
    "claude-sonnet-4-6": ModelPrice(3.00, 15.00),
    "claude-haiku-4-5": ModelPrice(1.00, 5.00),
    "claude-fable-5": ModelPrice(10.00, 50.00),
    # Groq (list price; the free tier bills nothing but the estimate stands).
    "openai/gpt-oss-20b": ModelPrice(0.10, 0.50),
    "openai/gpt-oss-120b": ModelPrice(0.15, 0.75),
    "llama-3.3-70b-versatile": ModelPrice(0.59, 0.79),
    "meta-llama/llama-4-scout-17b-16e-instruct": ModelPrice(0.11, 0.34),
    "meta-llama/llama-4-maverick-17b-128e-instruct": ModelPrice(0.20, 0.60),
}

_MTOK = 1_000_000.0


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Cost of one call, or None when the model has no published price here."""
    price = PRICING.get(model)
    if price is None:
        return None
    return (tokens_in / _MTOK) * price.input_per_mtok + (
        tokens_out / _MTOK
    ) * price.output_per_mtok
