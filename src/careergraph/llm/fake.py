"""Deterministic, input-dependent fake chat model for demo mode, tests and fake-mode evals.

It implements the same ChatPort interface as the live model. Each task has a handler that
reads the structured payload the prompt was built from (keyword extraction, evidence-based
composition, token-overlap entailment) so outputs change with inputs. Token usage is
estimated as characters / 4 and recorded like real usage, so budgets are exercised.

Scenario: draft requests whose job_id is in `fabricate_job_ids` get one fabricated claim on
the first draft (revision 0), so the verify -> revise loop is visible in the demo.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from careergraph.domain.models import (
    Claim,
    CVDraft,
    DraftOutput,
    Entailment,
    EvidenceDraft,
    JobAnalysis,
    LetterDraft,
    MatchRationale,
    ProfileExtraction,
    ResearchBrief,
    ResearchFact,
    RoleBullets,
    Salary,
    SearchResult,
)
from careergraph.llm.budget import Budget
from careergraph.skills.normalize import SkillNormalizer

FABRICATED_CLAIM = (
    "Led a 40-person machine learning organisation at Google and earned a PhD in 2015."
)

STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "the",
        "to",
        "we",
        "with",
        "you",
        "your",
        "will",
        "this",
        "that",
        "who",
        "what",
        "which",
        "into",
        "over",
        "under",
        "while",
        "using",
        "used",
        "use",
        "also",
        "more",
        "than",
        "across",
        "their",
        "them",
        "they",
        "then",
        "there",
        "these",
        "those",
        "such",
        "been",
        "was",
        "were",
        "per",
        "via",
        "i",
        "my",
        "me",
        "am",
    ]
)
FRAMING = frozenset(
    [
        "applying",
        "apply",
        "role",
        "position",
        "excited",
        "bring",
        "would",
        "welcome",
        "chance",
        "discuss",
        "experience",
        "fits",
        "fit",
        "team",
        "join",
        "believe",
        "contribute",
        "opportunity",
        "interested",
        "recent",
        "work",
        "strong",
        "background",
        "focus",
        "look",
        "forward",
        "thank",
        "consideration",
        "how",
        "where",
    ]
)
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#]*")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_SENT = re.compile(r"(?<=[.!?])\s+")


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_tokens(text: str, extra_stop: set[str] | frozenset[str] = frozenset()) -> set[str]:
    """Lowercased, lightly stemmed content words."""
    return {
        _stem(w)
        for w in (t.lower() for t in _WORD.findall(text))
        if len(w) >= 3 and w not in STOP and w not in FRAMING and w not in extra_stop
    }


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _approx_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


# ------------------------------------------------------------------------- profile


_SECTION_KIND = [
    (re.compile(r"experience|employment|work", re.I), "experience"),
    (re.compile(r"project", re.I), "project"),
    (re.compile(r"education", re.I), "education"),
    (re.compile(r"publication|talk", re.I), "publication"),
    (re.compile(r"achievement|award|honou?r", re.I), "achievement"),
]
_RANGE = re.compile(r"(\d{4}(?:-\d{2})?)\s*(?:to|-|–)\s*(present|\d{4}(?:-\d{2})?)", re.I)
_ACTION = re.compile(
    r"\b(built|led|shipped|reduced|designed|deployed|developed|created|improved|migrated|"
    r"mentored|published|launched|cut|introduced)\b",
    re.I,
)


def _section_kind(heading: str) -> str | None:
    return next((k for p, k in _SECTION_KIND if p.search(heading)), None)


def fake_extract_profile(payload: dict[str, Any], skills: SkillNormalizer) -> ProfileExtraction:
    """Bullets under known CV headings become items; letters yield action sentences; a GitHub
    repo yields one project item."""
    doc = payload["document"]
    text, title, kind = doc["text"], doc["title"], doc["kind"]
    items: list[EvidenceDraft] = []
    if kind == "github_repo":
        name = re.search(r"Repository:\s*(.+)", text)
        desc = re.search(r"Description:\s*(.+)", text)
        pushed = re.search(r"Last push:\s*(\d{4})", text)
        summary = f"Open-source project {name.group(1) if name else title}"
        summary += f": {desc.group(1).strip().rstrip('.')}." if desc else "."
        items.append(
            EvidenceDraft(
                kind="project",
                text=summary,
                skills=skills.find_in_text(text),
                source_ref=doc.get("uri") or title,
                dates=pushed.group(1) if pushed else "",
            )
        )
        return ProfileExtraction(items=items)
    if kind == "letter":
        for sent in _SENT.split(re.sub(r"\s+", " ", text)):
            found = skills.find_in_text(sent)
            if found and _ACTION.search(sent) and len(sent) > 40:
                items.append(
                    EvidenceDraft(
                        kind="achievement",
                        text=sent.strip(),
                        skills=found,
                        source_ref=f"{title}#letter",
                    )
                )
        return ProfileExtraction(items=items)
    section: str | None = None
    section_name, sub, sub_dates = "", "", ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section_name = stripped[3:].strip()
            section, sub, sub_dates = _section_kind(section_name), "", ""
        elif stripped.startswith("### "):
            sub = stripped[4:].split(":")[0].strip()
            rng = _RANGE.search(stripped)
            sub_dates = f"{rng.group(1)} to {rng.group(2)}" if rng else ""
        elif stripped.startswith(("- ", "* ")) and section:
            body = stripped[2:].strip()
            rng = _RANGE.search(body)
            ref = f"{title}#{_slug(section_name)}" + (f"/{_slug(sub)}" if sub else "")
            items.append(
                EvidenceDraft(
                    kind=section,  # type: ignore[arg-type]
                    text=body,
                    skills=skills.find_in_text(body),
                    source_ref=ref,
                    dates=sub_dates or (f"{rng.group(1)} to {rng.group(2)}" if rng else ""),
                )
            )
    return ProfileExtraction(items=items)


# ---------------------------------------------------------------------------- jobs

_MUST_H = re.compile(
    r"^(requirements|what you bring|must[- ]have|you have|qualifications|about you|"
    r"anforderungen|das bringst du mit|dein profil)\b",
    re.I,
)
_NICE_H = re.compile(r"^(nice[- ]to[- ]have|bonus|plus|wünschenswert|von vorteil)\b", re.I)
_OTHER_H = re.compile(
    r"^(responsibilities|what you will do|what you'll do|about (us|the role)|benefits|"
    r"we offer|aufgaben|deine aufgaben|wir bieten|salary|compensation|location)\b",
    re.I,
)
_GERMAN = frozenset(
    [
        "und",
        "der",
        "die",
        "das",
        "wir",
        "sie",
        "mit",
        "für",
        "du",
        "bist",
        "ist",
        "eine",
        "einen",
        "im",
        "zu",
        "auf",
        "bei",
    ]
)
_RED_FLAGS = [
    "unpaid",
    "rockstar",
    "ninja",
    "24/7",
    "unlimited overtime",
    "commission only",
    "work hard, play hard",
]
_CURRENCY = {"€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "$": "USD", "usd": "USD"}
_SALARY = re.compile(
    r"(€|eur|£|gbp|\$|usd)\s?(\d{2,3}(?:[.,]\d{3})?)\s?(k)?\s?(?:-|–|to)\s?(?:€|eur|£|gbp|\$|usd)?"
    r"\s?(\d{2,3}(?:[.,]\d{3})?)\s?(k)?",
    re.I,
)


def _amount(num: str, k: str | None) -> int:
    value = int(num.replace(",", "").replace(".", ""))
    return value * 1000 if k or value < 1000 else value


def parse_salary(text: str) -> Salary | None:
    """Parse the first salary range like '€85,000 - €105,000' or 'EUR 85k-105k'."""
    m = _SALARY.search(text)
    if not m:
        return None
    lo, hi = _amount(m.group(2), m.group(3)), _amount(m.group(4), m.group(5) or m.group(3))
    return Salary(min=lo, max=hi, currency=_CURRENCY[m.group(1).lower()], period="year")


def seniority_from_title(title: str) -> str:
    """Infer seniority from title keywords."""
    t = title.lower()
    for pattern, level in (
        (r"\bintern|praktikant", "intern"),
        (r"\bjunior|\bjr\b", "junior"),
        (r"\bprincipal\b", "principal"),
        (r"\bstaff\b", "staff"),
        (r"\blead\b|\bhead of\b", "lead"),
        (r"\bsenior\b|\bsr\b", "senior"),
    ):
        if re.search(pattern, t):
            return level
    return "mid"


def is_german(text: str) -> bool:
    """Cheap language guess by German stopword ratio."""
    words = [w.lower() for w in _WORD.findall(text)]
    return bool(words) and sum(w in _GERMAN for w in words) / len(words) > 0.06


def fake_extract_job(payload: dict[str, Any], skills: SkillNormalizer) -> JobAnalysis:
    """Keyword extraction with section awareness."""
    p = payload["posting"]
    text: str = p["description"]
    intro: list[str] = []
    buckets: dict[str, list[str]] = {"must": [], "nice": [], "other": []}
    current = "intro"
    for raw in text.splitlines():
        line = raw.strip().strip("#*").strip()
        head = line.rstrip(":").strip()
        if _MUST_H.match(head):
            current = "must"
        elif _NICE_H.match(head):
            current = "nice"
        elif _OTHER_H.match(head):
            current = "other"
        elif current == "intro":
            intro.append(line)
        else:
            buckets[current].append(line)
    must_text, nice_text = "\n".join(buckets["must"]), "\n".join(buckets["nice"])
    must = skills.find_in_text(must_text) if must_text else skills.find_in_text(text)
    nice = [s for s in skills.find_in_text(nice_text) if s not in must]
    for lang_skill in ("german",):
        if lang_skill in must:
            must.remove(lang_skill)
    languages = ["de"] if is_german(text) else ["en"]
    if re.search(
        r"(fluent|business|native|c1|c2)[^.\n]{0,30}(german|deutsch)", must_text, re.I
    ) or re.search(
        r"(german|deutsch)[^.\n]{0,30}(fluent|fließend|business|native|c1|c2)", must_text, re.I
    ):
        languages = sorted(set(languages) | {"de"})
    words = " ".join(intro or [text]).split()
    lowered = text.lower()
    remote = p.get("remote") or "unknown"
    if remote == "unknown":
        if re.search(r"fully remote|remote[- ]first|100% remote", lowered):
            remote = "remote"
        elif "hybrid" in lowered:
            remote = "hybrid"
        elif re.search(r"on-?site|in the office|vor ort", lowered):
            remote = "onsite"
    return JobAnalysis(
        summary=" ".join(words[:80]),
        must_have=must,
        nice_to_have=nice,
        seniority=seniority_from_title(p["title"]),  # type: ignore[arg-type]
        location=p.get("location", ""),
        remote=remote,
        languages=languages,
        salary=parse_salary(p.get("salary_text") or text),
        red_flags=[f for f in _RED_FLAGS if f in lowered],
        injection_flag="ignore all previous instructions" in lowered,
    )


def fake_rationale(payload: dict[str, Any]) -> MatchRationale:
    """Template rationale from the breakdown facts."""
    matched, missing = payload.get("matched", [])[:3], payload.get("missing", [])[:3]
    text = f"Scores {payload['score']:.0f}/100"
    text += f": evidence for {', '.join(matched)}" if matched else ": little direct skill evidence"
    text += f"; missing {', '.join(missing)}." if missing else "."
    return MatchRationale(rationale=text)


# ------------------------------------------------------------------------ drafting


def _sentence(text: str) -> str:
    t = text.strip().rstrip(".")
    return t[0].upper() + t[1:] + "." if t else t


def fake_draft(payload: dict[str, Any], fabricate_job_ids: set[str]) -> DraftOutput:
    """Compose CV and letter claims from the provided (already ranked) evidence."""
    evidence: list[dict[str, Any]] = payload["evidence"]
    job = payload["job"]
    rejected = set(payload.get("unsupported", []))
    by_kind = lambda *kinds: [e for e in evidence if e["kind"] in kinds]  # noqa: E731
    summary = [
        Claim(text=_sentence(e["text"]), evidence_ids=[e["id"]])
        for e in by_kind("experience", "achievement")[:2]
    ]
    if payload["job_id"] in fabricate_job_ids and payload.get("revision", 0) == 0 and evidence:
        summary.append(Claim(text=FABRICATED_CLAIM, evidence_ids=[evidence[0]["id"]]))
    roles = [
        RoleBullets(
            employer=emp,
            bullets=[
                Claim(text=_sentence(e["text"]), evidence_ids=[e["id"]])
                for e in by_kind("experience")
                if _slug(emp) in e["source_ref"].lower()
            ][:4],
        )
        for emp in payload["employers"]
    ]
    projects = [
        Claim(text=_sentence(e["text"]), evidence_ids=[e["id"]]) for e in by_kind("project")[:3]
    ]
    have = [s for e in evidence for s in e["skills"]]
    wanted = [s for s in job.get("must_have", []) + job.get("nice_to_have", []) if s in have]
    skills_list = list(dict.fromkeys(wanted + have))[:12]
    top = evidence[:3]
    paragraphs = []
    if top:
        paragraphs.append(
            Claim(
                text=f"I am applying for the {job['title']} role at {job['company']}. "
                + _sentence(top[0]["text"]),
                evidence_ids=[top[0]["id"]],
            )
        )
    if len(top) > 1:
        paragraphs.append(
            Claim(
                text=" ".join(_sentence(e["text"]) for e in top[1:]),
                evidence_ids=[e["id"] for e in top[1:]],
            )
        )
    fit = [s for s in job.get("must_have", []) if s in have][:3]
    if fit:
        ids = [e["id"] for e in evidence if set(fit) & set(e["skills"])][:3]
        paragraphs.append(
            Claim(
                text=f"I would welcome the chance to discuss how my experience with "
                f"{', '.join(fit)} fits {job['company']}.",
                evidence_ids=ids,
            )
        )
    keep = lambda cs: [c for c in cs if c.text not in rejected]  # noqa: E731
    return DraftOutput(
        cv=CVDraft(
            summary=keep(summary),
            roles=[RoleBullets(employer=r.employer, bullets=keep(r.bullets)) for r in roles],
            projects=keep(projects),
            skills=skills_list,
        ),
        letter=LetterDraft(paragraphs=keep(paragraphs)),
    )


def fake_verify(payload: dict[str, Any]) -> Entailment:
    """Token-overlap entailment: all numbers must appear; >=75% content overlap = supported."""
    claim: str = payload["claim"]
    context: str = payload.get("context", "")
    evidence: list[dict[str, Any]] = payload["evidence"]
    if not evidence:
        return Entailment(label="unsupported", reason="no evidence cited")
    ev_text = " ".join(e["text"] + " " + " ".join(e.get("skills", [])) for e in evidence)
    claim_tok = content_tokens(claim, content_tokens(context))
    ev_tok = content_tokens(ev_text)
    nums_missing = set(_NUM.findall(claim)) - set(_NUM.findall(ev_text + " " + context))
    ratio = len(claim_tok & ev_tok) / len(claim_tok) if claim_tok else 1.0
    sentences = [s for e in evidence for s in _SENT.split(e["text"])]
    quote = max(sentences, key=lambda s: len(content_tokens(s) & claim_tok), default="")
    if nums_missing:
        return Entailment(
            label="unsupported",
            quote=quote,
            reason=f"numbers not in evidence: {sorted(nums_missing)}",
        )
    if ratio >= 0.75:
        return Entailment(label="supported", quote=quote, reason=f"overlap {ratio:.2f}")
    if ratio >= 0.4:
        return Entailment(label="partial", quote=quote, reason=f"overlap {ratio:.2f}")
    missing = sorted(claim_tok - ev_tok)[:6]
    return Entailment(label="unsupported", quote=quote, reason=f"not in evidence: {missing}")


# ------------------------------------------------------------------------ research


def fake_research_step(payload: dict[str, Any], messages: Sequence[BaseMessage]) -> AIMessage:
    """Search once, fetch up to two allowed result pages, then stop."""
    company: str = payload["company"]
    allowed: list[str] = payload.get("allowed_domains", [])
    tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
    searches = [m for m in tool_msgs if m.name == "web_search"]
    step = sum(isinstance(m, AIMessage) for m in messages)
    if not searches:
        call = {
            "name": "web_search",
            "args": {"query": f"{company} engineering products"},
            "id": f"call_{step}_0",
        }
        return AIMessage(content="", tool_calls=[call])
    fetched = {
        tc["args"].get("url")
        for m in messages
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
        if tc["name"] == "fetch_page"
    }
    try:
        results = json.loads(str(searches[-1].content))
    except json.JSONDecodeError:
        results = []
    urls = [r["url"] for r in results if isinstance(r, dict) and "url" in r]
    nxt = next(
        (
            u
            for u in urls
            if (u not in fetched and any(d in u for d in allowed))
            or (u not in fetched and not allowed)
        ),
        None,
    )
    if nxt and len(fetched) < 2:
        return AIMessage(
            content="",
            tool_calls=[{"name": "fetch_page", "args": {"url": nxt}, "id": f"call_{step}_1"}],
        )
    return AIMessage(content="I have enough information.")


def fake_research_brief(payload: dict[str, Any]) -> ResearchBrief:
    """Take the first substantive sentences of each page as cited facts."""
    facts: list[ResearchFact] = []
    sources: list[SearchResult] = []
    for page in payload["pages"]:
        sents = [
            s.strip() for s in _SENT.split(re.sub(r"\s+", " ", page["text"])) if len(s.strip()) > 40
        ]
        facts += [ResearchFact(text=s, source_url=page["url"]) for s in sents[:2]]
        sources.append(
            SearchResult(
                title=page.get("title", page["url"]),
                url=page["url"],
                snippet=sents[0] if sents else "",
            )
        )
    n_src = len({f.source_url for f in facts})
    confidence = (
        "high" if len(facts) >= 3 and n_src >= 2 else "medium" if len(facts) >= 2 else "low"
    )
    summary = " ".join(" ".join(f.text for f in facts[:2]).split()[:60])
    return ResearchBrief(
        company=payload["company"],
        summary=summary or "No reliable information found.",
        facts=facts,
        sources=sources,
        confidence=confidence,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------- port


class FakeChat:
    """ChatPort implementation backed by the handlers above."""

    def __init__(
        self, tier: str, budget: Budget, skills: SkillNormalizer, fabricate_job_ids: set[str]
    ) -> None:
        self.tier, self.model, self.budget = tier, f"fake:{tier}", budget
        handlers: dict[str, Callable[[dict[str, Any]], BaseModel]] = {
            "extract_profile": lambda p: fake_extract_profile(p, skills),
            "extract_job": lambda p: fake_extract_job(p, skills),
            "match_rationale": fake_rationale,
            "draft_documents": lambda p: fake_draft(p, fabricate_job_ids),
            "verify_claim": fake_verify,
            "research_brief": fake_research_brief,
        }
        self._handlers = handlers

    def _record(self, task: str, run_id: str, inp: str, out: str) -> None:
        self.budget.record(
            run_id=run_id,
            task=task,
            tier=self.tier,
            model=self.model,
            input_tokens=_approx_tokens(inp),
            output_tokens=_approx_tokens(out),
            fake=True,
        )

    def structured[T: BaseModel](
        self,
        *,
        task: str,
        schema: type[T],
        system: str,
        prompt: str,
        payload: dict[str, Any],
        run_id: str,
    ) -> T:
        """Dispatch to the task handler and validate against schema."""
        self.budget.check(run_id)
        if task not in self._handlers:
            raise KeyError(f"fake LLM has no handler for task {task!r}")
        result = schema.model_validate(self._handlers[task](payload).model_dump())
        self._record(task, run_id, system + prompt, result.model_dump_json())
        return result

    def tool_step(
        self,
        *,
        task: str,
        system: str,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
        payload: dict[str, Any],
        run_id: str,
    ) -> AIMessage:
        """One deterministic research step."""
        self.budget.check(run_id)
        msg = fake_research_step(payload, messages)
        inp = system + "".join(str(m.content) for m in messages)
        out = json.dumps(msg.tool_calls) + str(msg.content)
        msg.usage_metadata = {
            "input_tokens": _approx_tokens(inp),
            "output_tokens": _approx_tokens(out),
            "total_tokens": _approx_tokens(inp) + _approx_tokens(out),
        }
        self._record(task, run_id, inp, out)
        return msg
