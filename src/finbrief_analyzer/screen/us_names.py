"""Korean display names for US stocks, from Naver's exchange listings.

Unofficial endpoint. Eight pages per exchange covered 500 of the 503 S&P 500 members
on 2026-10-08; the rest keep the English name from the index listing.
"""

import httpx

from finbrief_analyzer.collect.models import CollectError

SOURCE = "naver-us-names"
URL = "https://api.stock.naver.com/stock/exchange/{exchange}/marketValue"
EXCHANGES = ("NASDAQ", "NYSE")
PAGE_SIZE = 100
DEFAULT_PAGES = 8
HEADERS = {"User-Agent": "Mozilla/5.0"}


class NaverUsNames:
    def __init__(self, client: httpx.Client, pages: int = DEFAULT_PAGES) -> None:
        self._client = client
        self._pages = pages

    def fetch(self) -> dict[str, str]:
        """Ticker -> Korean name for the largest listings. Raises CollectError on failure."""
        names: dict[str, str] = {}
        for exchange in EXCHANGES:
            for page in range(1, self._pages + 1):
                for stock in self._page(exchange, page):
                    symbol, name = stock.get("symbolCode"), stock.get("stockName")
                    if symbol and name:
                        # "BRK B" here, "BRK-B" at Yahoo.
                        names.setdefault(symbol.replace(" ", "-").replace(".", "-"), name)
        return names

    def _page(self, exchange: str, page: int) -> list[dict[str, str]]:
        try:
            response = self._client.get(
                URL.format(exchange=exchange),
                params={"page": page, "pageSize": PAGE_SIZE},
                headers=HEADERS,
            )
            response.raise_for_status()
            stocks = response.json()["stocks"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            detail = f"{exchange} page {page}: {type(error).__name__}"
            raise CollectError(SOURCE, detail) from error
        if not isinstance(stocks, list):
            raise CollectError(SOURCE, f"{exchange} page {page}: unexpected body")
        return stocks
