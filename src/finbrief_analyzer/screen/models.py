"""Domain types for stock screening: daily bars and the universe they are screened from."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Exchange(StrEnum):
    """Which slice of the universe a stock belongs to."""

    KOSPI = "kospi"
    KOSDAQ = "kosdaq"
    SP500 = "sp500"


@dataclass(frozen=True, slots=True)
class Bar:
    """One completed trading day of one stock.

    Close and volume are what the rules use. Open, high and low come with the first
    load only; the daily ranking snapshot does not carry them.
    """

    symbol: str
    day: date
    close: float
    volume: int
    open: float | None = None
    high: float | None = None
    low: float | None = None


@dataclass(frozen=True, slots=True)
class Member:
    exchange: Exchange
    symbol: str
    name: str


class Rule(StrEnum):
    HIGH_52W = "high_52w"
    VOLUME_SPIKE = "volume_spike"


@dataclass(frozen=True, slots=True)
class ScreenHit:
    """One stock that met a rule, with what the briefing needs to show it."""

    symbol: str
    name: str
    close: float
    change_pct: float | None
    score: float


@dataclass(frozen=True, slots=True)
class ScreenResult:
    """The stocks of one exchange group that met one rule on one trading day."""

    rule: Rule
    exchanges: tuple[Exchange, ...]
    as_of: date
    hits: tuple[ScreenHit, ...]
