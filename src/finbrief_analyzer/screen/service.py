"""Screening end to end: bring the history up to date, apply the rules, report the hits."""

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

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
from finbrief_analyzer.screen.us_names import NaverUsNames
from finbrief_analyzer.store.price_bars import histories
from finbrief_analyzer.store.universe import members

logger = logging.getLogger(__name__)

KR_GROUP = (Exchange.KOSPI, Exchange.KOSDAQ)
US_GROUP = (Exchange.SP500,)
# Float slack for "closed exactly at the 52-week high".
NEW_HIGH = 1.0 - 1e-9


def _is_new_high(score: Score) -> bool:
    # At the high, not near it: a stock at 98% of its high has not made a new high.
    return score.score >= NEW_HIGH


def _closed_up(score: Score) -> bool:
    # Heavy volume on a falling day is a different event; it is not reported here.
    return score.change_pct is not None and score.change_pct > 0


@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule: Rule
    score: Callable[[Sequence[Bar]], float | None]
    # Which scored stocks count as meeting the rule.
    meets: Callable[[Score], bool]


RULES = (
    RuleSpec(Rule.HIGH_52W, high_ratio, _is_new_high),
    RuleSpec(Rule.VOLUME_SPIKE, volume_ratio, _closed_up),
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
        Exchange.SP500: Sp500UniverseSource(names=NaverUsNames(client).fetch),
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
    return [_apply(spec, current, names, exchanges, as_of, top) for spec in RULES]


def _liquid(history: Sequence[Bar], min_value: float) -> bool:
    value = trading_value(history)
    return value is not None and value >= min_value


def _apply(
    spec: RuleSpec,
    current: Mapping[str, Sequence[Bar]],
    names: Mapping[str, str],
    exchanges: tuple[Exchange, ...],
    as_of: date,
    top: int,
) -> ScreenResult:
    scores = [
        Score(symbol, value, change_pct(history))
        for symbol, history in current.items()
        if (value := spec.score(history)) is not None
    ]
    met = [score for score in scores if spec.meets(score)]
    hits = tuple(
        ScreenHit(s.symbol, names[s.symbol], current[s.symbol][-1].close, s.change_pct, s.score)
        for s in rank(met, top)
    )
    return ScreenResult(spec.rule, exchanges, as_of, hits, matched=len(met))


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
