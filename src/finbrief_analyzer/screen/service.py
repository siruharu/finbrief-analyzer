"""Screening end to end: bring the history up to date, apply the rules, report the hits."""

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlalchemy import Engine

from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.history import HistorySources, update_history
from finbrief_analyzer.screen.models import Bar, Exchange, Member, Rule, ScreenHit, ScreenResult
from finbrief_analyzer.screen.ranking import NaverRanking
from finbrief_analyzer.screen.rules import (
    Score,
    change_pct,
    high_ratio,
    rank,
    trading_value,
    volume_ratio,
)
from finbrief_analyzer.screen.sources import FdrHistorySource, YfBatchSource
from finbrief_analyzer.screen.universe import (
    NaverUniverseSource,
    Sp500UniverseSource,
    UniverseSource,
    refresh_universe,
)
from finbrief_analyzer.store.price_bars import histories
from finbrief_analyzer.store.universe import members

logger = logging.getLogger(__name__)

KR_GROUP = (Exchange.KOSPI, Exchange.KOSDAQ)
US_GROUP = (Exchange.SP500,)
RULES: tuple[tuple[Rule, Callable[[Sequence[Bar]], float | None]], ...] = (
    (Rule.HIGH_52W, high_ratio),
    (Rule.VOLUME_SPIKE, volume_ratio),
)


@dataclass(frozen=True, slots=True)
class ScreenDeps:
    """What the price history is built from."""

    engine: Engine
    sources: HistorySources
    universe: Mapping[Exchange, UniverseSource]


def build_screen_deps(settings: Settings, engine: Engine, client: httpx.Client) -> ScreenDeps:
    """Wire the real sources. The caller owns the engine and the client."""
    ranking = NaverRanking(client)
    korean = NaverUniverseSource(ranking)
    batch = YfBatchSource(
        batch_size=settings.screen_batch_size, pause_seconds=settings.screen_batch_pause_seconds
    )
    universe: dict[Exchange, UniverseSource] = {
        Exchange.KOSPI: korean,
        Exchange.KOSDAQ: korean,
        Exchange.SP500: Sp500UniverseSource(),
    }
    return ScreenDeps(engine, HistorySources(ranking, FdrHistorySource(), batch), universe)


def screen_group(
    universe: Sequence[Member],
    bars: Mapping[str, Sequence[Bar]],
    exchanges: tuple[Exchange, ...],
    top: int,
    min_value: float,
) -> list[ScreenResult]:
    """Apply every rule to one group of stocks. Pure: no database, no clock."""
    last_days = [history[-1].day for history in bars.values() if history]
    if not last_days:
        return []
    as_of = max(last_days)
    names = {member.symbol: member.name for member in universe}
    # A stock that did not trade on the latest day has nothing to report for it.
    current = {
        symbol: history
        for symbol, history in bars.items()
        if symbol in names and history and history[-1].day == as_of and _liquid(history, min_value)
    }
    return [
        ScreenResult(rule, exchanges, as_of, _hits(current, names, score, top))
        for rule, score in RULES
    ]


def _liquid(history: Sequence[Bar], min_value: float) -> bool:
    value = trading_value(history)
    return value is not None and value >= min_value


def _hits(
    current: Mapping[str, Sequence[Bar]],
    names: Mapping[str, str],
    score: Callable[[Sequence[Bar]], float | None],
    top: int,
) -> tuple[ScreenHit, ...]:
    scores = [
        Score(symbol, value, change_pct(history))
        for symbol, history in current.items()
        if (value := score(history)) is not None
    ]
    return tuple(
        ScreenHit(s.symbol, names[s.symbol], current[s.symbol][-1].close, s.change_pct, s.score)
        for s in rank(scores, top)
    )


class ScreenService:
    def __init__(
        self, deps: ScreenDeps, settings: Settings, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._deps = deps
        self._settings = settings
        self._clock = clock

    def run(self, now: datetime) -> tuple[ScreenResult, ...]:
        """Update the history within the time limit, then screen both groups."""
        settings, engine = self._settings, self._deps.engine
        with session_scope(engine) as session:
            refresh_universe(session, now.date(), self._deps.universe, settings.universe_sizes())
        deadline = self._clock() + settings.screen_update_seconds
        report = update_history(
            engine, self._deps.sources, now, settings.screen_history_days, deadline, self._clock
        )
        logger.info(
            "price history: added=%d loaded=%d reloaded=%d failed=%d skipped=%d",
            report.added,
            report.loaded,
            report.reloaded,
            len(report.failed),
            report.skipped,
        )
        since = now.date() - timedelta(days=settings.screen_history_days)
        groups = (
            (KR_GROUP, settings.screen_min_trading_value_krw),
            (US_GROUP, settings.screen_min_trading_value_usd),
        )
        results: list[ScreenResult] = []
        with session_scope(engine) as session:
            for exchanges, min_value in groups:
                universe = [m for exchange in exchanges for m in members(session, exchange)]
                bars = histories(session, [m.symbol for m in universe], since)
                results += screen_group(universe, bars, exchanges, settings.screen_top, min_value)
        return tuple(results)


def build_screen_service(
    settings: Settings, engine: Engine, client: httpx.Client
) -> ScreenService | None:
    """The screening step for the briefing job, or None when it is turned off."""
    if not settings.screen_enabled:
        return None
    return ScreenService(build_screen_deps(settings, engine, client), settings)
