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
