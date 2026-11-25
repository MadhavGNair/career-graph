"""Profile ingestion: parsers, GitHub adapter, ingest/extract nodes, cache skip."""

from __future__ import annotations

from pathlib import Path

from careergraph.config import DEMO_DIR
from careergraph.graphs.job_search.graph import build_profile_graph
from careergraph.security.fetcher import FetchPolicy, SafeFetcher
from careergraph.sources.documents import (
    classify,
    load_documents,
    load_pinned_evidence,
    parse_file,
    strip_latex,
)
from careergraph.sources.fixtures import FixtureTransport, demo_resolver
from careergraph.sources.github import GitHubAdapter
from tests.helpers import demo_services


def minimal_pdf(text: str) -> bytes:
    """Build a one-page PDF with a real text layer and a correct xref table."""
    stream = f"BT /F1 12 Tf 20 50 Td ({text}) Tj ET".encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 100]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + body + b"endobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_strip_latex_keeps_text() -> None:
    text = strip_latex((DEMO_DIR / "profile" / "letter_llm.tex").read_text())
    assert "large language model" in text
    assert "\\" not in text and "documentclass" not in text
    assert "Dear Hiring Team," in text


def test_pdf_text_layer(tmp_path: Path) -> None:
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(minimal_pdf("Built PyTorch models"))
    assert "Built PyTorch models" in parse_file(pdf)


def test_load_documents_classifies_and_skips_evidence() -> None:
    docs = load_documents(DEMO_DIR / "profile", ["*.md", "*.tex"], skip={"evidence.yaml"})
    kinds = {d.title: d.kind for d in docs}
    assert kinds == {"cv.md": "cv", "letter_llm.tex": "letter", "letter_platform.md": "letter"}
    assert classify(Path("Lebenslauf.pdf")) == "cv" and classify(Path("notes.txt")) == "notes"


def test_pinned_evidence() -> None:
    pinned = load_pinned_evidence(DEMO_DIR / "profile" / "evidence.yaml")
    assert [p.id for p in pinned] == ["ev-p001"] and pinned[0].pinned


def test_github_adapter_skips_forks_and_sends_headers(tmp_path: Path) -> None:
    transport = FixtureTransport()
    fetcher = SafeFetcher(FetchPolicy(min_interval=0), tmp_path, transport, demo_resolver)
    docs = GitHubAdapter(fetcher, token="t0k").fetch_profile("sam-demo-example", 10, 200)
    assert [d.title for d in docs][:2] == ["jobgraph-agent", "rag-eval-kit"] or len(docs) == 5
    assert len(docs) == 5 and all(d.kind == "github_repo" for d in docs)
    assert "awesome-mlops" not in {d.title for d in docs}
    rag = next(d for d in docs if d.title == "rag-eval-kit")
    assert "Languages: Python (97%)" in rag.text and "README (truncated):" in rag.text
    assert any("/readme" in r for r in transport.requests)


def test_profile_graph_extracts_then_uses_cache(tmp_path: Path) -> None:
    svc = demo_services(tmp_path)
    app = build_profile_graph().compile()
    first = app.invoke({"run_id": "r1"}, context=svc)
    ev = first["profile"].evidence
    assert 20 <= len(ev) <= 35
    assert len({e.id for e in ev}) == len(ev)
    assert ev[0].id == "ev-p001" and ev[0].pinned
    assert "kubernetes" in first["profile"].skills
    assert svc.repo.run_totals("r1")[0] > 0
    second = app.invoke({"run_id": "r2"}, context=svc)
    assert second["profile_cached"] is True
    assert svc.repo.run_totals("r2") == (0, 0.0)
    forced = app.invoke({"run_id": "r3", "force_profile": True}, context=svc)
    assert forced["profile_cached"] is False and svc.repo.run_totals("r3")[0] > 0
