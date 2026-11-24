"""Heuristic prompt-injection scanner for untrusted text (postings, pages, READMEs).

Deterministic and cheap: weighted regexes; a text is flagged at score >= 1.0. It cannot catch
everything, which is why analysis nodes have no tools and humans approve every action. The
flag is surfaced in the shortlist so you can read the posting yourself.
"""

from __future__ import annotations

import re

from careergraph.domain.models import InjectionReport

THRESHOLD = 1.0
_RULES: list[tuple[str, float, re.Pattern[str]]] = [
    (
        "ignore-instructions",
        1.0,
        re.compile(
            r"\b(ignore|forget|override)\s+(all\s+|any\s+|your\s+|the\s+)*(previous|prior|above|earlier|"
            r"preceding)\s+(instructions|prompts?|rules|directions)",
            re.I,
        ),
    ),
    (
        "disregard-rules",
        1.0,
        re.compile(
            r"\bdisregard\s+(all\s+|any\s+|your\s+|the\s+)*(scoring|instructions|rules|rubric|guidelines|"
            r"criteria)",
            re.I,
        ),
    ),
    (
        "reveal-prompt",
        1.0,
        re.compile(r"\b(reveal|print|show|repeat)\s+(your|the)\s+(system\s+)?prompt", re.I),
    ),
    ("chat-markup", 1.0, re.compile(r"<\|im_start\|>|<\|system\|>|\[/?INST\]|<</?SYS>>", re.I)),
    (
        "note-to-ai",
        0.8,
        re.compile(
            r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?"
            r"(ai|llm|gpt|chatgpt|claude|language model|assistant|screening (tool|bot|ai))s?\b",
            re.I,
        ),
    ),
    (
        "set-score",
        0.8,
        re.compile(
            r"\b(set|give|assign)\s+(the\s+|a\s+)?(score|rating)\s+(of\s+|to\s+)?\d+|"
            r"\b(rate|score|mark)\s+(this|the)\s+(candidate|applicant|job|posting)\b[^.]{0,40}"
            r"(100|perfect|approved|top|highest)",
            re.I,
        ),
    ),
    ("role-prefix", 0.6, re.compile(r"(^|[\n.!?]\s*)(system|assistant|developer)\s*:", re.I)),
    (
        "mode-switch",
        0.6,
        re.compile(r"\byou are now\b|\b(admin|developer|god|jailbreak)\s+mode\b", re.I),
    ),
    ("zero-width", 0.4, re.compile("[​-‏‪-‮⁠-⁤]")),
]


def scan(text: str) -> InjectionReport:
    """Score text against the rules; flagged when the summed weight reaches THRESHOLD."""
    matches: list[str] = []
    score = 0.0
    for name, weight, pattern in _RULES:
        m = pattern.search(text)
        if m:
            score += weight
            matches.append(f"{name}: {m.group(0).strip()[:80]}")
    return InjectionReport(flagged=score >= THRESHOLD, score=round(score, 2), matches=matches)
