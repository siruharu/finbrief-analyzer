"""Korean rates and the USD/KRW base rate from the Bank of Korea ECOS API.

ECOS puts the API key in the URL path and reports errors with HTTP 200, see
docs/01_research/2026-10-07_data-source-poc.md.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from finbrief_analyzer.collect.models import CollectError, Quote
from finbrief_analyzer.collect.quotes_base import Row, collect_each, quote_from_rows, window_start
from finbrief_analyzer.collect.redact import hide_from_http_log

SOURCE = "ecos"
BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
NO_DATA_CODE = "INFO-200"
# A ten-day daily window never comes close to this.
MAX_ROWS = 100


@dataclass(frozen=True, slots=True)
class EcosSeries:
    symbol: str
    stat_code: str
    item_code: str


DEFAULT_SERIES = (
    EcosSeries(symbol="KR_BASE_RATE", stat_code="722Y001", item_code="0101000"),
    EcosSeries(symbol="KR3YT", stat_code="817Y002", item_code="010200000"),
    EcosSeries(symbol="KR10YT", stat_code="817Y002", item_code="010210000"),
    EcosSeries(symbol="USD/KRW", stat_code="731Y001", item_code="0000001"),
)


class EcosRateProvider:
    name = SOURCE

    def __init__(
        self,
        client: httpx.Client,
        api_key: SecretStr,
        today: Callable[[], date] = date.today,
        series: Sequence[EcosSeries] = DEFAULT_SERIES,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._today = today
        self._series = {s.symbol: s for s in series}
        hide_from_http_log(api_key)

    def get_rates(self) -> Sequence[Quote]:
        """Return a quote per configured series that has data; raise only if none has."""
        today = self._today()
        return collect_each(list(self._series), lambda symbol: self._get_one(symbol, today))

    def _get_one(self, symbol: str, today: date) -> Quote:
        series = self._series[symbol]
        start = window_start(today)
        payload = self._request(series, start, today)
        return quote_from_rows(SOURCE, symbol, _parse(symbol, payload), start)

    def _request(self, series: EcosSeries, start: date, end: date) -> Any:
        """Fetch one series. Any: the decoded JSON document, validated in _parse."""
        url = (
            f"{BASE_URL}/{self._api_key.get_secret_value()}/json/kr/1/{MAX_ROWS}"
            f"/{series.stat_code}/D/{start:%Y%m%d}/{end:%Y%m%d}/{series.item_code}"
        )
        try:
            response = self._client.get(url)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            reason = type(error).__name__
        # Raised outside the except block on purpose: the original error quotes the URL,
        # the key is in the URL, and a chained exception would carry it into the logs.
        raise CollectError(SOURCE, f"{series.symbol}: request failed ({reason})")


def _parse(symbol: str, payload: Any) -> list[Row]:
    """Read (day, value) pairs. Any: external JSON; every access below is checked."""
    if not isinstance(payload, dict):
        raise CollectError(SOURCE, f"{symbol}: unexpected response layout")
    result = payload.get("RESULT")
    if isinstance(result, dict):
        code = str(result.get("CODE"))
        detail = "no data" if code == NO_DATA_CODE else f"rejected with {code}"
        raise CollectError(SOURCE, f"{symbol}: {detail}")
    search = payload.get("StatisticSearch")
    records = search.get("row") if isinstance(search, dict) else None
    if not isinstance(records, list):
        raise CollectError(SOURCE, f"{symbol}: unexpected response layout")
    rows: list[Row] = []
    for record in records:
        try:
            day = datetime.strptime(str(record["TIME"]), "%Y%m%d").date()
            rows.append((day, float(record["DATA_VALUE"])))
        except (KeyError, TypeError, ValueError):
            continue
    return rows
