import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine

from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.jobs.backfill_prices import ScreenDeps, main
from finbrief_analyzer.screen.history import HistorySources
from finbrief_analyzer.screen.models import Bar, Exchange, Member
from finbrief_analyzer.screen.ranking import RankRow
from finbrief_analyzer.screen.sources import BatchResult
from finbrief_analyzer.store.price_bars import history
from finbrief_analyzer.store.universe import members

KST = timezone(timedelta(hours=9))
EVENING = datetime(2026, 10, 8, 20, 0, tzinfo=KST)
D7, D8 = date(2026, 10, 7), date(2026, 10, 8)


class OneStockUniverse:
    def __init__(self, member: Member) -> None:
        self._member = member

    def members(self, exchange: Exchange, size: int) -> list[Member]:
        return [self._member]


class NoRanking:
    def fetch(self, exchange: Exchange, pages: int) -> list[RankRow]:
        return []


class KrHistory:
    def history(self, symbol: str, since: date) -> list[Bar]:
        return [Bar(symbol, D7, 100.0, 10), Bar(symbol, D8, 101.0, 10)]


class UsBatch:
    def __init__(self, answer: bool = True) -> None:
        self._answer = answer

    def fetch(self, symbols: Sequence[str], since: date) -> BatchResult:
        if not self._answer:
            return BatchResult({}, tuple(symbols))
        return BatchResult({s: [Bar(s, D7, 200.0, 10)] for s in symbols}, ())


def _open(
    engine: Engine, batch: UsBatch
) -> Callable[[Settings], AbstractContextManager[ScreenDeps]]:
    @contextmanager
    def opened(settings: Settings) -> Iterator[ScreenDeps]:
        yield ScreenDeps(
            engine=engine,
            sources=HistorySources(NoRanking(), KrHistory(), batch),
            universe={
                Exchange.KOSPI: OneStockUniverse(Member(Exchange.KOSPI, "005930", "삼성전자")),
                Exchange.SP500: OneStockUniverse(Member(Exchange.SP500, "NVDA", "Nvidia")),
            },
        )

    return opened


def _settings() -> Settings:
    # One stock per exchange is a full answer for this test.
    return Settings(screen_kospi_size=1, screen_kosdaq_size=1, screen_sp500_min_size=1)


def test_backfill_builds_the_universe_and_loads_its_history(store: Engine) -> None:
    # given: an empty database
    # when
    code = main(open_job=_open(store, UsBatch()), now=EVENING, settings=_settings())

    # then
    assert code == 0
    with session_scope(store) as session:
        assert [m.symbol for m in members(session, Exchange.KOSPI)] == ["005930"]
        assert [b.day for b in history(session, "005930", D7)] == [D7, D8]
        assert [b.day for b in history(session, "NVDA", D7)] == [D7]


def test_backfill_logs_how_much_was_loaded_and_what_failed(
    store: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    # given: Yahoo does not answer
    # when
    with caplog.at_level(logging.INFO):
        code = main(open_job=_open(store, UsBatch(answer=False)), now=EVENING, settings=_settings())

    # then: a stock that could not be loaded is retried next time, so the exit code stays 0
    assert code == 0
    assert "loaded=1" in caplog.text
    assert "failed=1" in caplog.text
    assert "NVDA" in caplog.text


def test_running_backfill_twice_loads_nothing_the_second_time(
    store: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    # given: a completed run
    main(open_job=_open(store, UsBatch()), now=EVENING, settings=_settings())

    # when
    with caplog.at_level(logging.INFO):
        main(open_job=_open(store, UsBatch()), now=EVENING, settings=_settings())

    # then
    assert "added=0 loaded=0" in caplog.text
    assert "universe rebuilt: none" in caplog.text


def test_backfill_without_database_settings_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given: no APP_DB_* in the environment or in a .env file
    monkeypatch.chdir(tmp_path)
    for key in ("HOST", "NAME", "USER", "PASSWORD"):
        monkeypatch.delenv(f"APP_DB_{key}", raising=False)

    # when
    code = main(settings=Settings())

    # then
    assert code != 0
