"""Map skill spellings to canonical names and find skills in free text. No LLM involved."""

from __future__ import annotations

import re
from collections.abc import Iterable

from careergraph.config import SkillsConfig

_BOUNDARY_L = r"(?<![A-Za-z0-9+#])"
_BOUNDARY_R = r"(?![A-Za-z0-9+#])"


class SkillNormalizer:
    """Canonicalise skills via aliases; offer related skills for partial credit."""

    def __init__(self, cfg: SkillsConfig) -> None:
        self._alias: dict[str, str] = {}
        for canonical, aliases in cfg.aliases.items():
            canon = canonical.strip().lower()
            self._alias[canon] = canon
            for alias in aliases:
                self._alias[alias.strip().lower()] = canon
        self._related: dict[str, set[str]] = {}
        for skill, rel in cfg.related.items():
            canon = self.normalize(skill)
            self._alias.setdefault(canon, canon)
            self._related.setdefault(canon, set()).update(self.normalize(r) for r in rel)
        self._pattern = self._compile()

    def _compile(self) -> re.Pattern[str]:
        terms = sorted(self._alias, key=len, reverse=True)
        parts: list[str] = []
        for term in terms:
            escaped = re.escape(term).replace(r"\ ", r"[\s-]+")
            if len(term) <= 2:
                # Short terms (go, ml, tf) only match when not written in lowercase,
                # so English words like "go" do not count as the Go language.
                variants = sorted({term.upper(), term.title()})
                escaped = "(?-i:" + "|".join(re.escape(v) for v in variants) + ")"
            parts.append(f"{_BOUNDARY_L}({escaped}){_BOUNDARY_R}")
        return re.compile("|".join(parts), re.IGNORECASE) if parts else re.compile(r"(?!x)x")

    @property
    def known(self) -> set[str]:
        """All canonical skill names."""
        return set(self._alias.values())

    def normalize(self, name: str) -> str:
        """Return the canonical name (or the cleaned input if unknown)."""
        cleaned = re.sub(r"\s+", " ", name.strip().lower())
        return self._alias.get(cleaned, cleaned)

    def normalize_all(self, names: Iterable[str]) -> list[str]:
        """Canonicalise and de-duplicate, keeping first-seen order."""
        out: list[str] = []
        for n in names:
            c = self.normalize(n)
            if c and c not in out:
                out.append(c)
        return out

    def find_in_text(self, text: str) -> list[str]:
        """Return canonical skills mentioned in text, in order of first mention."""
        found: list[str] = []
        for m in self._pattern.finditer(text):
            term = next(g for g in m.groups() if g)
            canon = self.normalize(re.sub(r"[\s-]+", " ", term))
            if canon not in found:
                found.append(canon)
        return found

    def related(self, skill: str) -> set[str]:
        """Canonical skills related to the given one (one hop)."""
        return self._related.get(self.normalize(skill), set())
