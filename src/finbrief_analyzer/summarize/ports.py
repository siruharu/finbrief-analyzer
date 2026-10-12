"""The interface the briefing job depends on; the Claude adapter is one implementation."""

from collections.abc import Sequence
from typing import Protocol

from finbrief_analyzer.collect.models import NewsItem, Slot
from finbrief_analyzer.summarize.models import NewsDigest


class Summarizer(Protocol):
    def summarize(self, news: Sequence[NewsItem], slot: Slot) -> NewsDigest | None:
        """Choose and summarise. None means "no digest this time"; it never raises for the API."""
        ...
