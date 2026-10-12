"""Delivery records. `claim` is what keeps a briefing from being sent twice."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Self

from sqlalchemy import ColumnElement, Engine, and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from finbrief_analyzer.collect.models import Slot
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.deliver.models import Briefing, Channel, DeliveryStatus
from finbrief_analyzer.store.tables import REASON_MAX_LENGTH, delivery_log

__all__ = [
    "REASON_MAX_LENGTH",
    "DeliveryKey",
    "DeliveryLog",
    "claim",
    "mark_failed",
    "mark_sent",
    "waiting",
]


@dataclass(frozen=True, slots=True)
class DeliveryKey:
    """One briefing to one recipient over one channel."""

    brief_date: date
    slot: Slot
    recipient_id: int
    channel: Channel

    @classmethod
    def for_email(cls, briefing: Briefing, recipient_id: int) -> Self:
        return cls(briefing.briefing_date, briefing.slot, recipient_id, Channel.EMAIL)


def _matches(key: DeliveryKey) -> ColumnElement[bool]:
    return and_(
        delivery_log.c.brief_date == key.brief_date,
        delivery_log.c.slot == key.slot.value,
        delivery_log.c.recipient_id == key.recipient_id,
        delivery_log.c.channel == key.channel.value,
    )


def claim(session: Session, key: DeliveryKey) -> bool:
    """Reserve the right to send. False means someone else has it or it was already sent.

    Insert first and let the unique constraint decide; a read-then-insert would race.
    A row left pending by a dead process stays claimed: a missed briefing over a duplicate.
    """
    row = {
        "brief_date": key.brief_date,
        "slot": key.slot.value,
        "recipient_id": key.recipient_id,
        "channel": key.channel.value,
        "status": DeliveryStatus.PENDING.value,
    }
    try:
        # Savepoint, so the conflict does not abort the caller's transaction.
        with session.begin_nested():
            session.execute(delivery_log.insert().values(**row))
    except IntegrityError:
        return _reopen_failed(session, key)
    return True


def _reopen_failed(session: Session, key: DeliveryKey) -> bool:
    """Take over a key whose last attempt failed. Check and update are one statement."""
    # Through the connection: it returns a CursorResult, which is what carries rowcount.
    reopened = session.connection().execute(
        update(delivery_log)
        .where(_matches(key), delivery_log.c.status == DeliveryStatus.FAILED.value)
        .values(status=DeliveryStatus.PENDING.value, reason=None)
    )
    return reopened.rowcount == 1


def mark_sent(session: Session, key: DeliveryKey) -> None:
    session.execute(
        update(delivery_log)
        .where(_matches(key))
        .values(status=DeliveryStatus.SENT.value, reason=None)
    )


def mark_failed(session: Session, key: DeliveryKey, reason: str) -> None:
    """Record a failure. Pass a short description, never a raw exception message."""
    session.execute(
        update(delivery_log)
        .where(_matches(key))
        .values(status=DeliveryStatus.FAILED.value, reason=reason[:REASON_MAX_LENGTH])
    )


def waiting(
    session: Session,
    brief_date: date,
    slot: Slot,
    channel: Channel,
    recipient_ids: Sequence[int],
) -> list[int]:
    """The recipients a run could still claim: no row yet, or the last attempt failed.

    Mirrors `claim`: a pending row counts as taken, so this never says "waiting" for someone
    another process is sending to right now.
    """
    if not recipient_ids:
        return []
    taken = session.execute(
        select(delivery_log.c.recipient_id).where(
            delivery_log.c.brief_date == brief_date,
            delivery_log.c.slot == slot.value,
            delivery_log.c.channel == channel.value,
            delivery_log.c.recipient_id.in_(recipient_ids),
            delivery_log.c.status != DeliveryStatus.FAILED.value,
        )
    )
    done = {row.recipient_id for row in taken}
    return [recipient_id for recipient_id in recipient_ids if recipient_id not in done]


class DeliveryLog:
    """The log bound to an engine. Every call is its own committed transaction.

    A claim has to be committed before the mail goes out, or a second process would not see it.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim(self, key: DeliveryKey) -> bool:
        with session_scope(self._engine) as session:
            return claim(session, key)

    def waiting(
        self, brief_date: date, slot: Slot, channel: Channel, recipient_ids: Sequence[int]
    ) -> list[int]:
        with session_scope(self._engine) as session:
            return waiting(session, brief_date, slot, channel, recipient_ids)

    def mark_sent(self, key: DeliveryKey) -> None:
        with session_scope(self._engine) as session:
            mark_sent(session, key)

    def mark_failed(self, key: DeliveryKey, reason: str) -> None:
        with session_scope(self._engine) as session:
            mark_failed(session, key, reason)
