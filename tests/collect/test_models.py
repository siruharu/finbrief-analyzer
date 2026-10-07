from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from finbrief_analyzer.collect.models import (
    CollectError,
    Market,
    MarketSnapshot,
    NewsItem,
    Quote,
    Slot,
)
from finbrief_analyzer.collect.ports import NewsProvider, QuoteProvider, RateProvider

KST = timezone(timedelta(hours=9))


def _news(link: str, title: str = "title") -> NewsItem:
    return NewsItem(
        title=title,
        link=link,
        source="yna",
        published_at=datetime(2026, 10, 7, 9, 0, tzinfo=KST),
    )


def test_quote_computes_change_as_percentage_from_close_and_prev_close() -> None:
    # given: a quote that rose from 200 to 210
    quote = Quote(symbol="^KS11", close=210.0, prev_close=200.0, as_of=date(2026, 10, 7))

    # when
    change = quote.change_pct

    # then
    assert change == pytest.approx(5.0)


def test_quote_change_is_none_without_prev_close() -> None:
    # given: only one trading day was available
    quote = Quote(symbol="^KS11", close=210.0, as_of=date(2026, 10, 7))

    # when / then
    assert quote.change_pct is None


def test_quote_change_is_none_when_prev_close_is_zero() -> None:
    # given
    quote = Quote(symbol="^KS11", close=210.0, prev_close=0.0, as_of=date(2026, 10, 7))

    # when / then
    assert quote.change_pct is None


def test_quote_rejects_nan_close() -> None:
    # given: sources return NaN closes for unfinished rows (seen in the PoC)
    # when / then
    with pytest.raises(ValueError, match="close"):
        Quote(symbol="USD/KRW", close=float("nan"), as_of=date(2026, 10, 6))


def test_snapshot_preserves_missing_source_names_in_order() -> None:
    # given
    snapshot = MarketSnapshot(slot=Slot.KR_OPEN, missing=("marketaux", "ecos", "dart"))

    # when / then
    assert snapshot.missing == ("marketaux", "ecos", "dart")


def test_snapshot_reports_markets_marked_as_closed() -> None:
    # given
    snapshot = MarketSnapshot(slot=Slot.US_OPEN, closed_markets=frozenset({Market.KR}))

    # when / then
    assert snapshot.is_closed(Market.KR)
    assert not snapshot.is_closed(Market.US)


def test_snapshot_without_quotes_or_news_is_valid() -> None:
    # given / when
    snapshot = MarketSnapshot(slot=Slot.KR_OPEN)

    # then
    assert snapshot.quotes == ()
    assert snapshot.news == ()
    assert snapshot.missing == ()


def test_news_items_with_same_link_are_the_same_item() -> None:
    # given: one article seen in two feeds with different titles
    first = _news("https://example.com/a", title="from feed one")
    second = _news("https://example.com/a", title="from feed two")
    other = _news("https://example.com/b")

    # when
    unique = {first, second, other}

    # then
    assert first == second
    assert len(unique) == 2


def test_news_item_rejects_naive_published_at() -> None:
    # given: a timestamp that lost its timezone while parsing
    naive = datetime(2026, 10, 7, 9, 0)

    # when / then
    with pytest.raises(ValueError, match="timezone"):
        NewsItem(title="t", link="https://example.com/a", source="mk", published_at=naive)


def test_slot_has_exactly_two_values() -> None:
    # given / when / then
    assert set(Slot) == {Slot.KR_OPEN, Slot.US_OPEN}


def test_collect_error_carries_source_name() -> None:
    # given / when
    error = CollectError("ecos", "invalid key")

    # then
    assert error.source == "ecos"
    assert "ecos" in str(error)
    assert "invalid key" in str(error)


class _FakeProvider:
    name = "fake"

    def get_quotes(self, symbols: Sequence[str]) -> list[Quote]:
        return [Quote(symbol=s, close=1.0, as_of=date(2026, 10, 7)) for s in symbols]

    def get_rates(self) -> list[Quote]:
        return []

    def get_news(self, since: datetime) -> list[NewsItem]:
        return [_news("https://example.com/a")]


def test_plain_class_with_matching_methods_satisfies_every_port() -> None:
    # given: an adapter that does not inherit from the protocols
    fake = _FakeProvider()
    quotes: QuoteProvider = fake
    rates: RateProvider = fake
    news: NewsProvider = fake

    # when
    result = (
        quotes.get_quotes(["IXIC"]),
        rates.get_rates(),
        news.get_news(datetime(2026, 10, 7, tzinfo=UTC)),
    )

    # then
    assert [q.symbol for q in result[0]] == ["IXIC"]
    assert result[1] == []
    assert len(result[2]) == 1
