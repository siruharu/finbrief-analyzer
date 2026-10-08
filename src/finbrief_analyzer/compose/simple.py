"""Composer v0: lay the snapshot out as it is. No selection, no summarising."""

from collections.abc import Sequence
from datetime import date

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote, Slot
from finbrief_analyzer.deliver.models import Briefing, LinkItem, Section

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


def compose_simple(snapshot: MarketSnapshot, briefing_date: date) -> Briefing:
    return Briefing(
        slot=snapshot.slot,
        briefing_date=briefing_date,
        sections=(*_quote_sections(snapshot), _news_section(snapshot.news)),
        notices=_notices(snapshot),
    )


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
