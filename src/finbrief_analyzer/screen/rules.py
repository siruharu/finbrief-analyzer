"""Screening rules as pure functions over daily bars. No database, no network, no pandas.

A rule returns None when it has no opinion (too little history, no trading); such a
stock is left out of the ranking instead of being scored zero.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from finbrief_analyzer.screen.models import Bar

HIGH_WINDOW = timedelta(weeks=52)
# How late the first bar may start and still count as "a full 52 weeks of history".
HIGH_SLACK = timedelta(days=10)
VOLUME_WINDOW = 20


@dataclass(frozen=True, slots=True)
class Score:
    symbol: str
    score: float
    # Move of the last day in percent; used to order stocks with the same score.
    change_pct: float | None


def _ordered(bars: Iterable[Bar]) -> list[Bar]:
    return sorted(bars, key=lambda bar: bar.day)


def high_ratio(bars: Iterable[Bar]) -> float | None:
    """Last close over the highest close of the past 52 weeks (George & Hwang 2004).

    Closing prices, not intraday highs. A stock listed less than 52 weeks ago has no
    score: its all-time high is not a 52-week high.
    """
    ordered = _ordered(bars)
    if not ordered:
        return None
    start = ordered[-1].day - HIGH_WINDOW
    if ordered[0].day > start + HIGH_SLACK:
        return None
    highest = max(bar.close for bar in ordered if bar.day >= start)
    return ordered[-1].close / highest if highest > 0 else None


def _before_last(bars: Iterable[Bar]) -> tuple[Sequence[Bar], Bar] | None:
    """The VOLUME_WINDOW bars before the last one, and the last one."""
    ordered = _ordered(bars)
    if len(ordered) <= VOLUME_WINDOW:
        return None
    return ordered[-VOLUME_WINDOW - 1 : -1], ordered[-1]


def volume_ratio(bars: Iterable[Bar]) -> float | None:
    """Last day's volume over the average of the 20 days before it.

    The last day is not part of the average, or a spike would dilute itself.
    """
    split = _before_last(bars)
    if split is None:
        return None
    window, last = split
    average = sum(bar.volume for bar in window) / len(window)
    return last.volume / average if average > 0 else None


def trading_value(bars: Iterable[Bar]) -> float | None:
    """Average of close x volume over the 20 days before the last, in the quote currency."""
    split = _before_last(bars)
    if split is None:
        return None
    window, _ = split
    return sum(bar.close * bar.volume for bar in window) / len(window)


def change_pct(bars: Iterable[Bar]) -> float | None:
    ordered = _ordered(bars)
    if len(ordered) < 2 or ordered[-2].close == 0:
        return None
    return (ordered[-1].close - ordered[-2].close) / ordered[-2].close * 100


def rank(scores: Iterable[Score], top: int) -> list[Score]:
    """Best `top` scores. Ties: larger move of the day first, then symbol, so it is stable."""

    def key(score: Score) -> tuple[float, float, str]:
        move = float("-inf") if score.change_pct is None else score.change_pct
        return (-score.score, -move, score.symbol)

    return sorted(scores, key=key)[:top]
