"""Text cleanup shared by the news adapters."""

import html
import re

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain_text(text: str) -> str:
    """Remove tags, decode entities and collapse whitespace. Output is plain text, not safe HTML."""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()
