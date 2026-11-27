# evals/

## Purpose
Measure the four places where CareerGraph can be wrong: matching, extraction, verification
and injection detection. **Fake-mode evals verify pipeline logic, not model quality.**

## How it works
| Suite | Gold data (`data/demo/evals/`) | Metrics |
|---|---|---|
| `match` | `triage_labels.yaml` (hand-labelled approve/reject per fixture posting) | precision and recall at the shortlist, ranking AUC (approve vs reject) |
| `extraction` | `expected_skills.yaml` (hand-written must/nice skills per posting) | micro precision/recall/F1 of skills |
| `verifier` | `seeded_claims.yaml` (claims incl. seeded fabrications, with their evidence) | label accuracy, fabricated-claim recall |
| `injection` | `injection.yaml` (3 injected postings) | precision, recall of the heuristic scanner |

Each run writes `OUTPUT_DIR/evals/eval-<mode>-<timestamp>.{md,json}`. Fake mode is gated by
`thresholds.yaml` (CI fails below a gate); live mode is never gated.

```bash
make eval                                    # all suites, fake mode (CI gate)
careergraph eval run --suite verifier --mode live   # real models on the fixtures (costs tokens)
careergraph eval export-labels               # your own approve/reject decisions -> YAML
careergraph eval run --suite match --labels outputs/evals/my_labels.yaml  # offline re-score
```

## Results
Fake mode, measured 2026-11-22 (plumbing checks only): match precision 0.750, recall 0.545,
AUC 0.864; extraction F1 1.000; verifier accuracy 1.000, fabricated recall 1.000; injection
precision 1.000, recall 1.000. The extraction and verifier numbers are 1.0 because the fake
model and the gold files were written together; they prove the plumbing, not quality.

**Live mode: not yet measured.** To measure: set `ANTHROPIC_API_KEY`, then
`careergraph eval run --suite all --mode live` (or the `live-eval` workflow), and keep the
reports to compare models, prompts and criteria over time.

## Key files
`suites.py`, `report.py`.

## LangGraph concepts used and why
The match suite runs the real `jobs` graph (nodes 1-5) on fixtures in a temp workspace, so it
tests routing and Send fan-out too; extraction and verifier call the same prompts and schemas
as the nodes.

## Configuration
`thresholds.yaml`; live mode uses `CHEAP_MODEL` and the budget caps.

## How to run and test
`uv run pytest tests/test_evals.py`.

## Design decisions and trade-offs
Small, hand-labelled, fictional gold sets: cheap to run and safe to publish, but too small for
statistically strong claims. Export your own labels to evaluate criteria on your real data
(the export contains personal data; keep it out of git, `outputs/` is ignored).

## Extending and gotchas
Add a case to the gold YAML (or the specs in `build_fixtures.py`), re-run `make eval`, and only
raise a threshold after measuring.
