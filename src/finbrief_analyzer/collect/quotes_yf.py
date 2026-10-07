"""Backup quote adapter backed by yfinance, for US symbols.

It reads the same Yahoo data as the primary adapter, so it covers a broken
FinanceDataReader release, not a Yahoo outage.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from finbrief_analyzer.collect.quotes_base import Fetch, FrameQuoteProvider

SOURCE = "yfinance"

YF_TICKERS = {
    "US500": "^GSPC",
    "IXIC": "^IXIC",
    "DJI": "^DJI",
    "US10YT": "^TNX",
}


def _yf_fetch(ticker: str, start: date) -> Any:  # pragma: no cover - network
    # Imported here so that importing this module does not load pandas.
    import yfinance as yf

    return yf.Ticker(ticker).history(start=start.isoformat(), auto_adjust=False)


class YfQuoteProvider(FrameQuoteProvider):
    def __init__(self, fetch: Fetch = _yf_fetch, today: Callable[[], date] = date.today) -> None:
        super().__init__(SOURCE, fetch, today, tickers=YF_TICKERS)
