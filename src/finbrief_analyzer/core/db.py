"""Engine and session helpers. Nothing here connects at import time."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from finbrief_analyzer.core.config import Settings


def make_engine(settings: Settings) -> Engine:
    """Build an engine from APP_DB_*. The first connection is made on first use."""
    # pool_pre_ping: a one-off job may start right after the database restarted.
    return create_engine(settings.database_url(), pool_pre_ping=True)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A transaction: commit on normal exit, roll back and re-raise on error."""
    with Session(engine) as session, session.begin():
        yield session
