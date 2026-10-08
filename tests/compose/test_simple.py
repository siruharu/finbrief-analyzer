from datetime import UTC, date, datetime, timedelta

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote, Slot
from finbrief_analyzer.compose.simple import MAX_NEWS_ITEMS, compose_simple

DAY = date(2026, 10, 8)
AS_OF = date(2026, 10, 7)

SP500 = Quote("US500", 7818.93, AS_OF, prev_close=7742.5, name="S&P 500", market=Market.US)
KTB3 = Quote("KTB3Y", 3.961, AS_OF, prev_close=3.933, name="국고채 3년", market=Market.RATE)
USDKRW = Quote("USD/KRW", 1343.4, AS_OF, prev_close=1358.5, name="원/달러", market=Market.FX)


def _news(index: int, summary: str | None = None) -> NewsItem:
    return NewsItem(
        title=f"기사 {index}",
        link=f"https://example.com/{index}",
        source="연합뉴스",
        published_at=datetime(2026, 10, 8, 0, 0, tzinfo=UTC) - timedelta(minutes=index),
        summary=summary,
    )


def _snapshot(
    quotes: tuple[Quote, ...] = (SP500,),
    news: tuple[NewsItem, ...] = (),
    missing: tuple[str, ...] = (),
    closed: frozenset[Market] = frozenset(),
) -> MarketSnapshot:
    return MarketSnapshot(Slot.KR_OPEN, quotes, news, missing, closed)


def _lines(snapshot: MarketSnapshot) -> tuple[str, ...]:
    return compose_simple(snapshot, DAY).sections[0].lines


def test_indices_fx_and_rates_share_one_required_section_with_their_changes() -> None:
    # given
    snapshot = _snapshot(quotes=(SP500, USDKRW, KTB3))

    # when
    briefing = compose_simple(snapshot, DAY)

    # then
    quotes = briefing.sections[0]
    assert quotes.required is True
    assert quotes.lines == (
        "S&P 500 7,818.93 (+0.99%)",
        "원/달러 1,343.40원 (-15.10원, -1.11%)",
        "국고채 3년 3.961% (+2.8bp)",
    )


def test_rate_change_is_given_in_basis_points_not_percent() -> None:
    # given: 3.933 -> 3.961 is +0.71% but should read +2.8bp
    # when
    line = _lines(_snapshot(quotes=(KTB3,)))[0]

    # then
    assert "bp" in line
    assert "0.71" not in line


def test_quote_without_a_previous_close_shows_the_value_only() -> None:
    # given
    lonely = Quote("DJI", 51521.28, AS_OF, name="다우존스", market=Market.US)

    # when / then
    assert _lines(_snapshot(quotes=(lonely,))) == ("다우존스 51,521.28",)


def test_quote_without_a_display_name_falls_back_to_its_symbol() -> None:
    # given: a symbol that is not in the configured list
    bare = Quote("IXIC", 27599.79, AS_OF)

    # when / then
    assert _lines(_snapshot(quotes=(bare,))) == ("IXIC 27,599.79",)


def test_briefing_carries_the_slot_and_the_given_date() -> None:
    # given / when
    briefing = compose_simple(_snapshot(), DAY)

    # then
    assert (briefing.slot, briefing.briefing_date) == (Slot.KR_OPEN, DAY)


def test_snapshot_without_quotes_makes_an_unsendable_briefing() -> None:
    # given: every quote source failed, news is fine
    snapshot = _snapshot(quotes=(), news=(_news(1),))

    # when / then
    assert compose_simple(snapshot, DAY).is_sendable is False


def test_missing_sources_become_a_notice() -> None:
    # given
    snapshot = _snapshot(missing=("ecos", "marketaux"))

    # when
    notices = compose_simple(snapshot, DAY).notices

    # then
    assert len(notices) == 1
    assert "ecos" in notices[0]
    assert "marketaux" in notices[0]


def test_closed_market_becomes_a_notice_naming_the_last_trading_day() -> None:
    # given: the US market was closed, so the quote is from the session before
    snapshot = _snapshot(closed=frozenset({Market.US}))

    # when
    notices = compose_simple(snapshot, DAY).notices

    # then
    assert len(notices) == 1
    assert "미국" in notices[0]
    assert "휴장" in notices[0]
    assert "2026-10-07" in notices[0]


def test_snapshot_with_nothing_wrong_has_no_notices() -> None:
    # given / when / then
    assert compose_simple(_snapshot(), DAY).notices == ()


def test_news_lists_title_link_and_source_without_the_summary_text() -> None:
    # given
    snapshot = _snapshot(news=(_news(1, summary="요약 본문은 싣지 않는다"),))

    # when
    news = compose_simple(snapshot, DAY).sections[1]

    # then
    item = news.links[0]
    assert (item.title, item.url, item.source) == ("기사 1", "https://example.com/1", "연합뉴스")
    assert news.lines == ()
    assert news.required is False


def test_news_is_capped_keeping_the_newest_items() -> None:
    # given: more items than fit in a mail, newest first as the snapshot delivers them
    items = tuple(_news(index) for index in range(MAX_NEWS_ITEMS + 5))

    # when
    links = compose_simple(_snapshot(news=items), DAY).sections[1].links

    # then
    assert len(links) == MAX_NEWS_ITEMS
    assert links[0].title == "기사 0"
