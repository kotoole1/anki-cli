"""Fixed-width terminal line helpers that are aware of SGR color escapes.

The study screens are designed for an 80-column terminal; anything that lays
text out against that budget (a right-aligned annotation, a table cell) measures
*visible* width here so coloring a word never shifts the layout.
"""

import re

LINE_WIDTH = 80

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def vis_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def pad_to(text: str, width: int) -> str:
    return text + " " * max(0, width - vis_len(text))


def ellipsize(text: str, width: int) -> str:
    """Plain text only (no escapes): cut to width with a trailing ellipsis."""
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def justify(left: str, right: str, width: int = LINE_WIDTH) -> str:
    """`left` flush left and `right` flush right on one `width`-column line.
    If they can't both fit, they are kept whole with a single space between —
    losing alignment beats losing content."""
    if not right:
        return left
    gap = max(1, width - vis_len(left) - vis_len(right))
    return f"{left}{' ' * gap}{right}"
