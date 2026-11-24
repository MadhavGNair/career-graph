# skills/

## Purpose
Deterministic skill normalisation: `py`, `Python3` and `python` count as one skill, and a
related skill (PyTorch vs TensorFlow) earns partial credit in matching. No LLM involved.

## How it works
`SkillNormalizer` builds an alias map from `config/skills.yaml` and one compiled regex over all
aliases (longest first, whole-word boundaries that treat `+` and `#` as word characters so
`C++` and `C#` work). Terms of two letters or fewer (`Go`, `ML`, `TF`) only match when not
written in lowercase, so the English word "go" is not the Go language.

## Key files
`normalize.py`: `normalize`, `normalize_all`, `find_in_text`, `related`.

## LangGraph concepts used and why
None directly. It runs inside `extract_profile`, `extract_jobs` and `match_jobs` so that LLM
output (live) and keyword extraction (demo) land on the same canonical names.

## Configuration
`config/skills.yaml` (`aliases`, `related`) and `criteria.yaml` `related_skill_credit`.

## How to test
`uv run pytest tests/test_skills.py`.

## Design decisions and trade-offs
A hand-maintained alias list beats embeddings here: it is predictable, explainable in the
score breakdown and free. The cost is maintenance; unknown skills pass through lowercased.

## Extending and gotchas
- Keep canonical names lowercase. Add aliases, do not add duplicate canonical entries.
- `related` is one hop and not automatically symmetric; list both directions if you want both.
