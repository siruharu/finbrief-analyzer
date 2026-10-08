"""Keep the stored daily bars current: first load, daily append, re-load on a mismatch.

Only completed sessions are stored. A stock whose stored prices no longer line up with
what the source says now (a split, an adjustment, missed days) is loaded again whole.
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from sqlalchemy import Engine

from finbrief_analyzer.collect.models import CollectError, Market
from finbrief_analyzer.collect.service import expected_session
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.models import Bar, Exchange, Member
from finbrief_analyzer.screen.ranking import RankRow
from finbrief_analyzer.screen.sources import BatchResult, rank_bar
from finbrief_analyzer.screen.universe import pages_for
from finbrief_analyzer.store.price_bars import add_bars, delete_symbol, last_bars
from finbrief_analyzer.store.universe import members

logger = logging.getLogger(__name__)

KR_EXCHANGES = (Exchange.KOSPI, Exchange.KOSDAQ)
# Relative difference beyond which stored and fetched closes are "not the same price".
TOLERANCE = 0.005
# A longer silence than a long weekend means days were missed, not that nothing traded.
MAX_GAP_DAYS = 4


class RankingSource(Protocol):
    def fetch(self, exchange: Exchange, pages: int) -> list[RankRow]: ...


class HistorySource(Protocol):
    def history(self, symbol: str, since: date) -> list[Bar]: ...


class BatchSource(Protocol):
    def fetch(self, symbols: Sequence[str], since: date) -> BatchResult: ...


@dataclass(frozen=True, slots=True)
class HistorySources:
    ranking: RankingSource
    kr_history: HistorySource
    us_batch: BatchSource


@dataclass(frozen=True, slots=True)
class UpdateReport:
    added: int = 0
    # Stocks loaded whole: for the first time, or again after a mismatch.
    loaded: int = 0
    reloaded: int = 0
    failed: tuple[str, ...] = ()
    # Left for the next run because the time limit was reached.
    skipped: int = 0


@dataclass(slots=True)
class _Tally:
    added: int = 0
    loaded: int = 0
    reloaded: int = 0
    failed: list[str] = field(default_factory=list)
    skipped: int = 0

    def report(self) -> UpdateReport:
        return UpdateReport(
            self.added, self.loaded, self.reloaded, tuple(self.failed), self.skipped
        )


def differs(stored: float, fetched: float) -> bool:
    return abs(stored - fetched) > TOLERANCE * max(abs(stored), abs(fetched))


def update_history(
    engine: Engine,
    sources: HistorySources,
    now: datetime,
    history_days: int,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> UpdateReport:
    """Bring every universe member up to the last completed session. Never raises for a source."""
    since = now.date() - timedelta(days=history_days)
    tally = _Tally()

    def expired() -> bool:
        return deadline is not None and clock() >= deadline

    with session_scope(engine) as session:
        kr = [member for exchange in KR_EXCHANGES for member in members(session, exchange)]
        us = members(session, Exchange.SP500)
    _update_kr(engine, kr, sources, now, since, tally, expired)
    if expired():
        tally.skipped += len(us)
    else:
        _update_us(engine, us, sources.us_batch, now, since, tally)
    return tally.report()


def _update_kr(
    engine: Engine,
    universe: Sequence[Member],
    sources: HistorySources,
    now: datetime,
    since: date,
    tally: _Tally,
    expired: Callable[[], bool],
) -> None:
    settled = expected_session(Market.KR, now)
    symbols = [member.symbol for member in universe]
    with session_scope(engine) as session:
        stored = last_bars(session, symbols)
    rows = _settled_rows(sources.ranking, universe, settled)
    for symbol in symbols:
        last, row = stored.get(symbol), rows.get(symbol)
        if last is not None and (last.day >= settled or (row and row.traded_on <= last.day)):
            continue  # up to date, or the stock has not traded since
        if last is not None and row is not None and _continues(last, row):
            _store(engine, [rank_bar(row)], tally)
        elif expired():
            tally.skipped += 1
        else:
            _load_kr(engine, symbol, sources.kr_history, since, settled, last is not None, tally)


def _settled_rows(
    ranking: RankingSource, universe: Sequence[Member], settled: date
) -> dict[str, RankRow]:
    """Today's ranking rows that belong to a completed session. Empty if the source fails."""
    rows: dict[str, RankRow] = {}
    for exchange in KR_EXCHANGES:
        size = sum(1 for member in universe if member.exchange is exchange)
        try:
            found = ranking.fetch(exchange, pages_for(size)) if size else []
        except CollectError as error:
            logger.warning("ranking unavailable, falling back to per-stock history: %s", error)
            continue
        # A row dated after the settled session is a session still in progress.
        rows.update({row.code: row for row in found if row.traded_on <= settled})
    return rows


