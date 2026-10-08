from datetime import UTC, date, datetime, timedelta

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote, Slot
from finbrief_analyzer.compose.simple import MAX_NEWS_ITEMS, compose_simple
from finbrief_analyzer.deliver.models import Briefing, Section
from finbrief_analyzer.screen.models import Exchange, Rule, ScreenHit, ScreenResult

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


SAMSUNG = Quote(
    "005930", 266750.0, AS_OF, prev_close=268500.0, name="삼성전자", market=Market.KR_STOCK
)
NVIDIA = Quote("NVDA", 235.12, AS_OF, prev_close=231.0, name="엔비디아", market=Market.US_STOCK)


def test_watchlist_stocks_get_one_group_per_country() -> None:
    # given
    snapshot = _snapshot(quotes=(SP500, SAMSUNG, NVIDIA))

    # when
    briefing = compose_simple(snapshot, DAY)

    # then
    assert _section(briefing, "국내 관심 종목").lines == ("삼성전자 266,750 (-0.65%)",)
    assert _section(briefing, "미국 관심 종목").lines == ("엔비디아 235.12 (+1.78%)",)


def test_watchlist_groups_come_after_every_market_group_in_both_slots() -> None:
    # given
    quotes = (*EVERY_MARKET, SAMSUNG, NVIDIA)

    # when
    kr = _quote_titles(compose_simple(_snapshot(quotes=quotes, slot=Slot.KR_OPEN), DAY))
    us = _quote_titles(compose_simple(_snapshot(quotes=quotes, slot=Slot.US_OPEN), DAY))

    # then
    assert kr[-2:] == ["국내 관심 종목", "미국 관심 종목"]
    assert us[-2:] == ["국내 관심 종목", "미국 관심 종목"]


def test_korean_stock_price_is_shown_without_decimals() -> None:
    # given: won prices are whole numbers
    lonely = Quote("000660", 1750000.0, AS_OF, name="SK하이닉스", market=Market.KR_STOCK)

    # when / then
    assert _lines(_snapshot(quotes=(lonely,))) == ("SK하이닉스 1,750,000",)


def test_watchlist_alone_still_makes_a_sendable_briefing() -> None:
    # given: every index failed, the watchlist came in
    briefing = compose_simple(_snapshot(quotes=(SAMSUNG,)), DAY)

    # when / then
    assert briefing.is_sendable is True


HIGH_KR = ScreenResult(
    Rule.HIGH_52W,
    (Exchange.KOSPI, Exchange.KOSDAQ),
    AS_OF,
    (ScreenHit("096770", "SK이노베이션", 142500.0, 4.21, 1.0),),
)
VOLUME_US = ScreenResult(
    Rule.VOLUME_SPIKE, (Exchange.SP500,), AS_OF, (ScreenHit("MRNA", "Moderna", 88.4, None, 6.84),)
)


def _screened(*results: ScreenResult, quotes: tuple[Quote, ...] = (SP500,)) -> Briefing:
    snapshot = MarketSnapshot(Slot.KR_OPEN, quotes=quotes, news=(_news(1),), screens=results)
    return compose_simple(snapshot, DAY)


def test_screen_result_becomes_a_section_named_after_the_country_and_the_rule() -> None:
    # given / when
    briefing = _screened(HIGH_KR, VOLUME_US)

    # then
    titles = [section.title for section in briefing.sections]
    assert "조건 충족 종목 — 국내 52주 신고가 근접" in titles
    assert "조건 충족 종목 — 미국 거래량 급증" in titles


def test_screen_section_titles_never_call_the_list_a_recommendation() -> None:
    # given / when
    briefing = _screened(HIGH_KR, VOLUME_US)

    # then
    text = " ".join(section.title for section in briefing.sections)
    assert all(word not in text for word in ("추천", "매수", "유망"))


def test_screen_section_starts_with_the_rule_and_the_day_it_was_measured_on() -> None:
    # given / when
    section = _section(_screened(HIGH_KR), "조건 충족 종목 — 국내 52주 신고가 근접")

    # then
    assert section.lines[0] == "종가가 최근 52주 최고 종가에 가까운 순 (2026-10-07 종가 기준)"


def test_high_hit_line_shows_name_close_move_and_distance_from_the_high() -> None:
    # given / when
    section = _section(_screened(HIGH_KR), "조건 충족 종목 — 국내 52주 신고가 근접")

    # then: a won price has no decimals
    assert section.lines[1] == "SK이노베이션 142,500 (+4.21%) · 고가 대비 100.0%"


def test_volume_hit_line_shows_the_multiple_and_leaves_out_an_unknown_move() -> None:
    # given / when
    section = _section(_screened(VOLUME_US), "조건 충족 종목 — 미국 거래량 급증")

    # then: a dollar price keeps two decimals
    assert section.lines[1] == "Moderna 88.40 · 평소의 6.8배"


def test_screen_sections_come_after_the_quotes_and_before_the_news() -> None:
    # given / when
    titles = [section.title for section in _screened(HIGH_KR, quotes=(SP500, SAMSUNG)).sections]

    # then
    screen = titles.index("조건 충족 종목 — 국내 52주 신고가 근접")
    assert titles.index("국내 관심 종목") < screen < titles.index("뉴스")


def test_rule_without_hits_makes_no_section() -> None:
    # given
    empty = ScreenResult(Rule.HIGH_52W, (Exchange.SP500,), AS_OF, ())

    # when
    briefing = _screened(empty)

    # then
    assert not any("조건 충족" in section.title for section in briefing.sections)
    assert briefing.footnotes == ()


def test_disclaimer_is_a_footnote_whenever_a_screen_section_is_shown() -> None:
    # given / when
    briefing = _screened(HIGH_KR)

    # then
    (note,) = briefing.footnotes
    assert "권하는 것이 아니며" in note
    assert "검증하지 않았습니다" in note


def test_briefing_without_screens_has_no_footnote() -> None:
    # given / when / then
    assert compose_simple(_snapshot(), DAY).footnotes == ()


def test_screens_alone_do_not_make_a_briefing_sendable() -> None:
    # given: every quote failed, screening worked
    briefing = _screened(HIGH_KR, quotes=())

    # when / then: the required section is still the quotes
    assert briefing.is_sendable is False
    assert all(not section.required for section in briefing.sections if "조건" in section.title)
