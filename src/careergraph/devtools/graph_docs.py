"""Generate Mermaid diagrams from the compiled graphs into READMEs (`make docs-graphs`).

Each diagram lives between markers `<!-- graph:<name>:start -->` and `<!-- graph:<name>:end -->`.
`--check` exits non-zero when a README is stale (used by CI).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from careergraph.config import REPO_ROOT

GRAPH_README = REPO_ROOT / "src" / "careergraph" / "graphs" / "job_search" / "README.md"


def _builders() -> dict[str, Callable[[], Any]]:
    from careergraph.graphs.job_search.graph import build_job_search_graph
    from careergraph.graphs.job_search.subgraphs.document_factory import build_document_factory
    from careergraph.graphs.job_search.subgraphs.research_company import build_research_company

    return {
        "job_search": build_job_search_graph,
        "document_factory": build_document_factory,
        "research_company": build_research_company,
    }


TARGETS: list[tuple[Path, list[str]]] = [
    (GRAPH_README, ["job_search", "document_factory", "research_company"]),
    (REPO_ROOT / "README.md", ["job_search"]),
]


def mermaid(name: str) -> str:
    """Mermaid source for one graph (compiled without persistence; purely structural)."""
    return _builders()[name]().compile().get_graph().draw_mermaid().strip()


def render_block(name: str) -> str:
    """The marker-delimited block for a README."""
    return (
        f"<!-- graph:{name}:start -->\n```mermaid\n{mermaid(name)}\n```\n<!-- graph:{name}:end -->"
    )


def sync(check: bool) -> list[str]:
    """Update (or check) every target; return the stale files."""
    stale: list[str] = []
    for path, names in TARGETS:
        text = path.read_text(encoding="utf-8")
        new = text
        for name in names:
            pattern = re.compile(rf"<!-- graph:{name}:start -->.*?<!-- graph:{name}:end -->", re.S)
            if not pattern.search(new):
                raise SystemExit(f"{path}: missing markers for graph {name!r}")
            new = pattern.sub(lambda _m, n=name: render_block(n), new)
        if new != text:
            stale.append(str(path.relative_to(REPO_ROOT)))
            if not check:
                path.write_text(new, encoding="utf-8")
    return stale


def main(argv: list[str] | None = None) -> int:
    """CLI: `python -m careergraph.devtools.graph_docs [--check]`."""
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    stale = sync(check)
    if check and stale:
        print("stale graph diagrams (run `make docs-graphs`): " + ", ".join(stale))
        return 1
    print("graph diagrams " + ("up to date" if not stale else "updated: " + ", ".join(stale)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
