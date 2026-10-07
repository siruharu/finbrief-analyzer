"""Quote adapter backed by FinanceDataReader.

Every default symbol resolves to Yahoo behind this library, see
docs/01_research/2026-10-07_data-source-poc.md.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Any

from finbrief_analyzer.collect.models import CollectError, Quote

logger = logging.getLogger(__name__)

SOURCE = "fdr"
# Long enough that a holiday week still leaves a previous close in the window.
LOOKBACK_DAYS = 10

# Any: the result is a pandas DataFrame and pandas ships no type stubs.
Fetch = Callable[[str, date], Any]


def _fdr_fetch(symbol: str, start: date) -> Any:  # pragma: no cover - network
    # Imported here so that importing this module does not load pandas.
    import FinanceDataReader as fdr

    return fdr.DataReader(symbol, start.isoformat())


class FdrQuoteProvider:
    name = SOURCE

    def __init__(self, fetch: Fetch = _fdr_fetch, today: Callable[[], date] = date.today) -> None:
        self._fetch = fetch
        self._today = today

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        """Return quotes for the symbols that have data; raise only if none has."""
        start = self._today() - timedelta(days=LOOKBACK_DAYS)
        quotes: list[Quote] = []
        last_error: CollectError | None = None
        for symbol in symbols:
            try:
                quotes.append(self._get_one(symbol, start))
            except CollectError as error:
                logger.warning("quote skipped: %s", error)
                last_error = error
        if last_error is not None and not quotes:
            raise last_error
        return quotes

    def _get_one(self, symbol: str, start: date) -> Quote:
        try:
            frame = self._fetch(symbol, start)
        except Exception as error:
            detail = f"{symbol}: fetch failed ({type(error).__name__}: {error})"
            raise CollectError(SOURCE, detail) from error
        return _to_quote(symbol, frame, start)


def _to_quote(symbol: str, frame: Any, not_before: date) -> Quote:
    """Turn the table into a Quote. No pandas value leaves this function."""
    if "Close" not in frame.columns:
        raise CollectError(SOURCE, f"{symbol}: no Close column")
    # Unfinished rows come back with a NaN close.
    closes = frame["Close"].dropna()
    if len(closes) == 0:
        raise CollectError(SOURCE, f"{symbol}: no data")
    stamp = closes.index[-1]
    as_of = date(stamp.year, stamp.month, stamp.day)
    if as_of < not_before:
        # The source answered without error but stopped updating.
        raise CollectError(SOURCE, f"{symbol}: stale data, last row is {as_of}")
    prev_close = float(closes.iloc[-2]) if len(closes) > 1 else None
    return Quote(symbol=symbol, close=float(closes.iloc[-1]), as_of=as_of, prev_close=prev_close)
