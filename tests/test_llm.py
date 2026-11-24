"""Budgets, the fake LLM handlers and the live client (mocked; no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.messages import AIMessage, SystemMessage

from careergraph.config import REPO_ROOT, ModelPrice, PricingConfig, Settings
from careergraph.domain.models import Entailment, JobAnalysis, ProfileDocument, ProfileExtraction
from careergraph.llm import port as port_mod
from careergraph.llm.budget import Budget, BudgetExceeded
from careergraph.llm.factory import ModelFactory
from careergraph.llm.fake import FakeChat, fake_verify, parse_salary, seniority_from_title
from careergraph.llm.port import LiveChat, LLMOutputError
from careergraph.llm.usage import InMemoryLedger, estimate_usd
from careergraph.skills import SkillNormalizer
from tests.conftest import make_settings

DEMO = REPO_ROOT / "data" / "demo"


def _budget(s: Settings, pricing: PricingConfig | None = None) -> Budget:
    return Budget(s, pricing or PricingConfig(), InMemoryLedger())


def test_token_budget_halts_run(tmp_path: Path, skills: SkillNormalizer) -> None:
    s = make_settings(tmp_path, max_tokens_per_run=1000)
    chat = FakeChat("cheap", _budget(s), skills, set())
    doc = ProfileDocument(
        source_id="cv",
        kind="cv",
        title="cv.md",
        text="## Projects\n- " + "Python " * 2000,
        content_hash="h",
    )
    payload = {"document": doc.model_dump()}
    chat.structured(task="extract_profile", schema=ProfileExtraction, system="s", prompt="p" * 4000,
                    payload=payload, run_id="r1")  # fmt: skip
    with pytest.raises(BudgetExceeded) as exc:
        chat.structured(task="extract_profile", schema=ProfileExtraction, system="s", prompt="p",
                        payload=payload, run_id="r1")  # fmt: skip
    assert exc.value.scope == "run" and "make resume" in str(exc.value)
    # another run is unaffected by the per-run cap
    chat.structured(task="extract_profile", schema=ProfileExtraction, system="s", prompt="p",
                    payload=payload, run_id="r2")  # fmt: skip


def test_usd_cap_only_with_prices(tmp_path: Path) -> None:
    s = make_settings(
        tmp_path, max_usd_per_run=0.01, max_tokens_per_run=10**8, max_tokens_per_day=10**8
    )
    b = _budget(s)
    b.record(run_id="r", task="t", tier="cheap", model="m", input_tokens=10**6, output_tokens=0)
    b.check("r")  # no prices -> USD cap cannot apply
    priced = PricingConfig(models={"m": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0)})
    b2 = _budget(s, priced)
    b2.record(run_id="r", task="t", tier="cheap", model="m", input_tokens=10**6, output_tokens=0)
    with pytest.raises(BudgetExceeded) as exc:
        b2.check("r")
    assert exc.value.unit == "USD"


def test_estimate_usd_with_cache() -> None:
    p = PricingConfig(
        models={"m": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0, cache_read_per_mtok=0.1)}
    )
    assert estimate_usd(p, "m", 1_000_000, 0, 1_000_000, 0) == pytest.approx(0.1)
    assert estimate_usd(PricingConfig(), "m", 1, 1, 0, 0) is None


def test_fake_profile_extraction_from_demo_cv(skills: SkillNormalizer) -> None:
    from careergraph.llm.fake import fake_extract_profile

    text = (DEMO / "profile" / "cv.md").read_text()
    doc = {"text": text, "title": "cv.md", "kind": "cv", "uri": ""}
    items = fake_extract_profile({"document": doc}, skills).items
    kinds = [i.kind for i in items]
    assert kinds.count("experience") == 11 and kinds.count("education") == 2
    first = items[0]
    assert "kubernetes" in first.skills and first.dates == "2021-03 to present"
    assert first.source_ref == "cv.md#experience/quillfeather-analytics-gmbh"


def test_fake_verifier_matches_seeded_gold() -> None:
    cases = yaml.safe_load((DEMO / "evals" / "seeded_claims.yaml").read_text())["cases"]
    for c in cases:
        ev = [{"id": f"e{i}", "text": t, "skills": []} for i, t in enumerate(c["evidence"])]
        out = fake_verify({"claim": c["claim"], "evidence": ev})
        assert out.label == c["expected"], (c["id"], out)


def test_fake_helpers() -> None:
    s = parse_salary("Pay: €85,000 - €105,000 per year")
    assert s is not None and (s.min, s.max, s.currency) == (85000, 105000, "EUR")
    g = parse_salary("€70.000 - €85.000 pro Jahr")
    assert g is not None and g.min == 70000
    assert seniority_from_title("Staff Machine Learning Engineer") == "staff"
    assert seniority_from_title("Machine Learning Intern") == "intern"


def test_factory_returns_fake_in_demo(tmp_path: Path, skills: SkillNormalizer) -> None:
    s = make_settings(tmp_path)
    f = ModelFactory(s, _budget(s), skills)
    assert f.get_model("cheap").model == "fake:cheap"
    assert f.get_model("strong") is f.get_model("strong")


# ------------------------------------------------------------------- live (mocked)


class _StubRunnable:
    def __init__(self, result: dict[str, Any], calls: list[Any]) -> None:
        self.result, self.calls = result, calls

    def invoke(self, messages: list[Any]) -> dict[str, Any]:
        self.calls.append(messages)
        return self.result


class _StubChat:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[Any] = []
        self.so_kwargs: dict[str, Any] = {}

    def with_structured_output(self, schema: type, **kwargs: Any) -> _StubRunnable:
        self.so_kwargs = {"schema": schema, **kwargs}
        return _StubRunnable(self.result, self.calls)


def _live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]):
    captured: dict[str, Any] = {}
    stub = _StubChat(result)

    def fake_init(model: str, **kwargs: Any) -> _StubChat:
        captured.update({"model": model, **kwargs})
        return stub

    monkeypatch.setattr(port_mod, "init_chat_model", fake_init)
    s = make_settings(tmp_path, app_mode="live", anthropic_api_key="sk-test")
    ledger = InMemoryLedger()
    chat = LiveChat("cheap", s.cheap_model, s.cheap_effort, s, Budget(s, PricingConfig(), ledger))
    return chat, stub, captured, ledger


def test_live_structured_uses_json_schema_cache_and_records_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = AIMessage(
        content="{}",
        usage_metadata={
            "input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
            "input_token_details": {"cache_read": 100},
        },
    )  # fmt: skip
    parsed = Entailment(label="supported", quote="q")
    chat, stub, captured, ledger = _live(
        tmp_path, monkeypatch, {"raw": raw, "parsed": parsed, "parsing_error": None}
    )
    out = chat.structured(task="verify_claim", schema=Entailment, system="SYS", prompt="P",
                          payload={}, run_id="r")  # fmt: skip
    assert out == parsed
    assert captured["model"] == "anthropic:claude-haiku-5-5"
    assert captured["effort"] == "low" and captured["api_key"] == "sk-test"
    assert "temperature" not in captured
    assert stub.so_kwargs["method"] == "json_schema" and stub.so_kwargs["include_raw"] is True
    sys_msg = stub.calls[0][0]
    assert isinstance(sys_msg, SystemMessage)
    assert sys_msg.content[0]["cache_control"] == {"type": "ephemeral"}  # type: ignore[index]
    rec = ledger.records[0]
    assert (rec.input_tokens, rec.output_tokens, rec.cache_read_tokens) == (120, 30, 100)
    assert not rec.fake


def test_live_parsing_error_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat, *_ = _live(
        tmp_path,
        monkeypatch,
        {"raw": AIMessage(content="x"), "parsed": None, "parsing_error": ValueError("bad")},
    )
    with pytest.raises(LLMOutputError):
        chat.structured(task="extract_job", schema=JobAnalysis, system="s", prompt="p",
                        payload={}, run_id="r")  # fmt: skip


def test_real_init_chat_model_builds_anthropic_client_offline(tmp_path: Path) -> None:
    """Constructing the real client makes no network call; checks kwargs are accepted."""
    s = make_settings(tmp_path, app_mode="live", anthropic_api_key="sk-test")
    chat = LiveChat("strong", s.strong_model, s.strong_effort, s, _budget(s))
    inner = chat._chat
    assert type(inner).__name__ == "ChatAnthropic"
    assert inner.model == "claude-sonnet-5-5"
    assert inner.max_tokens == s.max_output_tokens_per_call
