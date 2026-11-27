# ADR 0006: The LLM emits structured JSON, never LaTeX

Status: accepted (2026-11-22)

## Decision
`draft_documents` returns `DraftOutput` (claims with evidence ids). Identity facts come from
`profile.yaml`. Jinja2 templates with LaTeX-safe delimiters and mandatory escaping render the
`.tex`.

## Consequences
- No LaTeX injection, no uncompilable output from a model slip.
- Every sentence is addressable (`cv.summary.0`), verifiable and editable.
- Restyling never needs a new model call (`make render JOB=...`).
- The model cannot use custom LaTeX formatting; templates own presentation.
