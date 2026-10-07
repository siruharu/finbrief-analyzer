import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.collect.news_dart import DartNewsProvider
from finbrief_analyzer.collect.ports import NewsProvider

KEY = "dartSECRETkey0123456789abcdef0123456789"
KST = timezone(timedelta(hours=9))
SINCE = datetime(2026, 10, 7, 9, 0, tzinfo=KST)
FIXTURES = Path(__file__).parent / "fixtures"

Handler = Callable[[httpx.Request], httpx.Response]


def _load(name: str) -> dict[str, Any]:
    # Any: JSON document.
    loaded: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return loaded


LISTING = _load("dart_list.json")
EMPTY = _load("dart_empty.json")
LIMIT = _load("dart_limit.json")
BAD_KEY = {"status": "010", "message": "등록되지 않은 인증키입니다."}


def _provider(handler: Handler) -> DartNewsProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return DartNewsProvider(client, SecretStr(KEY))


def _serving(body: object) -> Handler:
    return lambda request: httpx.Response(200, json=body)


def test_filing_becomes_news_item_titled_with_company_and_report_name() -> None:
    # given
    provider = _provider(_serving(LISTING))

    # when
    items = provider.get_news(SINCE)

    # then: trailing blanks in the report name are trimmed
    titles = [i.title for i in items]
    assert "씨에스윈드 주요사항보고서(자기주식처분결정)" in titles
    assert "SK디앤디 [기재정정]주요사항보고서(유상증자결정)" in titles
    assert all(i.source == "dart" and i.summary is None for i in items)


def test_link_is_the_filing_viewer_address_built_from_the_receipt_number() -> None:
    # given
    provider = _provider(_serving(LISTING))

    # when
    item = next(i for i in provider.get_news(SINCE) if i.title.startswith("씨에스윈드"))

    # then
    assert item.link == "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261007000347"


def test_published_at_is_midnight_kst_of_the_receipt_date() -> None:
    # given: the API gives a date and no time
    provider = _provider(_serving(LISTING))

    # when
    items = provider.get_news(SINCE)

    # then
    assert {i.published_at for i in items} == {datetime(2026, 10, 7, 0, 0, tzinfo=KST)}


def test_since_is_compared_by_kst_date_so_same_day_filings_are_kept() -> None:
    # given: since is 09:00 but filings are stamped 00:00 of the same day
    provider = _provider(_serving(LISTING))

    # when
    items = provider.get_news(SINCE)

    # then: the three filings of 10-07 stay, the one of 10-06 goes
    assert len(items) == 3


def test_since_given_in_utc_is_converted_to_the_kst_date() -> None:
    # given: 16:00 UTC on 10-06 is already 01:00 on 10-07 in Korea
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=LISTING)

    # when
    items = _provider(handler).get_news(datetime(2026, 10, 6, 16, 0, tzinfo=UTC))

    # then
    assert seen[0].params["bgn_de"] == "20261007"
    assert len(items) == 3


def test_request_is_narrowed_to_major_reports_of_kospi_companies() -> None:
    # given: unfiltered, a day has ~450 filings, mostly fund prospectuses (PoC)
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=EMPTY)

    # when
    _provider(handler).get_news(SINCE)

    # then
    params = seen[0].params
    assert params["pblntf_ty"] == "B"
    assert params["corp_cls"] == "Y"
    assert params["page_count"] == "100"


def test_filings_are_returned_latest_receipt_first() -> None:
    # given
    provider = _provider(_serving(LISTING))

    # when
    links = [i.link[-14:] for i in provider.get_news(SINCE)]

    # then
    assert links == ["20261007000347", "20261007000206", "20261007000004"]


def test_no_result_code_means_an_empty_list() -> None:
    # given: status 013 arrives with HTTP 200
    provider = _provider(_serving(EMPTY))

    # when / then
    assert provider.get_news(SINCE) == []


def test_quota_exceeded_code_raises_collect_error() -> None:
    # given
    provider = _provider(_serving(LIMIT))

    # when / then
    with pytest.raises(CollectError, match="020"):
        provider.get_news(SINCE)


def test_other_error_code_raises_collect_error_with_code_and_message() -> None:
    # given
    provider = _provider(_serving(BAD_KEY))

    # when
    with pytest.raises(CollectError) as caught:
        provider.get_news(SINCE)

    # then
    assert "010" in str(caught.value)
    assert "등록되지 않은 인증키입니다." in str(caught.value)


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda request: httpx.Response(500), id="http-500"),
        pytest.param(lambda request: httpx.Response(200, text="<html>"), id="not-json"),
        pytest.param(_serving([1, 2]), id="wrong-shape"),
        pytest.param(_serving({"status": "000"}), id="no-list"),
        pytest.param(_serving(BAD_KEY), id="bad-key"),
        pytest.param(_serving({"status": "800", "message": f"echo {KEY}"}), id="key-echoed"),
    ],
)
def test_api_key_never_reaches_the_error_or_the_log(
    handler: Handler, caplog: pytest.LogCaptureFixture
) -> None:
    # given: the key travels as a query parameter
    provider = _provider(handler)

    # when
    with caplog.at_level(logging.DEBUG), pytest.raises(CollectError) as caught:
        provider.get_news(SINCE)

    # then
    assert KEY not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert KEY not in caplog.text


def test_timeout_is_translated_to_collect_error() -> None:
    # given
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timed out: {request.url}")

    # when
    with pytest.raises(CollectError) as caught:
        _provider(handler).get_news(SINCE)

    # then
    assert "ReadTimeout" in str(caught.value)
    assert KEY not in str(caught.value)


def test_unusable_filings_are_dropped() -> None:
    # given
    good = LISTING["list"][1]
    rows = [
        good,
        {**good, "rcept_no": "../../evil?x=1"},
        {**good, "rcept_no": "20261007000999", "rcept_dt": "notadate"},
        {**good, "rcept_no": "20261007000998", "corp_name": "", "report_nm": " "},
        "not an object",
    ]
    provider = _provider(_serving({"status": "000", "list": rows}))

    # when
    items = provider.get_news(SINCE)

    # then: bad receipt number, unreadable date, no title
    assert [i.link[-14:] for i in items] == ["20261007000347"]


def test_provider_satisfies_the_news_port() -> None:
    # given / when
    provider: NewsProvider = _provider(_serving(EMPTY))

    # then
    assert provider.name == "dart"
