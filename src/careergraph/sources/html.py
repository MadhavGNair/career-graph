"""Minimal HTML to text (stdlib only). Keeps hidden text on purpose: injection payloads often
hide in display:none blocks, and the scanner must see them."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK = {"p", "div", "br", "ul", "ol", "tr", "table", "section", "article", "header",
          "footer", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}  # fmt: skip
_SKIP = {"script", "style", "noscript", "template"}


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        # Comments are kept as text so injection hidden in comments is visible to the scanner.
        self.parts.append(f"\n{data}\n")


def html_to_text(markup: str, unescape_first: bool = False) -> str:
    """Convert HTML to readable text with one item per line.

    Args:
        markup: HTML source.
        unescape_first: Greenhouse returns entity-escaped HTML; unescape it before parsing.
    """
    if unescape_first:
        markup = html.unescape(markup)
    parser = _TextParser()
    parser.feed(markup)
    parser.close()
    text = "".join(parser.parts)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def html_title(markup: str) -> str:
    """Extract the <title> text."""
    parser = _TextParser()
    parser.feed(markup)
    return parser.title.strip()
