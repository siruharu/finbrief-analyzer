"""Provider interfaces. Adapters satisfy these structurally; nothing here does I/O."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from finbrief_analyzer.collect.models import NewsItem, Quote


class QuoteProvider(Protocol):
    @property
    def name(self) -> str:
        """Source name recorded in MarketSnapshot.missing when this provider fails."""
        ...

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        """Return quotes for the symbols that have data. Raises CollectError on failure."""
        ...


class RateProvider(Protocol):
    @property
    def name(self) -> str: ...

    def get_rates(self) -> Sequence[Quote]:
        """Return the provider's configured rates. Raises CollectError on failure."""
        ...


class NewsProvider(Protocol):
    @property
    def name(self) -> str: ...

    def get_news(self, since: datetime) -> Sequence[NewsItem]:
        """Return items published at or after `since`. Raises CollectError on failure."""
        ...
