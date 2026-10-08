from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.main import create_app
from finbrief_analyzer.store.tables import metadata, recipients


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def engine() -> Iterator[Engine]:
    # One shared in-memory connection, so every session in a test sees the same database.
    engine = create_engine("sqlite://", poolclass=StaticPool)
    yield engine
    engine.dispose()


@pytest.fixture
def store(engine: Engine) -> Engine:
    """An engine whose database already has the store tables."""
    metadata.create_all(engine)
    return engine


@pytest.fixture
def add_recipient(store: Engine) -> Callable[..., int]:
    """Insert a recipient and return its id."""

    def add(email: str, *, name: str = "", active: bool = True) -> int:
        with session_scope(store) as session:
            row = {"email": email, "name": name, "active": active}
            insert = recipients.insert().values(**row)
            key = session.connection().execute(insert).inserted_primary_key
            assert key is not None
            return int(key[0])

    return add
