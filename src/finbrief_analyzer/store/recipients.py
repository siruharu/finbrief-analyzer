"""Who receives the briefing."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbrief_analyzer.store.tables import recipients


@dataclass(frozen=True, slots=True)
class Recipient:
    id: int
    email: str
    name: str


def list_active(session: Session) -> list[Recipient]:
    """Active recipients in registration order."""
    query = (
        select(recipients.c.id, recipients.c.email, recipients.c.name)
        .where(recipients.c.active.is_(True))
        .order_by(recipients.c.id)
    )
    return [Recipient(id=row.id, email=row.email, name=row.name) for row in session.execute(query)]
