"""get_model(tier): the single place that decides fake vs live and which model per tier."""

from __future__ import annotations

from typing import Literal

from careergraph.config import Settings
from careergraph.llm.budget import Budget
from careergraph.llm.fake import FakeChat
from careergraph.llm.port import ChatPort, LiveChat
from careergraph.skills.normalize import SkillNormalizer

Tier = Literal["cheap", "strong"]


class ModelFactory:
    """Builds and caches one ChatPort per tier.

    cheap  -> CHEAP_MODEL  (extraction, rationales, verification, research)
    strong -> STRONG_MODEL (drafting only)
    Demo mode always returns the deterministic fake model.
    """

    def __init__(self, settings: Settings, budget: Budget, skills: SkillNormalizer) -> None:
        self.settings, self.budget, self.skills = settings, budget, skills
        self._cache: dict[str, ChatPort] = {}

    def get_model(self, tier: Tier) -> ChatPort:
        """Return the model for a tier."""
        if tier not in self._cache:
            self._cache[tier] = self._build(tier)
        return self._cache[tier]

    def _build(self, tier: Tier) -> ChatPort:
        s = self.settings
        if s.is_demo:
            fabricate = {s.demo_fabricate_job} if s.demo_fabricate_job else set()
            return FakeChat(tier, self.budget, self.skills, fabricate)
        if tier == "cheap":
            return LiveChat(tier, s.cheap_model, s.cheap_effort, s, self.budget)
        return LiveChat(tier, s.strong_model, s.strong_effort, s, self.budget)
