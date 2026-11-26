# profiles/

## Purpose
Where your private documents live. `profiles/me/` is **gitignored** (and a CI guard fails if
anything under it is ever tracked). `profiles/example/` is a template you copy with `make init`.

## How it works
`ingest_profile` reads every file in `documents.dir` (from `config/profile.yaml`) matching
`documents.include`: PDF via pypdf, Markdown/text as-is, LaTeX with light command stripping.
`extract_profile` turns them into evidence items (`ev-001`, ...) with skills and source refs.
Identity facts (name, contact, employers, degrees, dates) never come from the LLM: they come
from `config/profile.yaml` verbatim.

## Key files
| Path | What |
|---|---|
| `example/cv.md` | CV skeleton showing the section headings extraction understands |
| `example/evidence.yaml` | hand-editable evidence; `pinned: true` items are never overwritten |
| `example/templates/` | put `cv/default.tex.j2` / `letter/default.tex.j2` here to override `templates/` |
| `me/` | your real files (gitignored) |

## LangGraph concepts used and why
`ingest_profile` hashes these files; a conditional edge skips `extract_profile` when nothing
changed and a cached extraction exists (no LLM cost on repeat runs).

## Configuration
`config/profile.yaml` `documents.dir`, `documents.include`, `documents.evidence_file`,
`github.*`.

## How to test
`make profile` prints every extracted evidence item; `uv run pytest tests/test_profile.py`.

## evidence.yaml
Add facts the extractor missed or phrase them exactly as you want them cited. Pinned items are
merged into every extraction and keep their ids. Fields: `id` (optional, `ev-pNNN` style),
`kind` (experience, project, education, achievement, publication), `text`, `skills`,
`source_ref`, `dates`, `pinned`.

## Design decisions
- Plain files over a database for your source of truth: easy to back up, diff and edit.
- Pinned evidence lets you correct the model without fighting it on every run.

## Gotchas
- Scanned PDFs without a text layer yield no text (no OCR). Export your CV to Markdown or text.
- Re-extraction only happens when a document's content hash changes (`make profile` forces it).
