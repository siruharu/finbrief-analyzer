"""Turn collected news into the text the model reads, and map its answer back.

The model picks items by number and never sees a URL, so it cannot invent a link.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from finbrief_analyzer.collect.models import NewsItem

# Yonhap leads open with "(서울=연합뉴스) 홍길동 기자 = ", which says nothing about the story.
BYLINE = re.compile(r"^\([^)]*연합뉴스\)\s*[^=]*=\s*")


@dataclass(frozen=True, slots=True)
class Candidate:
    """A news item under the number the model will use to refer to it."""

    index: int
    news: NewsItem


def strip_byline(text: str) -> str:
    return BYLINE.sub("", text).strip()


def candidates(news: Sequence[NewsItem]) -> tuple[Candidate, ...]:
    """Number the items from 1, in the order they arrive (newest first)."""
    return tuple(Candidate(index, item) for index, item in enumerate(news, start=1))


def render_input(found: Sequence[Candidate]) -> str:
    """One line per item: [n] (source) title — lead. The lead is left out when there is none."""
    return "\n".join(_render_line(candidate) for candidate in found)


def _render_line(candidate: Candidate) -> str:
    item = candidate.news
    line = f"[{candidate.index}] ({item.source}) {item.title}"
    lead = strip_byline(item.summary) if item.summary else ""
    return f"{line} — {lead}" if lead else line


def resolve(found: Sequence[Candidate], index: int) -> NewsItem | None:
    """The item behind a number the model returned, or None for a number it made up."""
    for candidate in found:
        if candidate.index == index:
            return candidate.news
    return None
