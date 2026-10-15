"""Per-assessment limits on provider calls and tokens."""

from __future__ import annotations

import threading

from app.ai.gateway import LLMResponse


class BudgetExhausted(RuntimeError):
    """Raised instead of making a provider call once the run's budget is spent."""


class CallBudget:
    """Per-assessment limits on provider calls and tokens, shared by all workers.

    Judge calls run in worker threads, so every method takes the lock. A call
    already in flight when the token cap is crossed completes; the next one is
    refused.
    """

    def __init__(self, max_calls: int, max_tokens: int) -> None:
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls = 0
        self.tokens = 0
        self.cost_usd = 0.0
        self.unpriced_calls = 0
        self.exhausted_reason: str | None = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Claim one call, or raise BudgetExhausted."""
        with self._lock:
            if self.exhausted_reason is None:
                if self.calls >= self.max_calls:
                    self.exhausted_reason = (
                        f"Call budget reached: {self.calls} of {self.max_calls} provider calls."
                    )
                elif self.tokens >= self.max_tokens:
                    self.exhausted_reason = (
                        f"Token budget reached: {self.tokens} of {self.max_tokens} tokens."
                    )
            if self.exhausted_reason is not None:
                raise BudgetExhausted(self.exhausted_reason)
            self.calls += 1

    def record(self, response: LLMResponse) -> None:
        with self._lock:
            self.tokens += response.total_tokens
            if response.cost_usd is None:
                self.unpriced_calls += 1
            else:
                self.cost_usd += response.cost_usd

    @property
    def exhausted(self) -> bool:
        return self.exhausted_reason is not None
