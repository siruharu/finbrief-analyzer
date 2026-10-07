from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finbrief_analyzer.collect.factory import build_providers
from finbrief_analyzer.collect.models import CollectError, Market, NewsItem, Quote, Slot
from finbrief_analyzer.collect.quotes_fallback import QuoteResult
from finbrief_analyzer.collect.service import (
    MAX_NEWS,
    MAX_NEWS_PER_SOURCE,
    Providers,
    collect_snapshot,
    expected_session,
)
from finbrief_analyzer.core.config import DEFAULT_QUOTE_SYMBOLS, Settings

KST = timezone(timedelta(hours=9))
# Wednesday. 09:00 KST is Tuesday 20:00 in New York; 22:30 KST is Wednesday 09:30 there.
KR_OPEN_NOW = datetime(2026, 10, 7, 9, 0, tzinfo=KST)
US_OPEN_NOW = datetime(2026, 10, 7, 22, 30, tzinfo=KST)
US_SYMBOLS = ["US500", "IXIC", "DJI", "US10YT"]
KR_SYMBOLS = ["^KS11", "^KQ11", "US10YT"]


class _Quotes:
    """Stand-in for FallbackQuoteProvider."""

    def __init__(self, as_of: dict[str, date], error: Exception | None = None) -> None:
        self.asked: list[list[str]] = []
        self._as_of = as_of
        self._error = error

    def get_quotes(self, symbols: Sequence[str]) -> QuoteResult:
        self.asked.append(list(symbols))
        if self._error is not None:
            raise self._error
        found = tuple(
            Quote(symbol=s, close=1.0, as_of=self._as_of[s]) for s in symbols if s in self._as_of
        )
        return QuoteResult(found, tuple(s for s in symbols if s not in self._as_of))


class _Rates:
    name = "ecos"

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def get_rates(self) -> Sequence[Quote]:
        if self._error is not None:
            raise self._error
        return [Quote(symbol="USD/KRW", close=1343.4, as_of=date(2026, 10, 7))]


class _News:
    def __init__(
        self, name: str, items: Sequence[NewsItem] = (), error: Exception | None = None
    ) -> None:
        self.name = name
        self.since: list[datetime] = []
        self._items = items
        self._error = error

    def get_news(self, since: datetime) -> Sequence[NewsItem]:
        self.since.append(since)
        if self._error is not None:
            raise self._error
        return self._items


def _item(n: int, source: str = "yna.co.kr", hours_ago: float = 1.0) -> NewsItem:
    return NewsItem(
        title=f"{source} {n}",
        link=f"https://{source}/{n}",
        source=source,
        published_at=KR_OPEN_NOW - timedelta(hours=hours_ago, seconds=n),
    )


def _us_quotes(day: date = date(2026, 10, 6)) -> _Quotes:
    return _Quotes(dict.fromkeys(US_SYMBOLS, day))


def test_kr_open_slot_holds_us_indices_fx_and_news_since_the_previous_evening() -> None:
    # given
    quotes, news = _us_quotes(), _News("rss", [_item(1)])
    providers = Providers(quotes=quotes, rates=_Rates(), news=(news,))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert quotes.asked == [US_SYMBOLS]
    assert [q.symbol for q in snapshot.quotes] == [*US_SYMBOLS, "USD/KRW"]
    assert snapshot.slot is Slot.KR_OPEN
    assert news.since == [datetime(2026, 10, 6, 22, 0, tzinfo=KST)]
    assert len(snapshot.news) == 1
    assert snapshot.missing == ()


