"""What the summarising step produces."""

from dataclasses import dataclass

from finbrief_analyzer.collect.models import NewsItem


@dataclass(frozen=True, slots=True)
class DigestItem:
    """One chosen news item and the one-line Korean summary written for it."""

    news: NewsItem
    line: str


@dataclass(frozen=True, slots=True)
class NewsDigest:
    """The items chosen for one briefing, in the order the model gave them."""

    items: tuple[DigestItem, ...]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
