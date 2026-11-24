"""Budget enforcement. Caps are checked BEFORE each call, so one call can overshoot a cap by
at most its own size; the next call then halts the run with BudgetExceeded."""

from __future__ import annotations

from datetime import UTC, datetime

from careergraph.config import PricingConfig, Settings
from careergraph.llm.usage import UsageLedger, UsageRecord, estimate_usd


class BudgetExceeded(RuntimeError):
    """A token or USD cap was hit. The run halts; its state stays checkpointed and resumable."""

    def __init__(self, scope: str, used: float, cap: float, unit: str) -> None:
        self.scope, self.used, self.cap, self.unit = scope, used, cap, unit
        super().__init__(
            f"budget exceeded: {scope} {unit} used {used:,.4g} >= cap {cap:,.4g}. "
            "Raise the cap in .env or wait (daily caps reset at 00:00 UTC), then "
            "`make resume THREAD=<id>`."
        )


class Budget:
    """Checks caps against the ledger and records usage."""

    def __init__(self, settings: Settings, pricing: PricingConfig, ledger: UsageLedger) -> None:
        self.settings, self.pricing, self.ledger = settings, pricing, ledger

    def check(self, run_id: str) -> None:
        """Raise BudgetExceeded if any configured cap is already reached."""
        s = self.settings
        run_tokens, run_usd = self.ledger.run_totals(run_id)
        day_tokens, day_usd = self.ledger.day_totals(datetime.now(UTC).date())
        if run_tokens >= s.max_tokens_per_run:
            raise BudgetExceeded("run", run_tokens, s.max_tokens_per_run, "tokens")
        if day_tokens >= s.max_tokens_per_day:
            raise BudgetExceeded("day", day_tokens, s.max_tokens_per_day, "tokens")
        if s.max_usd_per_run is not None and run_usd >= s.max_usd_per_run:
            raise BudgetExceeded("run", run_usd, s.max_usd_per_run, "USD")
        if s.max_usd_per_day is not None and day_usd >= s.max_usd_per_day:
            raise BudgetExceeded("day", day_usd, s.max_usd_per_day, "USD")

    def record(
        self,
        *,
        run_id: str,
        task: str,
        tier: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
        fake: bool = False,
    ) -> UsageRecord:
        """Record one call (with a USD estimate when prices are configured)."""
        usd = estimate_usd(
            self.pricing, model, input_tokens, output_tokens, cache_read, cache_write
        )
        rec = UsageRecord(
            run_id=run_id,
            task=task,
            tier=tier,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            usd=usd,
            fake=fake,
        )
        self.ledger.record(rec)
        return rec
