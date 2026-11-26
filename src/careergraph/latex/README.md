# latex/

## Purpose
Turn `CVData`/`LetterData` into `.tex` safely and compile to PDF when an engine exists.

## How it works
Jinja2 with LaTeX-safe delimiters (`((( var )))`, `((* stmt *))`, `((# note #))`) and
`finalize=latex_escape`, so **every printed value is escaped** (`& % $ # _ { } ~ ^ \` plus a
few typographic characters). Only the `url` filter returns pre-escaped text (for `\href`).
`StrictUndefined` makes a typo in a template fail loudly. Compilation runs
`tectonic --untrusted -o DIR file.tex` or `pdflatex -no-shell-escape -halt-on-error`; with
no engine the `.tex` files are written and the report says so.

## Key files
`escape.py`, `render.py` (env, template lookup, `write_and_compile`), `compile.py`,
`sample.py` (sample data with every special character).

## LangGraph concepts used and why
Called by the deterministic `render_latex` node.

## Configuration
`LATEX_ENGINE` (auto/tectonic/pdflatex/none), `LATEX_TIMEOUT_SECONDS`, `TEMPLATES_DIR`;
user templates in `<documents dir>/templates/` override the shipped ones.

## How to test
`uv run pytest tests/test_latex.py` (golden files in `tests/golden/`; regenerate with
`UPDATE_GOLDEN=1` after an intentional template change). `make render-sample`.

## Verification status
Tectonic V1 CLI flags were checked against the Tectonic book. **No LaTeX engine was installed
in the development environment**, so PDF compilation of the default templates is
**unverified**; the compile test skips cleanly when no engine is found.

## Design decisions and trade-offs
Escaping in `finalize` (not per-variable filters) means a template author cannot forget it.
The trade-off: templates cannot inject raw LaTeX through variables, which is the point.

## Extending and gotchas
Keep templates to widely available packages (article, geometry, enumitem, hyperref, lmodern).