def _continues(last: Bar, row: RankRow) -> bool:
    """Whether the ranking row is simply the next day after what is stored."""
    gap = (row.traded_on - last.day).days
    return 0 < gap <= MAX_GAP_DAYS and not differs(last.close, row.prev_close)


def _load_kr(
    engine: Engine,
    symbol: str,
    source: HistorySource,
    since: date,
    settled: date,
    replace: bool,
    tally: _Tally,
) -> None:
    try:
        bars = [bar for bar in source.history(symbol, since) if bar.day <= settled]
    except CollectError as error:
        logger.warning("history skipped: %s", error)
        tally.failed.append(symbol)
        return
    _store(engine, bars, tally, replace=[symbol] if replace else [])
    tally.reloaded += replace
    tally.loaded += not replace


def _update_us(
    engine: Engine,
    universe: Sequence[Member],
    source: BatchSource,
    now: datetime,
    since: date,
    tally: _Tally,
) -> None:
    settled = expected_session(Market.US, now)
    symbols = [member.symbol for member in universe]
    with session_scope(engine) as session:
        stored = last_bars(session, symbols)
    fresh = [symbol for symbol in symbols if symbol not in stored]
    stale = [symbol for symbol in symbols if symbol in stored and stored[symbol].day < settled]
    again = _append_recent(engine, stale, stored, source, settled, tally)
    _load_us(engine, fresh, again, source, since, settled, tally)


def _append_recent(
    engine: Engine,
    stale: Sequence[str],
    stored: dict[str, Bar],
    source: BatchSource,
    settled: date,
    tally: _Tally,
) -> list[str]:
    """Append the new days of stocks that have history. Returns the ones to load again."""
    if not stale:
        return []
    # From the oldest stored last day, so every stock's last stored day is in the answer.
    result = source.fetch(stale, min(stored[symbol].day for symbol in stale))
    tally.failed += result.failed
    again: list[str] = []
    for symbol, bars in result.bars.items():
        last = stored[symbol]
        overlap = next((bar for bar in bars if bar.day == last.day), None)
        if overlap is None or differs(last.close, overlap.close):
            again.append(symbol)
            continue
        _store(engine, [bar for bar in bars if last.day < bar.day <= settled], tally)
    return again


def _load_us(
    engine: Engine,
    fresh: Sequence[str],
    again: Sequence[str],
    source: BatchSource,
    since: date,
    settled: date,
    tally: _Tally,
) -> None:
    wanted = [*fresh, *again]
    if not wanted:
        return
    result = source.fetch(wanted, since)
    tally.failed += result.failed
    for symbol, bars in result.bars.items():
        replace = symbol in again
        _store(
            engine,
            [bar for bar in bars if bar.day <= settled],
            tally,
            replace=[symbol] if replace else [],
        )
        tally.reloaded += replace
        tally.loaded += not replace


def _store(engine: Engine, bars: Sequence[Bar], tally: _Tally, replace: Sequence[str] = ()) -> None:
    """One transaction per stock: an interrupted first load keeps what it already has."""
    with session_scope(engine) as session:
        for symbol in replace:
            # Fetched first, deleted now: a failed fetch never costs the stored history.
            delete_symbol(session, symbol)
        tally.added += add_bars(session, bars)
