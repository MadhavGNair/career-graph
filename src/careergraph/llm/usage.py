"""Token (and optional USD) accounting. The ledger is the DB in production, memory in tests."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

from careergraph.config import PricingConfig


@dataclass(frozen=True)
class UsageRecord:
    """One LLM call's usage."""

    run_id: str
    task: str
    tier: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    usd: float | None = None
    fake: bool = False
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tokens(self) -> int:
        """Input + output tokens (cache reads/writes are part of input)."""
        return self.input_tokens + self.output_tokens


class UsageLedger(Protocol):
    """Where usage is recorded and summed."""

    def record(self, rec: UsageRecord) -> None:
        """Persist one record."""
        ...

    def run_totals(self, run_id: str) -> tuple[int, float]:
        """(tokens, usd) for a run."""
        ...

    def day_totals(self, day: date) -> tuple[int, float]:
        """(tokens, usd) for a UTC day across runs."""
        ...


class InMemoryLedger:
    """Ledger for tests and evals."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []
        self._lock = threading.Lock()

    def record(self, rec: UsageRecord) -> None:
        """Append a record."""
        with self._lock:
            self.records.append(rec)

    def run_totals(self, run_id: str) -> tuple[int, float]:
        """Sum a run."""
        rs = [r for r in self.records if r.run_id == run_id]
        return sum(r.total_tokens for r in rs), sum(r.usd or 0.0 for r in rs)

    def day_totals(self, day: date) -> tuple[int, float]:
        """Sum a UTC day."""
        rs = [r for r in self.records if r.ts.date() == day]
        return sum(r.total_tokens for r in rs), sum(r.usd or 0.0 for r in rs)


def estimate_usd(
    pricing: PricingConfig, model: str, inp: int, out: int, cache_read: int, cache_write: int
) -> float | None:
    """USD for one call, or None when prices for the model are not configured."""
    price = pricing.models.get(model)
    if price is None or not price.is_set:
        return None
    plain_input = max(inp - cache_read - cache_write, 0)
    cr = (
        price.cache_read_per_mtok if price.cache_read_per_mtok is not None else price.input_per_mtok
    )
    cw = (
        price.cache_write_per_mtok
        if price.cache_write_per_mtok is not None
        else price.input_per_mtok
    )
    assert price.input_per_mtok is not None and price.output_per_mtok is not None
    total = (
        plain_input * price.input_per_mtok
        + out * price.output_per_mtok
        + cache_read * (cr or 0.0)
        + cache_write * (cw or 0.0)
    )
    return total / 1_000_000
