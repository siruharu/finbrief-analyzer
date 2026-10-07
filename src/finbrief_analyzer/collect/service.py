"""Assemble one MarketSnapshot per slot. A failing source becomes an entry in `missing`."""

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Protocol
from zoneinfo import ZoneInfo

from finbrief_analyzer.collect.models import (
    CollectError,
    Market,
    MarketSnapshot,
    NewsItem,
    Quote,
    Slot,
)
from finbrief_analyzer.collect.ports import NewsProvider, RateProvider
from finbrief_analyzer.collect.quotes_fallback import QuoteResult
from finbrief_analyzer.core.config import QuoteSymbol

logger = logging.getLogger(__name__)

# Each briefing reports the market that closed before it, plus rates.
SLOT_MARKETS = {
    Slot.KR_OPEN: (Market.US, Market.RATE),
    Slot.US_OPEN: (Market.KR, Market.RATE),
}
# Back to roughly the previous slot (about 09:00 and 22:30 KST), with some margin.
NEWS_LOOKBACK = {
    Slot.KR_OPEN: timedelta(hours=11),
    Slot.US_OPEN: timedelta(hours=14),
}
MAX_NEWS = 80
MAX_NEWS_PER_SOURCE = 15
# Local closing time per exchange. Rates and FX have no session to be closed.
MARKET_CLOSE = {
    Market.KR: (ZoneInfo("Asia/Seoul"), time(15, 30)),
    Market.US: (ZoneInfo("America/New_York"), time(16, 0)),
}


class QuoteCollector(Protocol):
    """What FallbackQuoteProvider offers: partial results instead of exceptions."""

    def get_quotes(self, symbols: Sequence[str]) -> QuoteResult: ...


@dataclass(frozen=True, slots=True)
class Providers:
    """The sources to use. A source without its API key is simply absent."""

    quotes: QuoteCollector | None = None
    rates: RateProvider | None = None
    news: tuple[NewsProvider, ...] = ()


def collect_snapshot(
    slot: Slot, now: datetime, providers: Providers, symbols: Sequence[QuoteSymbol]
) -> MarketSnapshot:
    """Collect everything for the slot. Provider failures never raise from here."""
    if now.utcoffset() is None:
        raise ValueError("now must have a timezone")
    wanted = [s for s in symbols if s.market in SLOT_MARKETS[slot]]
    quotes = _labelled(_collect_quotes(providers.quotes, [s.symbol for s in wanted]), wanted)
    rates, rates_missing = _collect_rates(providers.rates)
    news, news_missing = _collect_news(providers.news, now - NEWS_LOOKBACK[slot])
    return MarketSnapshot(
        slot=slot,
        quotes=(*quotes.quotes, *rates),
        news=news,
        missing=(*quotes.missing, *rates_missing, *news_missing),
        closed_markets=_closed_markets(quotes.quotes, now),
    )


def expected_session(market: Market, now: datetime) -> date:
    """The latest weekday whose close has passed at `now`, in the exchange's own time."""
    zone, close = MARKET_CLOSE[market]
    local = now.astimezone(zone)
    day = local.date() if local.time() >= close else local.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _closed_markets(quotes: Sequence[Quote], now: datetime) -> frozenset[Market]:
    """A market is closed when one of its indices has no row for the expected session."""
    closed: set[Market] = set()
    for quote in quotes:
        market = quote.market
        if market in MARKET_CLOSE and quote.as_of < expected_session(market, now):
            closed.add(market)
    return frozenset(closed)


def _collect_quotes(collector: QuoteCollector | None, symbols: Sequence[str]) -> QuoteResult:
    nothing = QuoteResult(quotes=(), missing=tuple(symbols))
    if collector is None or not symbols:
        return nothing
    result = _attempt("quotes", lambda: collector.get_quotes(symbols))
    return nothing if result is None else result


def _labelled(result: QuoteResult, wanted: Sequence[QuoteSymbol]) -> QuoteResult:
    """Attach the configured display name and market to each quote."""
    by_symbol = {s.symbol: s for s in wanted}
    quotes = tuple(
        replace(q, name=by_symbol[q.symbol].name, market=by_symbol[q.symbol].market)
        if q.symbol in by_symbol
        else q
        for q in result.quotes
    )
    return QuoteResult(quotes=quotes, missing=result.missing)


def _collect_rates(provider: RateProvider | None) -> tuple[tuple[Quote, ...], tuple[str, ...]]:
    if provider is None:
        return (), ()
    rates = _attempt(provider.name, provider.get_rates)
    return ((), (provider.name,)) if rates is None else (tuple(rates), ())


def _collect_news(
    providers: Sequence[NewsProvider], since: datetime
) -> tuple[tuple[NewsItem, ...], tuple[str, ...]]:
    by_link: dict[str, NewsItem] = {}
    missing: list[str] = []
    for provider in providers:
        # Each provider applies `since` itself; DART filings only carry a date.
        items = _attempt(provider.name, partial(provider.get_news, since))
        if items is None:
            missing.append(provider.name)
            continue
        for item in items:
            by_link.setdefault(item.link, item)
    return _cap(by_link.values()), tuple(missing)


def _cap(items: Iterable[NewsItem]) -> tuple[NewsItem, ...]:
    """Keep the newest items, limited per source and in total."""
    newest_first = sorted(items, key=lambda item: item.published_at, reverse=True)
    kept: list[NewsItem] = []
    per_source: Counter[str] = Counter()
    for item in newest_first:
        if per_source[item.source] < MAX_NEWS_PER_SOURCE:
            kept.append(item)
            per_source[item.source] += 1
        if len(kept) == MAX_NEWS:
            break
    return tuple(kept)


def _attempt[T](source: str, call: Callable[[], T]) -> T | None:
    """Run one source. None means it failed; the reason is in the log."""
    try:
        return call()
    except CollectError as error:
        logger.warning("source failed: %s", error)
    except Exception:
        # A crash in a third-party library must not take the briefing down with it.
        logger.exception("source crashed: %s", source)
    return None
