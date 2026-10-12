import httpx
import pytest

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.screen.us_names import NaverUsNames


def _names(
    stocks: dict[str, list[dict[str, str]]], pages: int = 1
) -> tuple[dict[str, str], list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        exchange = request.url.path.split("/")[-2]
        first_page = request.url.params["page"] == "1"
        return httpx.Response(200, json={"stocks": stocks.get(exchange, []) if first_page else []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NaverUsNames(client, pages=pages).fetch(), seen


def test_korean_names_are_keyed_by_ticker() -> None:
    # given
    stocks = {
        "NASDAQ": [{"symbolCode": "NVDA", "stockName": "엔비디아"}],
        "NYSE": [{"symbolCode": "MDT", "stockName": "메드트로닉"}],
    }

    # when
    names, _ = _names(stocks)

    # then
    assert names == {"NVDA": "엔비디아", "MDT": "메드트로닉"}


def test_share_class_ticker_is_written_the_way_yahoo_writes_it() -> None:
    # given: the listing writes the class after a space
    stocks = {"NYSE": [{"symbolCode": "BRK B", "stockName": "버크셔 해서웨이 Class B"}]}

    # when
    names, _ = _names(stocks)

    # then
    assert names == {"BRK-B": "버크셔 해서웨이 Class B"}


def test_every_page_of_both_exchanges_is_requested() -> None:
    # given / when
    _, seen = _names({}, pages=3)

    # then
    asked = sorted(
        (request.url.path.split("/")[-2], request.url.params["page"]) for request in seen
    )
    assert asked == [(exchange, str(page)) for exchange in ("NASDAQ", "NYSE") for page in (1, 2, 3)]


def test_row_without_a_name_is_skipped() -> None:
    # given
    stocks = {"NASDAQ": [{"symbolCode": "AAPL"}, {"symbolCode": "NVDA", "stockName": "엔비디아"}]}

    # when
    names, _ = _names(stocks)

    # then
    assert names == {"NVDA": "엔비디아"}


def test_http_error_becomes_a_collect_error() -> None:
    # given
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))

    # when / then
    with pytest.raises(CollectError, match="naver-us-names"):
        NaverUsNames(client, pages=1).fetch()
