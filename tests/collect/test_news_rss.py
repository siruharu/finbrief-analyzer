from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.collect.news_rss import RssNewsProvider
from finbrief_analyzer.collect.ports import NewsProvider

KST = timezone(timedelta(hours=9))
FIXTURES = Path(__file__).parent / "fixtures"
HANKYUNG = "https://www.hankyung.com/feed/economy"
MK = "https://www.mk.co.kr/rss/30100041/"
BROKEN = "https://broken.example.com/rss"
LONG_AGO = datetime(2026, 1, 1, tzinfo=KST)

BODIES: dict[str, bytes] = {
    HANKYUNG: (FIXTURES / "rss_hankyung.xml").read_bytes(),
    MK: (FIXTURES / "rss_mk.xml").read_bytes(),
    BROKEN: (FIXTURES / "rss_broken.xml").read_bytes(),
}


def _provider(*feeds: str, bodies: dict[str, bytes] | None = None) -> RssNewsProvider:
    served = BODIES if bodies is None else bodies

    def handler(request: httpx.Request) -> httpx.Response:
        body = served.get(str(request.url))
        return httpx.Response(503) if body is None else httpx.Response(200, content=body)

    return RssNewsProvider(httpx.Client(transport=httpx.MockTransport(handler)), feeds)


def _feed(items: str, encoding: str = "UTF-8") -> bytes:
    xml = f'<?xml version="1.0" encoding="{encoding}"?><rss><channel>{items}</channel></rss>'
    return xml.encode(encoding)


def test_feed_item_becomes_news_item_with_title_summary_link_and_time() -> None:
    # given
    provider = _provider(MK)

    # when
    first = provider.get_news(LONG_AGO)[0]

    # then
    assert first.title.startswith("[단독] 정부 산란계 줄여놓고")
    assert first.title.endswith("땜질 논란")
    assert first.link == "https://www.mk.co.kr/news/economy/12170565"
    assert first.summary is not None
    assert first.summary.startswith("고병원성AI에 닭 살처분했는데")
    assert first.published_at == datetime(2026, 10, 7, 16, 27, 31, tzinfo=KST)
    assert first.source == "mk.co.kr"


def test_html_tags_and_entities_are_stripped_from_summary_and_title() -> None:
    # given
    provider = _provider(MK)

    # when
    item = next(i for i in provider.get_news(LONG_AGO) if i.link.endswith("12170546"))

    # then
    assert item.summary == (
        "금감원-증권사 21곳 내부감사 간담회 해킹 관련 IT보안 <전면> 재점검도 강조"
    )
    assert item.title == "금감원 & 증권사 간담회"


def test_feed_without_description_gives_items_without_summary() -> None:
    # given: hankyung.com ships title, link and time only
    provider = _provider(HANKYUNG)

    # when
    items = provider.get_news(LONG_AGO)

    # then
    assert len(items) == 3
    assert all(item.summary is None for item in items)


def test_timezone_written_with_a_colon_is_still_read_as_kst() -> None:
    # given: mk.co.kr writes "+09:00", which the RFC 822 parser reads as naive
    provider = _provider(MK)

    # when
    items = provider.get_news(LONG_AGO)

    # then
    assert items
    assert all(item.published_at.utcoffset() == timedelta(hours=9) for item in items)


def test_items_published_before_since_are_dropped() -> None:
    # given
    provider = _provider(HANKYUNG)

    # when
    items = provider.get_news(datetime(2026, 10, 7, 8, 8, 15, tzinfo=KST))

    # then: the boundary itself is kept, yesterday's item is not
    assert [i.link[-11:] for i in items] == ["2610078712i", "2610078173i"]


def test_since_in_another_timezone_compares_the_same_instant() -> None:
    # given: 07:00 UTC is 16:00 KST
    provider = _provider(HANKYUNG)

    # when
    items = provider.get_news(datetime(2026, 10, 7, 6, 58, 44, tzinfo=UTC))

    # then
    assert items == []


def test_same_link_in_two_feeds_is_kept_once_from_the_first_feed() -> None:
    # given
    provider = _provider(HANKYUNG, MK)

    # when
    items = provider.get_news(LONG_AGO)

    # then
    same = [i for i in items if i.link == "https://www.hankyung.com/article/202610078712i"]
    assert len(same) == 1
    assert same[0].source == "hankyung.com"
    assert len(items) == len({i.link for i in items})


