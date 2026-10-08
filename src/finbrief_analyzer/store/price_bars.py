"""Daily price history. Rows are only ever added; a stock is re-loaded by deleting it first."""

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import Row, delete, func, select
from sqlalchemy.orm import Session

from finbrief_analyzer.screen.models import Bar
from finbrief_analyzer.store.tables import price_bars


def add_bars(session: Session, bars: Iterable[Bar]) -> int:
    """Insert the bars whose (symbol, day) is not stored yet. Returns how many were added.

    Reads first, then inserts: portable across SQLite and Postgres, and safe because
    only one job writes history at a time.
    """
    by_symbol: dict[str, dict[date, Bar]] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, {}).setdefault(bar.day, bar)
    added = 0
    for symbol, by_day in by_symbol.items():
        stored = _stored_days(session, symbol, by_day)
        rows = [_row(bar) for day, bar in by_day.items() if day not in stored]
        if rows:
            session.execute(price_bars.insert(), rows)
            added += len(rows)
    return added


def _stored_days(session: Session, symbol: str, days: Iterable[date]) -> set[date]:
    query = select(price_bars.c.day).where(
        price_bars.c.symbol == symbol, price_bars.c.day.in_(list(days))
    )
    return set(session.execute(query).scalars())


def _row(bar: Bar) -> dict[str, object]:
    return {
        "symbol": bar.symbol,
        "day": bar.day,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def history(session: Session, symbol: str, since: date) -> list[Bar]:
    """Bars of one stock from `since` on, oldest first."""
    query = (
        select(price_bars)
        .where(price_bars.c.symbol == symbol, price_bars.c.day >= since)
        .order_by(price_bars.c.day)
    )
    return [_bar(row) for row in session.execute(query)]


def _bar(row: Row[Any]) -> Bar:  # Any: the row's columns are only known at runtime
    return Bar(row.symbol, row.day, row.close, row.volume, row.open, row.high, row.low)


def last_days(session: Session, symbols: Sequence[str]) -> dict[str, date]:
    """The latest stored day of each symbol. Symbols without history are absent."""
    if not symbols:
        return {}
    query = (
        select(price_bars.c.symbol, func.max(price_bars.c.day))
        .where(price_bars.c.symbol.in_(symbols))
        .group_by(price_bars.c.symbol)
    )
    return {symbol: day for symbol, day in session.execute(query)}


def last_bars(session: Session, symbols: Sequence[str]) -> dict[str, Bar]:
    """The latest stored bar of each symbol. Symbols without history are absent."""
    if not symbols:
        return {}
    latest = (
        select(price_bars.c.symbol, func.max(price_bars.c.day).label("day"))
        .where(price_bars.c.symbol.in_(symbols))
        .group_by(price_bars.c.symbol)
        .subquery()
    )
    query = select(price_bars).join(
        latest,
        (price_bars.c.symbol == latest.c.symbol) & (price_bars.c.day == latest.c.day),
    )
    return {row.symbol: _bar(row) for row in session.execute(query)}


def delete_symbol(session: Session, symbol: str) -> None:
    session.execute(delete(price_bars).where(price_bars.c.symbol == symbol))
