"""Composer v0: lay the snapshot out as it is. No selection, no summarising."""

from collections.abc import Sequence
from datetime import date

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote
from finbrief_analyzer.deliver.models import Briefing, LinkItem, Section

# Newest first. Choosing which items matter is the summarising step's job, which does not exist yet.
MAX_NEWS_ITEMS = 10
MARKET_LABELS = {Market.KR: "국내", Market.US: "미국"}


def compose_simple(snapshot: MarketSnapshot, briefing_date: date) -> Briefing:
    return Briefing(
        slot=snapshot.slot,
        briefing_date=briefing_date,
        sections=(_quote_section(snapshot.quotes), _news_section(snapshot.news)),
        notices=_notices(snapshot),
    )


def _quote_section(quotes: Sequence[Quote]) -> Section:
    # Required: a briefing without a single quote is not worth sending.
    return Section(title="시세", lines=tuple(_quote_line(q) for q in quotes), required=True)


def _quote_line(quote: Quote) -> str:
    name = quote.name or quote.symbol
    if quote.market is Market.RATE:
        # A yield moving 3.933 -> 3.961 is +2.8bp; as a percentage it would read +0.71%.
        change = "" if quote.change_bp is None else f" ({quote.change_bp:+.1f}bp)"
        return f"{name} {quote.close:.3f}%{change}"
    if quote.change is None or quote.change_pct is None:
        unit = "원" if quote.market is Market.FX else ""
        return f"{name} {quote.close:,.2f}{unit}"
    if quote.market is Market.FX:
        return f"{name} {quote.close:,.2f}원 ({quote.change:+,.2f}원, {quote.change_pct:+.2f}%)"
    return f"{name} {quote.close:,.2f} ({quote.change_pct:+.2f}%)"


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
