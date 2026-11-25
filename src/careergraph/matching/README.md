# matching/

## Purpose
Deterministic, explainable job scoring (the "workflow, not agent" half of matching; see
ADR 0005) and the shortlist interrupt payload.

## How it works
```
score = 100 * sum(w_i * c_i) + clip(preference_points, +-max_adjustment), clipped to 0..100
```
| Criterion | c_i in [0,1] |
|---|---|
| `must_have` | share of required skills with evidence; related skill = `related_skill_credit` |
| `nice_to_have` | same for bonus skills (neutral 0.5 when none listed) |
| `semantic` | mean cosine of the top-3 evidence items vs the posting (hybrid index) |
| `title` | half best overlap with `search.yaml` include keywords, half overlap with your headline |
| `seniority` | 1 in `target_seniority`, 0.5 one level away or unknown, else 0 |
| `location` | remote 1.0; hybrid/on-site in your home city 1.0/0.8; elsewhere 0.6/0.4; unknown 0.5 |
| `language` | lowest of your levels for required languages (fluent 1, intermediate 0.5, basic 0.25) |
| `salary` | 1 above floor, 0 below, 0.5 unknown/no floor/other currency (never penalised) |

Dealbreakers (excluded companies/keywords, missing required language, salary below floor
when enforced) remove a job regardless of score. The shortlist keeps dealbreaker-free jobs
with `score >= threshold`, best `top_n`, and never re-asks about jobs you already approved or
rejected (deferred ones can return).

## Key files
`scoring.py` (criteria, dealbreakers, `score_job`, `shortlist`), `payload.py` (interrupt
rows, resume validation: unknown ids dropped, unanswered jobs deferred).

## LangGraph concepts used and why
`match_jobs` is a plain node; its output feeds `human_shortlist`'s `interrupt()` payload. The
learned preferences come from the LangGraph **Store** (`runtime.store`), i.e. long-term memory
that outlives any single thread.

## Configuration
`config/criteria.yaml` (everything above), `ENABLE_MATCH_RATIONALE` (one cheap call per
shortlisted job; off = deterministic rationale).

## How to test
`uv run pytest tests/test_matching.py`. Inspect a real ranking with `make jobs`.

## Design decisions and trade-offs
An LLM is not needed to compare skill lists, and a deterministic score is reproducible,
debuggable and free. Semantic similarity covers what keyword skills miss. The cost: the score
is only as good as the extracted skills and your weights; the breakdown is shown so you can
tune `criteria.yaml`.

## Extending and gotchas
Add a criterion: a weight in `Weights` + YAML (with comment), a function here, an entry in
`score_job`. The drift guard will remind you to document it.
