"""Strict LaTeX escaping. Every value a template prints goes through `latex_escape` unless it
is explicitly marked safe (only the `url` filter does that)."""

from __future__ import annotations

import re

_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "€": r"\texteuro{}",
    "–": "--",
    "—": "---",
    "…": r"\ldots{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
}
_PATTERN = re.compile("|".join(re.escape(k) for k in _SPECIAL))
_URL_SPECIAL = re.compile(r"([%#\\{}])")


class LatexSafe(str):
    """A string already valid in LaTeX; the renderer prints it unchanged."""


def latex_escape(value: object) -> str:
    """Escape & % $ # _ { } ~ ^ \\ (and a few typographic characters) in one pass."""
    if isinstance(value, LatexSafe):
        return value
    return _PATTERN.sub(lambda m: _SPECIAL[m.group(0)], "" if value is None else str(value))


def url_escape(value: object) -> LatexSafe:
    """Escape a URL for the first argument of \\href (only % # \\ { } need it)."""
    url = str(value or "")
    if not re.match(r"^(https?://|mailto:)", url):
        url = ""
    return LatexSafe(_URL_SPECIAL.sub(r"\\\1", url))
