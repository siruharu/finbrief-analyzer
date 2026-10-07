from collections.abc import Callable
from datetime import date

import httpx
import pandas as pd
import pytest

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.collect.ports import QuoteProvider
from finbrief_analyzer.collect.quotes_naver import NaverQuoteProvider
from finbrief_analyzer.collect.quotes_yf import YfQuoteProvider

TODAY = date(2026, 10, 7)

# Body copied from the PoC: a JavaScript array literal, not JSON.
NAVER_BODY = """[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],
\t\t ["20261002", 6938.27, 7011.04, 6927.88, 7003.74, 239009, 0.0],
\t\t ["20261006", 7044.67, 7044.67, 6897.38, 6941.39, 269831, 0.0],
\t\t ["20261007", 6864.25, 6977.77, 6803.81, 6803.9, 256760, 0.0]
\t  ]"""


def _yf_frame(rows: dict[str, float]) -> pd.DataFrame:
    """Build a table shaped like yfinance history(): timezone-aware index."""
    index = pd.DatetimeIndex(list(rows), tz="America/New_York")
    return pd.DataFrame({"Close": list(rows.values()), "Dividends": 0.0}, index=index)


def _yf(fetch: Callable[[str, date], object]) -> YfQuoteProvider:
    return YfQuoteProvider(fetch=fetch, today=lambda: TODAY)


def _naver(handler: Callable[[httpx.Request], httpx.Response]) -> NaverQuoteProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NaverQuoteProvider(client=client, today=lambda: TODAY)


def test_yf_asks_yahoo_for_its_own_ticker_but_keeps_the_internal_symbol() -> None:
    # given
    asked: list[str] = []

    def fetch(ticker: str, start: date) -> object:
        asked.append(ticker)
        return _yf_frame({"2026-10-05": 7773.95, "2026-10-06": 7818.93})

    # when
    (quote,) = _yf(fetch).get_quotes(["US500"])

    # then
    assert asked == ["^GSPC"]
    assert quote.symbol == "US500"
    assert quote.close == pytest.approx(7818.93)
    assert quote.prev_close == pytest.approx(7773.95)


def test_yf_uses_the_market_local_date_of_a_timezone_aware_index() -> None:
    # given: midnight New York time is already the next day in UTC+9
    provider = _yf(lambda ticker, start: _yf_frame({"2026-10-06": 7818.93}))

    # when
    (quote,) = provider.get_quotes(["US500"])

    # then
    assert quote.as_of == date(2026, 10, 6)


def test_yf_supports_us_symbols_only() -> None:
    # given
    provider = _yf(lambda ticker, start: _yf_frame({}))

    # when / then
    assert provider.supports("IXIC")
    assert provider.supports("US10YT")
    assert not provider.supports("^KS11")


def test_yf_does_not_fetch_an_unsupported_symbol() -> None:
    # given
    asked: list[str] = []

    def fetch(ticker: str, start: date) -> object:
        asked.append(ticker)
        return _yf_frame({"2026-10-06": 1.0})

    # when
    quotes = _yf(fetch).get_quotes(["^KS11", "DJI"])

    # then
    assert asked == ["^DJI"]
    assert [q.symbol for q in quotes] == ["DJI"]


def test_yf_translates_a_blocked_response_to_collect_error() -> None:
    # given: yfinance raises its own error type when Yahoo rate-limits
    def fetch(ticker: str, start: date) -> object:
        raise RuntimeError("Too Many Requests. Rate limited.")

    # when
    with pytest.raises(CollectError) as caught:
        _yf(fetch).get_quotes(["IXIC"])

    # then
    assert caught.value.source == "yfinance"
    assert "Rate limited" in str(caught.value)


