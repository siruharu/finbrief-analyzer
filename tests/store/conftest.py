from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine() -> Iterator[Engine]:
    # One shared in-memory connection, so every session in a test sees the same database.
    engine = create_engine("sqlite://", poolclass=StaticPool)
    yield engine
    engine.dispose()
