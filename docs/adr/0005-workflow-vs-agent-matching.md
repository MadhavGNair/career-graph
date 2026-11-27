# ADR 0005: Matching is a workflow, not an agent

Status: accepted (2026-11-22)

## Context
Matching could be "ask an LLM how well this job fits". That is costly per posting,
non-deterministic, hard to explain and open to prompt injection from the posting.

## Decision
Deterministic scoring with user-editable weights (`criteria.yaml`): skill coverage with
related-skill partial credit, hybrid semantic similarity, title, seniority, location,
language, salary, dealbreakers, plus learned preference adjustments from tagged decisions.
The LLM is used only to extract structured requirements (once per posting, cached by hash)
and, optionally, to phrase a two-sentence rationale.

## Consequences
Cheap, reproducible, explainable (breakdown shown in the UI), evaluable (`eval --suite
match`). Quality depends on extraction and weights, which the user can tune.
