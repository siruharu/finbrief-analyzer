from datetime import date

import httpx
import pytest

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.screen.models import Exchange
from finbrief_analyzer.screen.ranking import NaverRanking, RankRow


def row(
    code: str,
    name: str,
    value: int,
    kind: str = "stock",
    close: int = 1000,
    change: int = -50,
    volume: int = 12345,
) -> dict[str, str]:
    """One stock as the ranking endpoint returns it (only the fields that are read)."""
    return {
        "itemCode": code,
        "stockName": name,
        "stockEndType": kind,
        "closePriceRaw": str(close),
        "compareToPreviousClosePriceRaw": str(change),
        "accumulatedTradingVolumeRaw": str(volume),
        "marketValueRaw": str(value),
        "localTradedAt": "2026-10-07T15:30:00+09:00",
        "marketStatus": "CLOSE",
    }


def _ranking(pages: dict[int, list[dict[str, str]]]) -> tuple[NaverRanking, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"stocks": pages.get(page, [])})

    return NaverRanking(httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_row_is_parsed_into_numbers_and_the_trading_day() -> None:
    # given
    ranking, _ = _ranking({1: [row("005930", "삼성전자", 1_559_000, close=266750, change=-1750)]})

    # when
    (found,) = ranking.fetch(Exchange.KOSPI, pages=1)

    # then
    assert found == RankRow(
        code="005930",
        name="삼성전자",
        kind="stock",
        close=266750.0,
        prev_close=268500.0,
        volume=12345,
        market_value=1_559_000,
        traded_on=date(2026, 10, 7),
        market_status="CLOSE",
    )


def test_each_page_is_requested_for_the_exchange() -> None:
    # given
    ranking, seen = _ranking({1: [row("000001", "가", 3)], 2: [row("000002", "나", 2)]})

    # when
    ranking.fetch(Exchange.KOSDAQ, pages=2)

    # then
    assert [request.url.path for request in seen] == ["/api/stocks/marketValue/KOSDAQ"] * 2
    assert [request.url.params["page"] for request in seen] == ["1", "2"]
    assert seen[0].url.params["pageSize"] == "100"


def test_rows_are_sorted_by_market_value_whatever_order_they_arrive_in() -> None:
    # given: the endpoint is not strictly sorted
    ranking, _ = _ranking(
        {1: [row("000002", "나", 5), row("000001", "가", 9), row("000003", "다", 7)]}
    )

    # when
    found = ranking.fetch(Exchange.KOSPI, pages=1)

    # then
    assert [r.code for r in found] == ["000001", "000003", "000002"]


def test_stock_appearing_on_two_pages_is_kept_once() -> None:
    # given: the ranking moved between two page requests
    ranking, _ = _ranking(
        {1: [row("000001", "가", 9)], 2: [row("000001", "가", 9), row("000002", "나", 5)]}
    )

    # when
    found = ranking.fetch(Exchange.KOSPI, pages=2)

    # then
    assert [r.code for r in found] == ["000001", "000002"]


def test_row_that_cannot_be_read_is_skipped() -> None:
    # given: a row without a price, as for a newly listed stock before its first trade
    broken = row("000009", "신규", 1) | {"closePriceRaw": "-"}
    ranking, _ = _ranking({1: [broken, row("000001", "가", 9)]})

    # when
    found = ranking.fetch(Exchange.KOSPI, pages=1)

    # then
    assert [r.code for r in found] == ["000001"]


def test_http_error_becomes_a_collect_error() -> None:
    # given
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))

    # when / then
    with pytest.raises(CollectError, match="naver-ranking"):
        NaverRanking(client).fetch(Exchange.KOSPI, pages=1)


def test_unexpected_body_becomes_a_collect_error() -> None:
    # given: an HTML error page with status 200
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html>"))
    )

    # when / then
    with pytest.raises(CollectError, match="naver-ranking"):
        NaverRanking(client).fetch(Exchange.KOSPI, pages=1)
