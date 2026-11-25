"""Parse the user's own documents with pure Python: PDF (pypdf), Markdown/text, LaTeX."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from careergraph.domain.models import EvidenceItem, ProfileDocument

_LATEX_KEEP_ARG = re.compile(
    r"\\(?:textbf|textit|emph|underline|texttt|textsc|section\*?|subsection\*?|paragraph|"
    r"opening|closing|signature|item|href\{[^}]*\})\s*\{([^{}]*)\}"
)
_LATEX_ENV = re.compile(r"\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?")
_LATEX_CMD = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?")


def sha256(text: str) -> str:
    """Hex sha256 of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_latex(source: str) -> str:
    """Lightly strip LaTeX: drop comments, environments and commands, keep text arguments."""
    no_comments = re.sub(r"(?<!\\)%.*", "", source)
    text = _LATEX_KEEP_ARG.sub(r"\1", no_comments)
    text = _LATEX_ENV.sub("", text)
    text = _LATEX_CMD.sub("", text)
    text = text.replace("~", " ").replace(r"\\", "\n").replace("{", "").replace("}", "")
    text = re.sub(r"\\([&%$#_])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def read_pdf(path: Path) -> str:
    """Extract text from a PDF's text layer (no OCR)."""
    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()


def parse_file(path: Path) -> str:
    """Return plain text for a supported file type."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    return strip_latex(raw) if suffix == ".tex" else raw.strip()


def classify(path: Path) -> str:
    """Guess document kind from its file name."""
    name = path.stem.lower()
    if any(k in name for k in ("letter", "motivation", "cover", "anschreiben")):
        return "letter"
    if any(k in name for k in ("cv", "resume", "lebenslauf")):
        return "cv"
    return "notes"


def load_documents(folder: Path, patterns: list[str], skip: set[str]) -> list[ProfileDocument]:
    """Read every matching file in folder (non-recursive), sorted by name."""
    if not folder.exists():
        return []
    paths = sorted({p for pat in patterns for p in folder.glob(pat) if p.is_file()})
    docs: list[ProfileDocument] = []
    for path in paths:
        if path.name in skip:
            continue
        text = parse_file(path)
        if not text:
            continue
        docs.append(
            ProfileDocument(
                source_id=f"file:{path.name}",
                kind=classify(path),  # type: ignore[arg-type]
                title=path.name,
                text=text,
                content_hash=sha256(text),
                uri=str(path.name),
            )
        )
    return docs


class _EvidenceFile(BaseModel):
    items: list[EvidenceItem] = []


def load_pinned_evidence(path: Path) -> list[EvidenceItem]:
    """Load hand-edited evidence; only items marked pinned are returned.

    Raises:
        ValueError: with the file name if the file is malformed.
    """
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for i, item in enumerate(raw.get("items", []) or []):
        item.setdefault("id", f"ev-p{i + 1:03d}")
    try:
        parsed = _EvidenceFile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path.name}: invalid evidence file: {exc.errors()[0]['msg']}") from None
    return [e for e in parsed.items if e.pinned]
