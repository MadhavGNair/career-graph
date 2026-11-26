# templates/

## Purpose
How your CV and cover letter look. The model never writes LaTeX; it fills these templates
with structured, verified data.

## How it works
Jinja2 with LaTeX-safe delimiters, so LaTeX braces never clash with template syntax:

| Syntax | Meaning |
|---|---|
| `((( cv.name )))` | print a value, **always LaTeX-escaped** |
| `((( link \| url )))` | print a URL for `\href{...}` (only `% # \ { }` escaped) |
| `((* for x in xs *)) ... ((* endfor *))` | statements |
| `((# comment #))` | template comment |

Undefined variables raise an error (no silent blanks).

## Variable contract
`cv` (CVData):

| Variable | Type | Source |
|---|---|---|
| `cv.name`, `cv.headline`, `cv.email`, `cv.phone`, `cv.location` | str | `profile.yaml` identity (verbatim) |
| `cv.links` | dict label -> URL | `profile.yaml` identity.links |
| `cv.summary` | list of `{text, evidence_ids}` | drafted, verified claims |
| `cv.experience` | list of `{employer, title, start, end, location, bullets[{text, evidence_ids}]}` | headers from `profile.yaml`, bullets drafted |
| `cv.projects` | list of `{text, evidence_ids}` | drafted |
| `cv.skills` | list of str | drafted (canonical names) |
| `cv.education` | list of `{institution, degree, field, start, end}` | `profile.yaml` (verbatim) |
| `cv.languages` | list of str, e.g. "German (intermediate)" | `profile.yaml` |

`letter` (LetterData):

| Variable | Type | Source |
|---|---|---|
| `letter.name`, `letter.email`, `letter.phone`, `letter.location` | str | `profile.yaml` |
| `letter.date` | str ("20 November 2026") | run date |
| `letter.company`, `letter.role` | str | posting |
| `letter.greeting`, `letter.closing` | str | defaults "Dear Hiring Team," / "Kind regards," |
| `letter.paragraphs` | list of `{text, evidence_ids}` | drafted, verified claims |

## Using your own LaTeX pattern
1. Copy `cv/default.tex.j2` to `profiles/me/templates/cv/default.tex.j2` (same for `letter/`).
2. Edit freely; use only the variables above. Escaping is automatic.
3. `make render-sample` renders sample data (with every special character) to
   `outputs/sample/` and compiles it if `tectonic` or `pdflatex` is installed.
4. `make render JOB=<id>` re-renders a saved application with your new template.

## LangGraph concepts used and why
Rendering is a deterministic node (`render_latex`) after the review pause, so a template
change never needs an LLM call: `make render JOB=...` re-renders saved drafts.

## Design decisions and trade-offs
The model emits JSON and these templates own all formatting (ADR 0006): no LaTeX injection,
no broken documents from a malformed model output, and you can restyle without re-drafting.

## Key files
`cv/default.tex.j2`, `letter/default.tex.j2`. Packages used: geometry, enumitem, hyperref,
lmodern, fontenc, inputenc (all in standard TeX distributions).

## Configuration
`TEMPLATES_DIR`, `LATEX_ENGINE`, `LATEX_TIMEOUT_SECONDS`.

## How to test
`uv run pytest tests/test_latex.py`. Compilation was not verified in development (no engine
installed); see `src/careergraph/latex/README.md`.

## Gotchas
- Do not print evidence ids in a CV meant for employers; they are for verification and appear
  in `report.md`.
- Keep `\usepackage` lists short: tectonic downloads packages on first use.
