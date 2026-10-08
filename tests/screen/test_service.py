from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import Engine

from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.history import HistorySources
from finbrief_analyzer.screen.models import Bar, Exchange, Member, Rule, ScreenResult
from finbrief_analyzer.screen.ranking import RankRow
from finbrief_analyzer.screen.service import (
    ScreenDeps,
    ScreenService,
    build_screen_service,
    screen_group,
)
from finbrief_analyzer.screen.sources import BatchResult
from finbrief_analyzer.store.price_bars import add_bars
from finbrief_analyzer.store.universe import replace_members

KST = timezone(timedelta(hours=9))
EVENING = datetime(2026, 10, 8, 20, 0, tzinfo=KST)
LAST = date(2026, 10, 8)
KR = (Exchange.KOSPI, Exchange.KOSDAQ)


def weekly(
    symbol: str, closes: Sequence[float], last_volume: int = 1000, end: date = LAST
) -> list[Bar]:
    """A year of history: weekly bars, then 21 daily bars so the volume rule has its window."""
    count = len(closes)
    older = [
        Bar(symbol, end - timedelta(days=30 + (count - 1 - i) * 7), close, 1000)
        for i, close in enumerate(closes)
    ]
    daily = [Bar(symbol, end - timedelta(days=20 - i), closes[-1], 1000) for i in range(20)]
    return [*older, *daily, Bar(symbol, end, closes[-1], last_volume)]


def members(*symbols: str) -> list[Member]:
    return [Member(Exchange.KOSPI, symbol, f"이름{symbol}") for symbol in symbols]


def by_rule(results: Sequence[ScreenResult], rule: Rule) -> ScreenResult:
    return next(result for result in results if result.rule is rule)


FLAT = [100.0] * 53
PEAKED = [100.0] * 26 + [200.0] + [100.0] * 26


def test_stock_at_its_high_ranks_above_one_far_below_it() -> None:
    # given
    bars = {"A": weekly("A", FLAT), "B": weekly("B", PEAKED)}

    # when
    high = by_rule(screen_group(members("A", "B"), bars, KR, top=5, min_value=0), Rule.HIGH_52W)

    # then
    assert [(hit.symbol, hit.score) for hit in high.hits] == [("A", 1.0), ("B", 0.5)]
    assert high.as_of == LAST
    assert high.exchanges == KR


def test_hit_carries_the_name_the_close_and_the_move_of_the_day() -> None:
    # given: the last day closed 10% up on five times the usual volume
    history = weekly("A", FLAT, last_volume=5000)
    history[-1] = Bar("A", LAST, 110.0, 5000)

    # when
    volume = by_rule(
        screen_group(members("A"), {"A": history}, KR, top=5, min_value=0), Rule.VOLUME_SPIKE
    )

    # then
    (hit,) = volume.hits
    assert (hit.name, hit.close) == ("이름A", 110.0)
    assert hit.change_pct == pytest.approx(10.0)
    assert hit.score == pytest.approx(5.0)


def test_only_the_top_n_are_kept() -> None:
    # given
    bars = {symbol: weekly(symbol, FLAT) for symbol in "ABCDEFG"}

    # when
    results = screen_group(members(*"ABCDEFG"), bars, KR, top=3, min_value=0)

    # then
    assert all(len(result.hits) == 3 for result in results)


def test_stock_trading_too_little_is_left_out() -> None:
    # given: A trades 100 x 1,000 a day, the threshold is above that
    bars = {"A": weekly("A", FLAT)}

    # when
    results = screen_group(members("A"), bars, KR, top=5, min_value=200_000)

    # then
    assert all(result.hits == () for result in results)


def test_stock_whose_history_stops_before_the_latest_day_is_left_out() -> None:
    # given: B was suspended a week ago; its "last day" is not today
    bars = {
        "A": weekly("A", FLAT),
        "B": weekly("B", FLAT, last_volume=99_000, end=LAST - timedelta(days=7)),
    }

    # when
    results = screen_group(members("A", "B"), bars, KR, top=5, min_value=0)

    # then: an old spike is not reported as today's
    assert all([hit.symbol for hit in result.hits] == ["A"] for result in results)


def test_member_without_history_is_left_out() -> None:
    # given / when
    results = screen_group(members("A", "B"), {"A": weekly("A", FLAT)}, KR, top=5, min_value=0)

    # then
    assert all([hit.symbol for hit in result.hits] == ["A"] for result in results)


def test_group_without_any_history_gives_no_results() -> None:
    # given / when / then
    assert screen_group(members("A"), {}, KR, top=5, min_value=0) == []


class _Ranking:
    def fetch(self, exchange: Exchange, pages: int) -> list[RankRow]:
        return []


class _KrHistory:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def history(self, symbol: str, since: date) -> list[Bar]:
        self.asked.append(symbol)
        return weekly(symbol, FLAT)


class _Batch:
    def fetch(self, symbols: Sequence[str], since: date) -> BatchResult:
        return BatchResult({}, tuple(symbols))


class _Universe:
    def members(self, exchange: Exchange, size: int) -> list[Member]:
        return []


def _service(engine: Engine, history: _KrHistory, clock: float = 0.0) -> ScreenService:
    deps = ScreenDeps(
        engine=engine,
        sources=HistorySources(_Ranking(), history, _Batch()),
        universe={Exchange.KOSPI: _Universe()},
    )
    settings = Settings(screen_min_trading_value_krw=0, screen_update_seconds=60)
    return ScreenService(deps, settings, clock=lambda: clock)


def _seed(engine: Engine, stocks: dict[str, list[Bar]]) -> None:
    with session_scope(engine) as session:
        replace_members(session, Exchange.KOSPI, members(*stocks), date(2026, 10, 1))
        for bars in stocks.values():
            add_bars(session, bars)


def test_service_screens_the_stored_history_of_the_universe(store: Engine) -> None:
    # given: history already up to date
    _seed(store, {"A": weekly("A", FLAT), "B": weekly("B", PEAKED)})
    history = _KrHistory()

    # when
    results = _service(store, history).run(EVENING)

    # then: nothing had to be fetched, and both rules report the Korean group
    assert history.asked == []
    assert {result.rule for result in results} == {Rule.HIGH_52W, Rule.VOLUME_SPIKE}
    assert [hit.symbol for hit in by_rule(results, Rule.HIGH_52W).hits] == ["A", "B"]
    assert all(result.exchanges == KR for result in results)


def test_service_loads_missing_history_before_screening(store: Engine) -> None:
    # given: a universe member with no history yet
    with session_scope(store) as session:
        replace_members(session, Exchange.KOSPI, members("A"), date(2026, 10, 1))
    history = _KrHistory()

    # when
    results = _service(store, history).run(EVENING)

    # then
    assert history.asked == ["A"]
    assert [hit.symbol for hit in by_rule(results, Rule.HIGH_52W).hits] == ["A"]


def test_service_with_an_empty_universe_gives_no_results(store: Engine) -> None:
    # given / when / then
    assert _service(store, _KrHistory()).run(EVENING) == ()


def test_screening_is_not_built_when_it_is_turned_off(store: Engine) -> None:
    # given: the default
    settings = Settings()

    # when
    with httpx.Client() as client:
        service = build_screen_service(settings, store, client)

    # then
    assert settings.screen_enabled is False
    assert service is None


def test_screening_is_built_when_it_is_turned_on(store: Engine) -> None:
    # given
    settings = Settings(screen_enabled=True)

    # when
    with httpx.Client() as client:
        service = build_screen_service(settings, store, client)

    # then
    assert isinstance(service, ScreenService)
