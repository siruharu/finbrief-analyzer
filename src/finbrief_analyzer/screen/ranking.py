"""Naver's market-value ranking: the Korean universe and each day's close and volume.

Unofficial endpoint, confirmed in docs/01_research/2026-10-08_screening-poc.md. The
KRX listing that FinanceDataReader wraps returns no prices without a login.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.screen.models import Exchange

logger = logging.getLogger(__name__)

SOURCE = "naver-ranking"
URL = "https://m.stock.naver.com/api/stocks/marketValue/{exchange}"
PAGE_SIZE = 100
EXCHANGE_CODES = {Exchange.KOSPI: "KOSPI", Exchange.KOSDAQ: "KOSDAQ"}


@dataclass(frozen=True, slots=True)
class RankRow:
    code: str
    name: str
    # "stock", "etf" or "etn".
    kind: str
    close: float
    prev_close: float
    volume: int
    market_value: int
    traded_on: date
    market_status: str


def _parse(raw: dict[str, str]) -> RankRow:
    close = float(raw["closePriceRaw"])
    return RankRow(
        code=raw["itemCode"],
        name=raw["stockName"],
        kind=raw["stockEndType"],
        close=close,
        prev_close=close - float(raw["compareToPreviousClosePriceRaw"]),
        volume=int(raw["accumulatedTradingVolumeRaw"]),
        market_value=int(raw["marketValueRaw"]),
        traded_on=datetime.fromisoformat(raw["localTradedAt"]).date(),
        market_status=raw["marketStatus"],
    )


class NaverRanking:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def fetch(self, exchange: Exchange, pages: int) -> list[RankRow]:
        """The top `pages` x 100 listings, largest first. Raises CollectError on failure."""
        by_code: dict[str, RankRow] = {}
        for page in range(1, pages + 1):
            for raw in self._page(exchange, page):
                try:
                    parsed = _parse(raw)
                except (KeyError, ValueError, TypeError):
                    # A newly listed stock has "-" for a price until its first trade.
                    logger.debug("ranking row skipped: %s", raw.get("itemCode"))
                    continue
                # The ranking moves while pages are fetched, so a stock can show up twice.
                by_code.setdefault(parsed.code, parsed)
        # The endpoint is close to sorted, not strictly sorted.
        return sorted(by_code.values(), key=lambda row: (-row.market_value, row.code))

    def _page(self, exchange: Exchange, page: int) -> list[dict[str, str]]:
        url = URL.format(exchange=EXCHANGE_CODES[exchange])
        try:
            response = self._client.get(url, params={"page": page, "pageSize": PAGE_SIZE})
            response.raise_for_status()
            stocks = response.json()["stocks"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            detail = f"{exchange.value} page {page}: {type(error).__name__}"
            raise CollectError(SOURCE, detail) from error
        if not isinstance(stocks, list):
            raise CollectError(SOURCE, f"{exchange.value} page {page}: unexpected body")
        return stocks