def test_us_open_slot_holds_kr_indices_fx_and_news_since_this_morning() -> None:
    # given
    quotes = _Quotes(dict.fromkeys(KR_SYMBOLS, date(2026, 10, 7)))
    news = _News("rss")
    providers = Providers(quotes=quotes, rates=_Rates(), news=(news,))

    # when
    snapshot = collect_snapshot(Slot.US_OPEN, US_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert quotes.asked == [KR_SYMBOLS]
    assert [q.symbol for q in snapshot.quotes] == [*KR_SYMBOLS, "USD/KRW"]
    assert news.since == [datetime(2026, 10, 7, 8, 30, tzinfo=KST)]


def test_quotes_are_labelled_with_the_configured_name_and_market() -> None:
    # given: adapters return symbols only
    providers = Providers(quotes=_us_quotes(), rates=_Rates())

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then: rate provider quotes are passed through as the provider labelled them
    labels = {q.symbol: (q.name, q.market) for q in snapshot.quotes}
    assert labels["US500"] == ("S&P 500", Market.US)
    assert labels["US10YT"] == ("미 국채 10년", Market.RATE)
    assert labels["USD/KRW"] == ("", None)


def test_failing_news_provider_is_recorded_as_missing_and_the_rest_is_kept() -> None:
    # given
    providers = Providers(
        quotes=_us_quotes(),
        news=(
            _News("marketaux", error=CollectError("marketaux", "HTTP 429")),
            _News("rss", [_item(1)]),
            _News("dart", error=RuntimeError("bug")),
        ),
    )

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert snapshot.missing == ("marketaux", "dart")
    assert len(snapshot.news) == 1
    assert len(snapshot.quotes) == 4


def test_quote_provider_failing_entirely_still_gives_a_snapshot_with_news() -> None:
    # given: the fallback is not supposed to raise, but the snapshot must survive if it does
    providers = Providers(
        quotes=_Quotes({}, error=RuntimeError("boom")), news=(_News("rss", [_item(1)]),)
    )

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert snapshot.quotes == ()
    assert snapshot.missing == tuple(US_SYMBOLS)
    assert len(snapshot.news) == 1


def test_symbols_no_provider_could_answer_are_recorded_as_missing() -> None:
    # given
    quotes = _Quotes({"US500": date(2026, 10, 6), "DJI": date(2026, 10, 6)})

    # when
    snapshot = collect_snapshot(
        Slot.KR_OPEN, KR_OPEN_NOW, Providers(quotes=quotes), DEFAULT_QUOTE_SYMBOLS
    )

    # then
    assert snapshot.missing == ("IXIC", "US10YT")


def test_index_older_than_the_last_expected_session_marks_its_market_closed() -> None:
    # given: Tuesday's US session should be in by Wednesday 09:00 KST, but the last row is Monday
    providers = Providers(quotes=_us_quotes(day=date(2026, 10, 5)))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert snapshot.is_closed(Market.US)
    assert not snapshot.is_closed(Market.KR)


def test_market_with_the_expected_session_is_not_marked_closed() -> None:
    # given
    providers = Providers(quotes=_us_quotes(day=date(2026, 10, 6)))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert snapshot.closed_markets == frozenset()


def test_monday_morning_expects_fridays_us_session_not_the_weekend() -> None:
    # given: Monday 09:00 KST is Sunday evening in New York
    monday = datetime(2026, 10, 12, 9, 0, tzinfo=KST)
    providers = Providers(quotes=_us_quotes(day=date(2026, 10, 9)))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, monday, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert expected_session(Market.US, monday) == date(2026, 10, 9)
    assert not snapshot.is_closed(Market.US)


def test_kr_holiday_is_judged_separately_from_the_us_market() -> None:
    # given: 22:30 KST on a Korean holiday, the last KOSPI row is the day before
    quotes = _Quotes(
        {
            "^KS11": date(2026, 10, 6),
            "^KQ11": date(2026, 10, 6),
            "US10YT": date(2026, 10, 6),
        }
    )

    # when
    snapshot = collect_snapshot(
        Slot.US_OPEN, US_OPEN_NOW, Providers(quotes=quotes), DEFAULT_QUOTE_SYMBOLS
    )

    # then: the rate symbol being a day old says nothing about a market being closed
    assert snapshot.closed_markets == frozenset({Market.KR})


@pytest.mark.parametrize(
    ("market", "now", "expected"),
    [
        pytest.param(Market.KR, datetime(2026, 10, 7, 15, 29, tzinfo=KST), date(2026, 10, 6)),
        pytest.param(Market.KR, datetime(2026, 10, 7, 15, 30, tzinfo=KST), date(2026, 10, 7)),
        pytest.param(Market.KR, datetime(2026, 10, 10, 12, 0, tzinfo=KST), date(2026, 10, 9)),
        pytest.param(Market.US, datetime(2026, 10, 7, 4, 59, tzinfo=KST), date(2026, 10, 5)),
        pytest.param(Market.US, datetime(2026, 10, 7, 5, 0, tzinfo=KST), date(2026, 10, 6)),
    ],
)
def test_expected_session_is_the_last_weekday_whose_close_has_passed(
    market: Market, now: datetime, expected: date
) -> None:
    # given / when / then: New York closes at 16:00 EDT, which is 05:00 KST
    assert expected_session(market, now) == expected


def test_without_a_rate_provider_the_snapshot_has_no_rates_and_nothing_missing() -> None:
    # given
    providers = Providers(quotes=_us_quotes())

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert [q.symbol for q in snapshot.quotes] == US_SYMBOLS
    assert snapshot.missing == ()


def test_failing_rate_provider_is_recorded_as_missing() -> None:
    # given
    providers = Providers(quotes=_us_quotes(), rates=_Rates(error=CollectError("ecos", "x")))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert snapshot.missing == ("ecos",)


def test_never_raises_whatever_the_providers_raise() -> None:
    # given
    providers = Providers(
        quotes=_Quotes({}, error=KeyError("x")),
        rates=_Rates(error=ZeroDivisionError()),
        news=(_News("rss", error=MemoryError()), _News("dart", error=CollectError("dart", "x"))),
    )

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert snapshot.quotes == ()
    assert snapshot.news == ()
    assert snapshot.missing == (*US_SYMBOLS, "ecos", "rss", "dart")


def test_empty_providers_give_an_empty_snapshot() -> None:
    # given / when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, Providers(), DEFAULT_QUOTE_SYMBOLS)

    # then: with no quote provider wired, the wanted symbols are simply missing
    assert snapshot.quotes == ()
    assert snapshot.news == ()
    assert snapshot.missing == tuple(US_SYMBOLS)


def test_same_link_from_two_providers_is_kept_once() -> None:
    # given
    providers = Providers(news=(_News("rss", [_item(1), _item(2)]), _News("other", [_item(2)])))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    assert len(snapshot.news) == 2


def test_news_is_capped_per_source_so_one_publisher_cannot_crowd_out_the_rest() -> None:
    # given: one feed with far more items than the others (339 in 12 hours, seen live)
    loud = [_item(n, "yna.co.kr") for n in range(200)]
    quiet = [_item(n, "mk.co.kr", hours_ago=5.0) for n in range(3)]
    providers = Providers(news=(_News("rss", [*loud, *quiet]),))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    by_source = [i.source for i in snapshot.news]
    assert by_source.count("yna.co.kr") == MAX_NEWS_PER_SOURCE
    assert by_source.count("mk.co.kr") == 3


def test_total_news_count_is_capped_and_the_newest_are_kept() -> None:
    # given: many sources, each under its own cap
    items = [_item(n, f"site{n % 20}.example", hours_ago=n / 100) for n in range(200)]
    providers = Providers(news=(_News("rss", items),))

    # when
    snapshot = collect_snapshot(Slot.KR_OPEN, KR_OPEN_NOW, providers, DEFAULT_QUOTE_SYMBOLS)

    # then
    times = [i.published_at for i in snapshot.news]
    assert len(times) == MAX_NEWS
    assert times == sorted(times, reverse=True)
    assert times[0] == max(i.published_at for i in items)


def test_naive_now_is_rejected() -> None:
    # given: a caller bug, not a provider failure
    # when / then
    with pytest.raises(ValueError, match="timezone"):
        collect_snapshot(
            Slot.KR_OPEN, datetime(2026, 10, 7, 9, 0), Providers(), DEFAULT_QUOTE_SYMBOLS
        )


@pytest.fixture
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for key in ("APP_MARKETAUX_TOKEN", "APP_DART_API_KEY", "APP_ECOS_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.usefixtures("_isolated_env")
def test_providers_without_a_key_are_left_out_by_build_providers() -> None:
    # given: no API key configured
    with httpx.Client() as client:
        # when
        providers = build_providers(Settings(), client)

    # then: only the keyless sources remain
    assert providers.rates is None
    assert [p.name for p in providers.news] == ["rss"]
    assert providers.quotes is not None


@pytest.mark.usefixtures("_isolated_env")
def test_build_providers_wires_every_source_that_has_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given
    monkeypatch.setenv("APP_MARKETAUX_TOKEN", "t")
    monkeypatch.setenv("APP_DART_API_KEY", "d")
    monkeypatch.setenv("APP_ECOS_API_KEY", "e")

    # when
    with httpx.Client() as client:
        providers = build_providers(Settings(), client)

    # then
    assert providers.rates is not None
    assert providers.rates.name == "ecos"
    assert [p.name for p in providers.news] == ["rss", "marketaux", "dart"]


@pytest.mark.usefixtures("_isolated_env")
def test_build_providers_skips_rss_when_no_feed_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given
    monkeypatch.setenv("APP_KR_RSS_FEEDS", "[]")

    # when
    with httpx.Client() as client:
        providers = build_providers(Settings(), client)

    # then
    assert providers.news == ()
