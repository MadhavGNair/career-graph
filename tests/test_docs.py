"""Documentation guards: generated diagrams are fresh; documented directories have READMEs."""

from __future__ import annotations

import pytest

from careergraph.config import REPO_ROOT
from careergraph.devtools.graph_docs import sync

README_DIRS = [
    ".", "config", "profiles", "templates", "data/demo", "ui", "tests", "deploy",
    "deploy/helm/careergraph", "deploy/argocd", "deploy/k3s", ".github",
    "src/careergraph/service", "src/careergraph/domain", "src/careergraph/llm",
    "src/careergraph/skills", "src/careergraph/retrieval", "src/careergraph/memory",
    "src/careergraph/security", "src/careergraph/sources", "src/careergraph/latex",
    "src/careergraph/persistence", "src/careergraph/graphs/job_search",
    "src/careergraph/graphs/job_search/nodes", "src/careergraph/graphs/job_search/subgraphs", "src/careergraph/graphs/tracker",
    "src/careergraph/evals",
]  # fmt: skip
# Directories documented in later phases (P6 ui/tests, P7 evals/.github, P8 deploy).
# PLAN.md P10 requires this to be empty.
PENDING: set[str] = set()
SECTIONS = ["Purpose", "How it works", "Key files", "LangGraph concepts", "Configuration",
            "test", "Design decisions", "Gotchas"]  # fmt: skip


def test_graph_diagrams_are_fresh() -> None:
    assert sync(check=True) == [], "run `make docs-graphs`"


@pytest.mark.parametrize("folder", README_DIRS)
def test_documented_directory_has_complete_readme(folder: str) -> None:
    readme = REPO_ROOT / folder / "README.md"
    if folder in PENDING and not readme.exists():
        pytest.skip("documented in a later phase")
    if not readme.exists():
        pytest.fail(f"missing {folder}/README.md")
    if folder == ".":
        return
    text = readme.read_text().lower()
    missing = [s for s in SECTIONS if s.lower() not in text]
    assert missing == [], f"{folder}/README.md lacks sections: {missing}"
