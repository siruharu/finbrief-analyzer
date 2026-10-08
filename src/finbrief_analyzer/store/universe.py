"""Which stocks are screened. One composition per exchange, replaced as a whole."""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from finbrief_analyzer.screen.models import Exchange, Member
from finbrief_analyzer.store.tables import universe_members


def replace_members(
    session: Session, exchange: Exchange, new: Iterable[Member], as_of: date
) -> None:
    """Swap the exchange's composition for `new`, keeping the given order."""
    session.execute(delete(universe_members).where(universe_members.c.exchange == exchange.value))
    # A symbol listed twice keeps its first position.
    unique: dict[str, Member] = {}
    for member in new:
        unique.setdefault(member.symbol, member)
    rows = [
        {
            "exchange": exchange.value,
            "symbol": member.symbol,
            "name": member.name,
            "position": position,
            "as_of": as_of,
        }
        for position, member in enumerate(unique.values())
    ]
    if rows:
        session.execute(universe_members.insert(), rows)


def members(session: Session, exchange: Exchange) -> list[Member]:
    query = (
        select(universe_members.c.symbol, universe_members.c.name)
        .where(universe_members.c.exchange == exchange.value)
        .order_by(universe_members.c.position)
    )
    return [Member(exchange, row.symbol, row.name) for row in session.execute(query)]


def built_on(session: Session, exchange: Exchange) -> date | None:
    """The day the stored composition was built, or None if there is none yet."""
    query = select(func.max(universe_members.c.as_of)).where(
        universe_members.c.exchange == exchange.value
    )
    return session.execute(query).scalar_one_or_none()
