"""Backup quote adapter for Korean indices, backed by Naver's chart endpoint.

The endpoint is unofficial and can change shape without notice. It is the only
source found that is independent of Yahoo and has the same-day close.
"""

import ast
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

import httpx

from finbrief_analyzer.collect.models import CollectError, Quote
from finbrief_analyzer.collect.quotes_base import Row, collect_each, quote_from_rows, window_start

SOURCE = "naver"
URL = "https://fchart.stock.naver.com/siseJson.nhn"
# Ten daily rows are a few hundred bytes; anything far larger is not the expected answer.
MAX_BODY_CHARS = 20_000
DAY_HEADER = "날짜"
CLOSE_HEADER = "종가"

NAVER_CODES = {
    "^KS11": "KOSPI",
    "^KQ11": "KOSDAQ",
}


class NaverQuoteProvider:
    name = SOURCE

    def __init__(self, client: httpx.Client, today: Callable[[], date] = date.today) -> None:
        self._client = client
        self._today = today

    def supports(self, symbol: str) -> bool:
        return symbol in NAVER_CODES

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        today = self._today()
        return collect_each(symbols, lambda symbol: self._get_one(symbol, today))

    def _get_one(self, symbol: str, today: date) -> Quote:
        if not self.supports(symbol):
            raise CollectError(SOURCE, f"{symbol}: unsupported symbol")
        start = window_start(today)
        params = {
            "symbol": NAVER_CODES[symbol],
            "requestType": "1",
            "startTime": start.strftime("%Y%m%d"),
            "endTime": today.strftime("%Y%m%d"),
            "timeframe": "day",
        }
        try:
            response = self._client.get(URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            detail = f"{symbol}: request failed ({type(error).__name__})"
            raise CollectError(SOURCE, detail) from error
        return quote_from_rows(SOURCE, symbol, _parse_rows(symbol, response.text), start)


def _parse_rows(symbol: str, body: str) -> list[Row]:
    table = _parse_table(symbol, body)
    header = table[0]
    day_at, close_at = header.index(DAY_HEADER), header.index(CLOSE_HEADER)
    rows: list[Row] = []
    for record in table[1:]:
        try:
            day = datetime.strptime(str(record[day_at]), "%Y%m%d").date()
            rows.append((day, float(record[close_at])))
        except (ValueError, TypeError, IndexError):
            continue
    return rows


def _parse_table(symbol: str, body: str) -> list[list[Any]]:
    """Parse the body, a JavaScript array literal with single-quoted headers (not JSON).

    Any: cell values come from an external literal; _parse_rows converts or skips them.
    """
    if len(body) > MAX_BODY_CHARS:
        raise CollectError(SOURCE, f"{symbol}: response too large")
    try:
        # literal_eval accepts literals only; it never calls or imports anything.
        table = ast.literal_eval(body.strip())
    except (ValueError, SyntaxError, MemoryError, RecursionError) as error:
        raise CollectError(SOURCE, f"{symbol}: unreadable response") from error
    if not isinstance(table, list) or not all(isinstance(row, list) for row in table):
        raise CollectError(SOURCE, f"{symbol}: unexpected response layout")
    if not table or DAY_HEADER not in table[0] or CLOSE_HEADER not in table[0]:
        raise CollectError(SOURCE, f"{symbol}: unexpected response layout")
    return table
