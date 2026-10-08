"""Composer v0: lay the snapshot out as it is. No selection, no summarising."""

from collections.abc import Sequence
from datetime import date

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote, Slot
from finbrief_analyzer.deliver.models import Briefing, LinkItem, Section
from finbrief_analyzer.screen.models import Exchange, Rule, ScreenHit, ScreenResult

# Newest first. Choosing which items matter is the summarising step's job, which does not exist yet.
MAX_NEWS_ITEMS = 10
MARKET_LABELS = {Market.KR: "국내", Market.US: "미국"}
GROUP_TITLES: dict[Market | None, str] = {
    Market.KR: "국내 증시",
    Market.US: "미국 증시",
    Market.ASIA: "아시아 증시",
    Market.RATE: "금리",
    Market.FX: "환율",
    Market.COMMODITY: "원자재·코인",
    Market.KR_STOCK: "국내 관심 종목",
    Market.US_STOCK: "미국 관심 종목",
    # A quote whose symbol is not in the configured list carries no market.
    None: "기타",
}
_TAIL = (Market.RATE, Market.FX, Market.COMMODITY, Market.KR_STOCK, Market.US_STOCK, None)
# Each briefing leads with the market that closed just before it.
GROUP_ORDER: dict[Slot, tuple[Market | None, ...]] = {
    Slot.KR_OPEN: (Market.US, Market.KR, Market.ASIA, *_TAIL),
    Slot.US_OPEN: (Market.KR, Market.ASIA, Market.US, *_TAIL),
}


# The list is what a rule produced, not advice. The words 추천, 매수 and 유망 stay out of it.
SCREEN_TITLE = "조건 충족 종목"
RULE_TITLES = {Rule.HIGH_52W: "52주 신고가 근접", Rule.VOLUME_SPIKE: "거래량 급증"}
RULE_NOTES = {
    Rule.HIGH_52W: "종가가 최근 52주 최고 종가에 가까운 순",
    Rule.VOLUME_SPIKE: "거래량이 직전 20일 평균의 몇 배인지",
}
DISCLAIMER = (
    "조건 충족 종목은 정해진 규칙에 따라 자동으로 뽑은 목록입니다. 매수·매도를 권하는 것이 "
    "아니며, 이 규칙이 수익으로 이어지는지는 과거 자료로 검증하지 않았습니다. "
    "투자 판단과 그 결과는 본인에게 있습니다."
)


def compose_simple(snapshot: MarketSnapshot, briefing_date: date) -> Briefing:
    screens = _screen_sections(snapshot.screens)
    return Briefing(
        slot=snapshot.slot,
        briefing_date=briefing_date,
        sections=(*_quote_sections(snapshot), *screens, _news_section(snapshot.news)),
        notices=_notices(snapshot),
        footnotes=(DISCLAIMER,) if screens else (),
    )


def _screen_sections(results: Sequence[ScreenResult]) -> tuple[Section, ...]:
    """One section per rule and country that has hits. Never required."""
    return tuple(
        Section(
            title=f"{SCREEN_TITLE} — {_country(result)} {RULE_TITLES[result.rule]}",
            lines=(
                f"{RULE_NOTES[result.rule]} ({result.as_of.isoformat()} 종가 기준)",
                *(_hit_line(hit, result) for hit in result.hits),
            ),
        )
        for result in results
        if result.hits
    )


def _country(result: ScreenResult) -> str:
    return "미국" if Exchange.SP500 in result.exchanges else "국내"


def _hit_line(hit: ScreenHit, result: ScreenResult) -> str:
    digits = 2 if Exchange.SP500 in result.exchanges else 0  # won prices are whole numbers
    move = "" if hit.change_pct is None else f" ({hit.change_pct:+.2f}%)"
    if result.rule is Rule.HIGH_52W:
        detail = f"고가 대비 {hit.score * 100:.1f}%"
    else:
        detail = f"평소의 {hit.score:.1f}배"
    return f"{hit.name} {hit.close:,.{digits}f}{move} · {detail}"


def _quote_sections(snapshot: MarketSnapshot) -> tuple[Section, ...]:
    """One section per market that has quotes, in the slot's order."""
    groups = [
        (GROUP_TITLES[market], [q for q in snapshot.quotes if q.market is market])
        for market in GROUP_ORDER[snapshot.slot]
    ]
    filled = [(title, quotes) for title, quotes in groups if quotes]
    if not filled:
        # Required and empty: a briefing without a single quote is not worth sending.
        return (Section(title="시세", required=True),)
    # Only the first group is required, so one failed source does not block the rest.
    return tuple(
        Section(title=title, lines=tuple(_quote_line(q) for q in quotes), required=index == 0)
        for index, (title, quotes) in enumerate(filled)
    )


def _quote_line(quote: Quote) -> str:
    name = quote.name or quote.symbol
    if quote.market is Market.RATE:
        # A yield moving 3.933 -> 3.961 is +2.8bp; as a percentage it would read +0.71%.
        change = "" if quote.change_bp is None else f" ({quote.change_bp:+.1f}bp)"
        return f"{name} {quote.close:.3f}%{change}"
    digits = _digits(quote)
    value = f"{name} {quote.close:,.{digits}f}"
    if quote.change is None or quote.change_pct is None:
        return value
    if quote.market is Market.FX:
        return f"{value} ({quote.change:+,.{digits}f}, {quote.change_pct:+.2f}%)"
    return f"{value} ({quote.change_pct:+.2f}%)"


def _digits(quote: Quote) -> int:
    if quote.market is Market.KR_STOCK:
        return 0  # won prices are whole numbers
    # A value around 1 (EUR/USD) would lose its movement at two decimals.
    return 4 if abs(quote.close) < 10 else 2


def _news_section(items: Sequence[NewsItem]) -> Section:
    links = tuple(
        LinkItem(title=item.title, url=item.link, source=item.source)
        for item in items[:MAX_NEWS_ITEMS]
    )
    return Section(title="뉴스", links=links)


def _notices(snapshot: MarketSnapshot) -> tuple[str, ...]:
    notices = [
        _closed_notice(market, snapshot.quotes) for market in sorted(snapshot.closed_markets)
    ]
    if snapshot.missing:
        notices.append(f"일부 출처를 가져오지 못했습니다: {', '.join(snapshot.missing)}")
    return tuple(notices)


def _closed_notice(market: Market, quotes: Sequence[Quote]) -> str:
    label = MARKET_LABELS.get(market, market.value)
    days = [quote.as_of for quote in quotes if quote.market is market]
    basis = f" 아래 값은 직전 거래일({max(days).isoformat()}) 기준입니다." if days else ""
    return f"{label} 시장은 휴장이었습니다.{basis}"