def test_items_are_returned_newest_first() -> None:
    # given
    provider = _provider(HANKYUNG, MK)

    # when
    times = [i.published_at for i in provider.get_news(LONG_AGO)]

    # then
    assert times == sorted(times, reverse=True)


def test_feed_answering_5xx_does_not_hide_the_other_feeds() -> None:
    # given
    provider = _provider("https://down.example.com/rss", HANKYUNG)

    # when
    items = provider.get_news(LONG_AGO)

    # then
    assert len(items) == 3


def test_broken_xml_fails_that_feed_only() -> None:
    # given
    provider = _provider(BROKEN, HANKYUNG)

    # when
    items = provider.get_news(LONG_AGO)

    # then
    assert len(items) == 3


def test_every_feed_failing_raises_collect_error() -> None:
    # given
    provider = _provider(BROKEN, "https://down.example.com/rss")

    # when / then
    with pytest.raises(CollectError, match="rss"):
        provider.get_news(LONG_AGO)


def test_items_without_usable_time_link_or_title_are_dropped() -> None:
    # given: the fixture has items with no pubDate, an unreadable one, a javascript link, no title
    provider = _provider(MK)

    # when
    links = [i.link for i in provider.get_news(LONG_AGO)]

    # then
    assert links == [
        "https://www.mk.co.kr/news/economy/12170565",
        "https://www.mk.co.kr/news/stock/12170546",
        "https://www.hankyung.com/article/202610078712i",
    ]


def test_summary_equal_to_the_title_is_dropped() -> None:
    # given
    item = (
        "<item><title>같은 문장</title><link>https://example.com/a</link>"
        "<pubDate>Wed, 7 Oct 2026 16:23:52 +0900</pubDate>"
        "<description>같은 문장</description></item>"
    )
    provider = _provider("https://example.com/rss", bodies={"https://example.com/rss": _feed(item)})

    # when
    (news,) = provider.get_news(LONG_AGO)

    # then
    assert news.summary is None


def test_feed_declared_as_euc_kr_is_decoded_by_the_parser() -> None:
    # given
    item = (
        "<item><title>한글 제목</title><link>https://example.com/a</link>"
        "<pubDate>Wed, 7 Oct 2026 16:23:52 +0900</pubDate></item>"
    )
    body = _feed(item, encoding="EUC-KR")
    provider = _provider("https://example.com/rss", bodies={"https://example.com/rss": body})

    # when
    (news,) = provider.get_news(LONG_AGO)

    # then
    assert news.title == "한글 제목"


def test_feed_declaring_an_unknown_encoding_fails_that_feed() -> None:
    # given
    body = b'<?xml version="1.0" encoding="NOPE-8"?><rss><channel></channel></rss>'
    provider = _provider("https://example.com/rss", bodies={"https://example.com/rss": body})

    # when / then
    with pytest.raises(CollectError):
        provider.get_news(LONG_AGO)


def test_entity_expansion_attack_is_rejected() -> None:
    # given: a "billion laughs" style document
    body = (
        b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        b"<rss><channel><item><title>&b;</title><link>https://example.com/a</link>"
        b"<pubDate>Wed, 7 Oct 2026 16:23:52 +0900</pubDate></item></channel></rss>"
    )
    provider = _provider("https://example.com/rss", bodies={"https://example.com/rss": body})

    # when / then
    with pytest.raises(CollectError):
        provider.get_news(LONG_AGO)


def test_requests_identify_the_app_instead_of_the_http_library() -> None:
    # given: publishers answer 403 to the default "python-httpx" agent (seen live)
    agents: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        agents.append(request.headers["User-Agent"])
        return httpx.Response(200, content=BODIES[HANKYUNG])

    client = httpx.Client(transport=httpx.MockTransport(handler))

    # when
    RssNewsProvider(client, [HANKYUNG]).get_news(LONG_AGO)

    # then
    assert agents == ["finbrief-analyzer/0.1"]


def test_no_feeds_configured_returns_nothing() -> None:
    # given
    provider = _provider()

    # when / then
    assert provider.get_news(LONG_AGO) == []


def test_provider_satisfies_the_news_port() -> None:
    # given / when
    provider: NewsProvider = _provider(HANKYUNG)

    # then
    assert provider.name == "rss"
