"""Domain types shared by every collector adapter and the snapshot assembly."""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Slot(StrEnum):
    """Which briefing is being prepared."""

    KR_OPEN = "kr_open"
    US_OPEN = "us_open"


class Market(StrEnum):
    KR = "kr"
    US = "us"
    FX = "fx"
    RATE = "rate"


class CollectError(Exception):
    """A source failed; adapters translate library and HTTP errors into this."""

    def __init__(self, source: str, message: str) -> None:
        super().__init__(f"{source}: {message}")
        self.source = source


@dataclass(frozen=True, slots=True)
class Quote:
    """Closing value of an index, exchange rate or yield on one trading day."""

    symbol: str
    close: float
    as_of: date
    prev_close: float | None = None
    # Display label and market. Adapters know symbols only; the assembly fills these in.
    name: str = ""
    market: Market | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.close):
            raise ValueError(f"close must be a finite number: {self.symbol}")

    @property
    def change(self) -> float | None:
        """Change from the previous close in the quoted unit, or None if unknown."""
        if self.prev_close is None or math.isnan(self.prev_close):
            return None
        return self.close - self.prev_close

    @property
    def change_pct(self) -> float | None:
        """Change from the previous close in percent, or None if unknown.

        Meant for indices and exchange rates. For a rate, use change_bp instead.
        """
        if self.change is None or self.prev_close == 0 or self.prev_close is None:
            return None
        return self.change / self.prev_close * 100

    @property
    def change_bp(self) -> float | None:
        """Change in basis points, for values quoted in percent (Market.RATE)."""
        return None if self.change is None else self.change * 100


@dataclass(frozen=True, slots=True)
class NewsItem:
    """One article or filing. Identity is the link, so duplicates across feeds collapse."""

    title: str = field(compare=False)
    link: str
    source: str = field(compare=False)
    published_at: datetime = field(compare=False)
    summary: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.published_at.utcoffset() is None:
            raise ValueError(f"published_at must have a timezone: {self.link}")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Everything collected for one slot. Empty quotes or news is still a valid value."""

    slot: Slot
    quotes: tuple[Quote, ...] = ()
    news: tuple[NewsItem, ...] = ()
    # Names of sources that failed, in the order they were tried.
    missing: tuple[str, ...] = ()
    closed_markets: frozenset[Market] = frozenset()

    def is_closed(self, market: Market) -> bool:
        return market in self.closed_markets
