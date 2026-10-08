"""Rules shared by the quote adapters: per-symbol collection and rows-to-Quote."""

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from finbrief_analyzer.collect.models import CollectError, Quote

logger = logging.getLogger(__name__)

# Long enough that a holiday week still leaves a previous close in the window.
LOOKBACK_DAYS = 10

Row = tuple[date, float]
# Any: the result is a pandas DataFrame and pandas ships no type stubs.
Fetch = Callable[[str, date], Any]


def window_start(today: date) -> date:
    return today - timedelta(days=LOOKBACK_DAYS)


def collect_each(symbols: Sequence[str], get_one: Callable[[str], Quote]) -> list[Quote]:
    """Return quotes for the symbols that have data; raise only if none has."""
    quotes: list[Quote] = []
    last_error: CollectError | None = None
    for symbol in symbols:
        try:
            quotes.append(get_one(symbol))
        except CollectError as error:
            logger.warning("quote skipped: %s", error)
            last_error = error
    if last_error is not None and not quotes:
        raise last_error
    return quotes


def quote_from_rows(source: str, symbol: str, rows: Sequence[Row], not_before: date) -> Quote:
    """Last valid row is the close, the one before it the previous close."""
    # Unfinished rows come back with a NaN close.
    valid = sorted(row for row in rows if math.isfinite(row[1]))
    if not valid:
        raise CollectError(source, f"{symbol}: no data")
    as_of, close = valid[-1]
    if as_of < not_before:
        # The source answered without error but stopped updating.
        raise CollectError(source, f"{symbol}: stale data, last row is {as_of}")
    prev_close = valid[-2][1] if len(valid) > 1 else None
    return Quote(symbol=symbol, close=close, as_of=as_of, prev_close=prev_close)


def frame_rows(source: str, symbol: str, frame: Any) -> list[Row]:
    """Read (trading day, close) pairs out of a table. No pandas value leaves this function."""
    if "Close" not in frame.columns:
        raise CollectError(source, f"{symbol}: no Close column")
    # The index holds the market-local trading day, with or without a timezone.
    return [
        (date(stamp.year, stamp.month, stamp.day), float(close))
        for stamp, close in frame["Close"].items()
    ]


class FrameQuoteProvider:
    """Quote provider over a library that returns one price table per ticker."""

    def __init__(
        self,
        name: str,
        fetch: Fetch,
        today: Callable[[], date],
        tickers: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self._fetch = fetch
        self._today = today
        # Internal symbol -> the library's ticker. None means symbols are passed through.
        self._tickers = tickers

    def supports(self, symbol: str) -> bool:
        return self._tickers is None or symbol in self._tickers

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        start = window_start(self._today())
        return collect_each(symbols, lambda symbol: self._get_one(symbol, start))

    def _get_one(self, symbol: str, start: date) -> Quote:
        if not self.supports(symbol):
            raise CollectError(self.name, f"{symbol}: unsupported symbol")
        ticker = symbol if self._tickers is None else self._tickers.get(symbol, symbol)
        try:
            frame = self._fetch(ticker, start)
        except Exception as error:
            detail = f"{symbol}: fetch failed ({type(error).__name__}: {error})"
            raise CollectError(self.name, detail) from error
        return quote_from_rows(self.name, symbol, frame_rows(self.name, symbol, frame), start)
