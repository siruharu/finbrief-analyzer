"""Backup quote adapter backed by yfinance, for everything but the Korean indices.

It reads the same Yahoo data as the primary adapter, so it covers a broken
FinanceDataReader release, not a Yahoo outage.
"""

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from finbrief_analyzer.collect.quotes_base import Fetch, FrameQuoteProvider

SOURCE = "yfinance"

YF_TICKERS = {
    "US500": "^GSPC",
    "IXIC": "^IXIC",
    "DJI": "^DJI",
    "^SOX": "^SOX",
    "^RUT": "^RUT",
    "^VIX": "^VIX",
    "^N225": "^N225",
    "SSEC": "000001.SS",
    "^HSI": "^HSI",
    "US10YT": "^TNX",
    "DX-Y.NYB": "DX-Y.NYB",
    "USD/JPY": "JPY=X",
    "JPY/KRW": "JPYKRW=X",
    "EUR/USD": "EURUSD=X",
    "CL=F": "CL=F",
    "GC=F": "GC=F",
    "HG=F": "HG=F",
    "BTC/USD": "BTC-USD",
}


# A plain US ticker such as NVDA or BRK-B is already what Yahoo calls it. Korean stock
# codes are six digits and would need a .KS or .KQ suffix, so they do not match.
_US_TICKER = re.compile(r"[A-Z]{1,5}(-[A-Z])?")


def _yf_fetch(ticker: str, start: date) -> Any:  # pragma: no cover - network
    # Imported here so that importing this module does not load pandas.
    import yfinance as yf

    return yf.Ticker(ticker).history(start=start.isoformat(), auto_adjust=False)


class YfQuoteProvider(FrameQuoteProvider):
    def __init__(self, fetch: Fetch = _yf_fetch, today: Callable[[], date] = date.today) -> None:
        super().__init__(SOURCE, fetch, today, tickers=YF_TICKERS)

    def supports(self, symbol: str) -> bool:
        return symbol in YF_TICKERS or _US_TICKER.fullmatch(symbol) is not None