def test_naver_parses_close_and_prev_close_from_the_array_body() -> None:
    # given
    provider = _naver(lambda request: httpx.Response(200, text=NAVER_BODY))

    # when
    (quote,) = provider.get_quotes(["^KS11"])

    # then
    assert quote.symbol == "^KS11"
    assert quote.close == pytest.approx(6803.9)
    assert quote.prev_close == pytest.approx(6941.39)
    assert quote.as_of == date(2026, 10, 7)


def test_naver_requests_its_own_code_for_the_lookback_window() -> None:
    # given
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, text=NAVER_BODY)

    # when
    _naver(handler).get_quotes(["^KQ11"])

    # then
    params = seen[0].params
    assert params["symbol"] == "KOSDAQ"
    assert params["startTime"] == "20260927"
    assert params["endTime"] == "20261007"
    assert params["timeframe"] == "day"


def test_naver_supports_kr_indices_only() -> None:
    # given
    provider = _naver(lambda request: httpx.Response(200, text=NAVER_BODY))

    # when / then
    assert provider.supports("^KS11")
    assert provider.supports("^KQ11")
    assert not provider.supports("IXIC")


def test_naver_does_not_request_an_unsupported_symbol() -> None:
    # given
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, text=NAVER_BODY)

    # when
    quotes = _naver(handler).get_quotes(["IXIC", "^KS11"])

    # then
    assert len(seen) == 1
    assert [q.symbol for q in quotes] == ["^KS11"]


def test_naver_http_error_is_translated_to_collect_error() -> None:
    # given
    provider = _naver(lambda request: httpx.Response(503))

    # when / then
    with pytest.raises(CollectError, match="naver"):
        provider.get_quotes(["^KS11"])


def test_naver_network_error_is_translated_to_collect_error() -> None:
    # given
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    # when / then
    with pytest.raises(CollectError, match="ConnectTimeout"):
        _naver(handler).get_quotes(["^KS11"])


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("<html>blocked</html>", id="html"),
        pytest.param("[]", id="empty-array"),
        pytest.param("[['date', 'close'], ['20261007', 1.0]]", id="unknown-headers"),
        pytest.param("__import__('os').system('echo hacked')", id="code"),
        pytest.param("[" * 5000, id="deep-nesting"),
        pytest.param("{'날짜': 1, '종가': 2}", id="not-a-list"),
        pytest.param("[1, 2]", id="rows-not-lists"),
        pytest.param("[" + "1," * 20_000 + "]", id="too-large"),
    ],
)
def test_naver_unexpected_body_is_rejected_without_being_executed(body: str) -> None:
    # given: an unofficial endpoint can change shape at any time
    provider = _naver(lambda request: httpx.Response(200, text=body))

    # when / then
    with pytest.raises(CollectError):
        provider.get_quotes(["^KS11"])


def test_naver_header_only_body_means_no_data() -> None:
    # given: a window with no trading day
    body = "[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율']]"
    provider = _naver(lambda request: httpx.Response(200, text=body))

    # when / then
    with pytest.raises(CollectError, match="no data"):
        provider.get_quotes(["^KS11"])


def test_naver_skips_rows_it_cannot_read() -> None:
    # given
    body = """[['날짜', '시가', '고가', '저가', '종가'],
    ["20261006", 1.0, 1.0, 1.0, 6941.39],
    ["notadate", 1.0, 1.0, 1.0, 1.0],
    ["20261007", 1.0, 1.0, 1.0, None]]"""
    provider = _naver(lambda request: httpx.Response(200, text=body))

    # when
    (quote,) = provider.get_quotes(["^KS11"])

    # then
    assert quote.as_of == date(2026, 10, 6)
    assert quote.close == pytest.approx(6941.39)


def test_both_backups_satisfy_the_quote_port() -> None:
    # given / when
    providers: list[QuoteProvider] = [
        _yf(lambda ticker, start: _yf_frame({})),
        _naver(lambda request: httpx.Response(200, text=NAVER_BODY)),
    ]

    # then
    assert [p.name for p in providers] == ["yfinance", "naver"]
