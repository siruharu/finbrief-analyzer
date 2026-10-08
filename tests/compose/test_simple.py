from datetime import UTC, date, datetime, timedelta

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote, Slot
from finbrief_analyzer.compose.simple import MAX_NEWS_ITEMS, compose_simple
from finbrief_analyzer.deliver.models import Briefing, Section

DAY = date(2026, 10, 8)
AS_OF = date(2026, 10, 7)

SP500 = Quote("US500", 7818.93, AS_OF, prev_close=7742.5, name="S&P 500", market=Market.US)
KOSPI = Quote("^KS11", 6803.9, AS_OF, prev_close=6941.39, name="KOSPI", market=Market.KR)
NIKKEI = Quote("^N225", 69309.23, AS_OF, prev_close=70683.98, name="닛케이 225", market=Market.ASIA)
KTB3 = Quote("KTB3Y", 3.961, AS_OF, prev_close=3.933, name="국고채 3년", market=Market.RATE)
USDKRW = Quote("USD/KRW", 1343.4, AS_OF, prev_close=1358.5, name="원/달러", market=Market.FX)
EURUSD = Quote("EUR/USD", 1.1204, AS_OF, prev_close=1.12535, name="유로/달러", market=Market.FX)
WTI = Quote("CL=F", 89.44, AS_OF, prev_close=88.1, name="WTI", market=Market.COMMODITY)
EVERY_MARKET = (KOSPI, SP500, NIKKEI, KTB3, USDKRW, WTI)


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
    slot: Slot = Slot.KR_OPEN,
) -> MarketSnapshot:
    return MarketSnapshot(slot, quotes, news, missing, closed)


def _lines(snapshot: MarketSnapshot) -> tuple[str, ...]:
    return compose_simple(snapshot, DAY).sections[0].lines


def _section(briefing: Briefing, title: str) -> Section:
    return next(section for section in briefing.sections if section.title == title)


def _quote_titles(briefing: Briefing) -> list[str]:
    return [section.title for section in briefing.sections if section.title != "뉴스"]


def test_quotes_are_grouped_under_one_heading_per_market() -> None:
    # given
    snapshot = _snapshot(quotes=EVERY_MARKET)

    # when
    briefing = compose_simple(snapshot, DAY)

    # then
    assert _section(briefing, "국내 증시").lines == ("KOSPI 6,803.90 (-1.98%)",)
    assert _section(briefing, "미국 증시").lines == ("S&P 500 7,818.93 (+0.99%)",)
    assert _section(briefing, "아시아 증시").lines == ("닛케이 225 69,309.23 (-1.94%)",)
    assert _section(briefing, "금리").lines == ("국고채 3년 3.961% (+2.8bp)",)
    assert _section(briefing, "환율").lines == ("원/달러 1,343.40 (-15.10, -1.11%)",)
    assert _section(briefing, "원자재·코인").lines == ("WTI 89.44 (+1.52%)",)


def test_kr_open_briefing_leads_with_the_us_market_that_closed_overnight() -> None:
    # given / when
    briefing = compose_simple(_snapshot(quotes=EVERY_MARKET, slot=Slot.KR_OPEN), DAY)

    # then
    assert _quote_titles(briefing) == [
        "미국 증시",
        "국내 증시",
        "아시아 증시",
        "금리",
        "환율",
        "원자재·코인",
    ]


def test_us_open_briefing_leads_with_the_kr_market_that_closed_today() -> None:
    # given / when
    briefing = compose_simple(_snapshot(quotes=EVERY_MARKET, slot=Slot.US_OPEN), DAY)

    # then
    assert _quote_titles(briefing)[:3] == ["국내 증시", "아시아 증시", "미국 증시"]


def test_quotes_within_a_group_keep_the_order_of_the_snapshot() -> None:
    # given
    dow = Quote("DJI", 51521.28, AS_OF, name="다우존스", market=Market.US)

    # when
    lines = _section(compose_simple(_snapshot(quotes=(SP500, KOSPI, dow)), DAY), "미국 증시").lines

    # then
    assert [line.split()[0] for line in lines] == ["S&P", "다우존스"]


def test_only_the_first_group_with_quotes_is_required() -> None:
    # given: the leading US group failed entirely, the rest came in
    snapshot = _snapshot(quotes=(KOSPI, KTB3))

    # when
    briefing = compose_simple(snapshot, DAY)

    # then: one missing group does not block the briefing
    assert [(s.title, s.required) for s in briefing.sections if s.lines] == [
        ("국내 증시", True),
        ("금리", False),
    ]
    assert briefing.is_sendable is True


def test_group_without_quotes_is_left_out() -> None:
    # given / when
    briefing = compose_simple(_snapshot(quotes=(SP500,)), DAY)

    # then
    assert _quote_titles(briefing) == ["미국 증시"]


def test_quote_without_a_market_is_still_shown() -> None:
    # given: a symbol that is not in the configured list
    bare = Quote("IXIC", 27599.79, AS_OF)

    # when
    briefing = compose_simple(_snapshot(quotes=(bare,)), DAY)

    # then
    assert _section(briefing, "기타").lines == ("IXIC 27,599.79",)


def test_rate_change_is_given_in_basis_points_not_percent() -> None:
    # given: 3.933 -> 3.961 is +0.71% but should read +2.8bp
    # when
    line = _lines(_snapshot(quotes=(KTB3,)))[0]

    # then
    assert "bp" in line
    assert "0.71" not in line


def test_small_values_keep_four_decimals() -> None:
    # given: a rate around 1 would lose its movement at two decimals
    # when / then
    assert _lines(_snapshot(quotes=(EURUSD,))) == ("유로/달러 1.1204 (-0.0050, -0.44%)",)


def test_quote_without_a_previous_close_shows_the_value_only() -> None:
    # given
    lonely = Quote("DJI", 51521.28, AS_OF, name="다우존스", market=Market.US)

    # when / then
    assert _lines(_snapshot(quotes=(lonely,))) == ("다우존스 51,521.28",)


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
    news = _section(compose_simple(snapshot, DAY), "뉴스")

    # then
    item = news.links[0]
    assert (item.title, item.url, item.source) == ("기사 1", "https://example.com/1", "연합뉴스")
    assert news.lines == ()
    assert news.required is False


def test_news_is_capped_keeping_the_newest_items() -> None:
    # given: more items than fit in a mail, newest first as the snapshot delivers them
    items = tuple(_news(index) for index in range(MAX_NEWS_ITEMS + 5))

    # when
    links = _section(compose_simple(_snapshot(news=items), DAY), "뉴스").links

    # then
    assert len(links) == MAX_NEWS_ITEMS
    assert links[0].title == "기사 0"
