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
from finbrief_analyzer.collect.news_marketaux import MarketauxNewsProvider
from finbrief_analyzer.collect.ports import NewsProvider

TOKEN = "tok-SECRET-0123456789"
SINCE = datetime(2026, 10, 7, 5, 0, tzinfo=timezone(timedelta(hours=9)))
# Any: JSON documents.
PAGE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "marketaux_page.json").read_text(encoding="utf-8")
)
EMPTY = {"meta": {"found": 0, "returned": 0, "limit": 3, "page": 1}, "data": []}
BAD_TOKEN = {
    "error": {"code": "invalid_api_token", "message": "An invalid API token was supplied."}
}

Handler = Callable[[httpx.Request], httpx.Response]


def _article(n: int) -> dict[str, Any]:
    return {
        "title": f"article {n}",
        "description": f"description {n}",
        "url": f"https://example.com/{n}",
        "published_at": f"2026-10-07T06:{n:02d}:00.000000Z",
        "source": "example.com",
    }


def _provider(handler: Handler, max_calls: int = 3) -> MarketauxNewsProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return MarketauxNewsProvider(client, SecretStr(TOKEN), max_calls=max_calls)


def _pages(*pages: httpx.Response) -> tuple[Handler, list[httpx.Request]]:
    """Serve the given responses in order and record the requests."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return pages[len(seen) - 1]

    return handler, seen


def test_articles_become_news_items() -> None:
    # given
    handler, _ = _pages(httpx.Response(200, json=PAGE))

    # when
    items = _provider(handler, max_calls=1).get_news(SINCE)

    # then
    first = items[0]
    assert first.title.startswith("Marvell Technology, Inc. (MRVL)")
    assert first.link.startswith("https://seekingalpha.com/article/4952406")
    assert first.source == "seekingalpha.com"
    assert first.published_at == datetime(2026, 10, 7, 6, 33, 6, tzinfo=UTC)
    assert first.summary == (
        "2026-10-07. The following slide deck was published by Marvell Technology, Inc."
    )


def test_summary_comes_from_description_never_from_the_unreliable_snippet() -> None:
    # given: the snippet field carried anti-bot boilerplate in the PoC
    handler, _ = _pages(httpx.Response(200, json=PAGE))

    # when
    items = _provider(handler, max_calls=1).get_news(SINCE)

    # then
    assert items[1].summary == "Stocks rose even as Treasury yields climbed."
    assert items[2].summary is None
    assert all("Javascript" not in (i.summary or "") for i in items)


def test_request_asks_for_us_english_news_since_the_given_instant_in_utc() -> None:
    # given
    handler, seen = _pages(httpx.Response(200, json=EMPTY))

    # when
    _provider(handler).get_news(SINCE)

    # then: 05:00 KST is 20:00 UTC the day before
    params = seen[0].url.params
    assert params["language"] == "en"
    assert params["countries"] == "us"
    assert params["published_after"] == "2026-10-06T20:00"
    assert params["page"] == "1"


def test_pages_are_requested_only_up_to_the_call_limit() -> None:
    # given: an API that always has more
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(request.url.params["page"])
        return httpx.Response(200, json={"data": [_article(page)]})

    # when
    items = _provider(handler, max_calls=2).get_news(SINCE)

    # then
    assert seen == ["1", "2"]
    assert len(items) == 2


def test_rate_limit_response_stops_and_returns_what_was_collected() -> None:
    # given
    handler, seen = _pages(
        httpx.Response(200, json={"data": [_article(1)]}),
        httpx.Response(429, json={"error": {"code": "usage_limit_reached"}}),
        httpx.Response(200, json={"data": [_article(3)]}),
    )

    # when
    items = _provider(handler, max_calls=3).get_news(SINCE)

    # then
    assert len(seen) == 2
    assert [i.title for i in items] == ["article 1"]


def test_timeout_on_a_later_page_is_not_retried() -> None:
    # given: a timed-out request still costs quota (seen in the PoC)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, json={"data": [_article(calls)]})

    # when
    items = _provider(handler, max_calls=5).get_news(SINCE)

    # then
    assert calls == 2
    assert len(items) == 1


def test_auth_failure_on_the_first_call_raises_collect_error() -> None:
    # given
    handler, seen = _pages(httpx.Response(401, json=BAD_TOKEN))

    # when / then
    with pytest.raises(CollectError, match="401"):
        _provider(handler).get_news(SINCE)
    assert len(seen) == 1


def test_empty_page_ends_the_paging() -> None:
    # given
    handler, seen = _pages(
        httpx.Response(200, json={"data": [_article(1)]}),
        httpx.Response(200, json=EMPTY),
        httpx.Response(200, json={"data": [_article(3)]}),
    )

    # when
    items = _provider(handler, max_calls=3).get_news(SINCE)

    # then
    assert len(seen) == 2
    assert len(items) == 1


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(httpx.Response(401, json=BAD_TOKEN), id="http-401"),
        pytest.param(httpx.Response(200, text="<html>"), id="not-json"),
        pytest.param(httpx.Response(200, json=[1]), id="wrong-shape"),
        pytest.param(None, id="timeout"),
    ],
)
def test_token_never_reaches_the_error_or_the_log(
    response: httpx.Response | None, caplog: pytest.LogCaptureFixture
) -> None:
    # given: the token travels as a query parameter and httpx errors quote the URL
    def handler(request: httpx.Request) -> httpx.Response:
        if response is None:
            raise httpx.ReadTimeout(f"timed out: {request.url}")
        return response

    # when
    with caplog.at_level(logging.DEBUG), pytest.raises(CollectError) as caught:
        _provider(handler).get_news(SINCE)

    # then
    assert TOKEN not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert TOKEN not in caplog.text


def test_token_is_not_logged_when_a_later_page_fails(caplog: pytest.LogCaptureFixture) -> None:
    # given
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise httpx.ConnectError(f"failed: {request.url}")
        return httpx.Response(200, json={"data": [_article(1)]})

    # when
    with caplog.at_level(logging.DEBUG):
        _provider(handler).get_news(SINCE)

    # then
    assert "page 2" in caplog.text
    assert TOKEN not in caplog.text


def test_article_repeated_across_pages_is_kept_once() -> None:
    # given
    handler, _ = _pages(
        httpx.Response(200, json={"data": [_article(1), _article(2)]}),
        httpx.Response(200, json={"data": [_article(2), _article(3)]}),
    )

    # when
    items = _provider(handler, max_calls=2).get_news(SINCE)

    # then: newest first
    assert [i.title for i in items] == ["article 3", "article 2", "article 1"]


def test_unusable_articles_are_dropped() -> None:
    # given
    articles = [
        _article(1),
        {**_article(2), "url": "javascript:alert(1)"},
        {**_article(3), "published_at": "2026-10-07T06:03:00"},
        {**_article(4), "published_at": "yesterday"},
        {**_article(5), "title": ""},
        {**_article(6), "published_at": "2026-10-06T19:59:59.000000Z"},
        "not an object",
    ]
    handler, _ = _pages(httpx.Response(200, json={"data": articles}))

    # when
    items = _provider(handler, max_calls=1).get_news(SINCE)

    # then: no web link, no timezone, unreadable time, no title, older than since
    assert [i.title for i in items] == ["article 1"]


def test_provider_satisfies_the_news_port() -> None:
    # given / when
    handler, _ = _pages(httpx.Response(200, json=EMPTY))
    provider: NewsProvider = _provider(handler)

    # then
    assert provider.name == "marketaux"
