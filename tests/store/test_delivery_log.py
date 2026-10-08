from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, select

from finbrief_analyzer.collect.models import Slot
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.deliver.models import Channel, DeliveryStatus
from finbrief_analyzer.store.delivery_log import (
    REASON_MAX_LENGTH,
    DeliveryKey,
    claim,
    mark_failed,
    mark_sent,
)
from finbrief_analyzer.store.tables import delivery_log, metadata

REPO_ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 10, 8)


@pytest.fixture
def key(add_recipient: Callable[..., int]) -> DeliveryKey:
    recipient_id = add_recipient("a@example.com")
    return DeliveryKey(DAY, Slot.KR_OPEN, recipient_id, Channel.EMAIL)


def _claim(engine: Engine, key: DeliveryKey) -> bool:
    with session_scope(engine) as session:
        return claim(session, key)


def _rows(engine: Engine) -> list[tuple[str, str | None]]:
    with engine.connect() as connection:
        rows = connection.execute(select(delivery_log.c.status, delivery_log.c.reason))
        return [(row.status, row.reason) for row in rows]


def _alembic_config(url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _schema(url: str) -> dict[str, list[str]]:
    inspector = inspect(create_engine(url))
    return {
        table: sorted(column["name"] for column in inspector.get_columns(table))
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


def test_first_claim_succeeds_and_leaves_a_pending_row(store: Engine, key: DeliveryKey) -> None:
    # given: nothing was sent yet
    # when
    claimed = _claim(store, key)

    # then
    assert claimed is True
    assert _rows(store) == [(DeliveryStatus.PENDING, None)]


def test_second_claim_of_the_same_key_is_refused(store: Engine, key: DeliveryKey) -> None:
    # given
    _claim(store, key)

    # when
    claimed = _claim(store, key)

    # then
    assert claimed is False
    assert len(_rows(store)) == 1


def test_refused_claim_keeps_the_rest_of_the_transaction_usable(
    store: Engine, key: DeliveryKey
) -> None:
    # given: the key is taken
    _claim(store, key)
    other = DeliveryKey(DAY, Slot.US_OPEN, key.recipient_id, Channel.EMAIL)

    # when: one transaction hits the conflict and then claims a different key
    with session_scope(store) as session:
        results = (claim(session, key), claim(session, other))

    # then
    assert results == (False, True)
    assert len(_rows(store)) == 2


def test_different_slots_on_the_same_day_are_claimed_separately(
    store: Engine, key: DeliveryKey
) -> None:
    # given
    _claim(store, key)
    us_key = DeliveryKey(DAY, Slot.US_OPEN, key.recipient_id, Channel.EMAIL)

    # when
    claimed = _claim(store, us_key)

    # then
    assert claimed is True


def test_failed_key_can_be_claimed_again(store: Engine, key: DeliveryKey) -> None:
    # given: the first attempt failed
    _claim(store, key)
    with session_scope(store) as session:
        mark_failed(session, key, "smtp timeout")

    # when
    claimed = _claim(store, key)

    # then: the same row is pending again, not duplicated
    assert claimed is True
    assert _rows(store) == [(DeliveryStatus.PENDING, None)]


def test_sent_key_cannot_be_claimed_again(store: Engine, key: DeliveryKey) -> None:
    # given
    _claim(store, key)
    with session_scope(store) as session:
        mark_sent(session, key)

    # when
    claimed = _claim(store, key)

    # then
    assert claimed is False
    assert _rows(store) == [(DeliveryStatus.SENT, None)]


def test_pending_key_left_by_a_dead_process_is_not_claimed_again(
    store: Engine, key: DeliveryKey
) -> None:
    # given: claimed, then the process died before recording a result
    _claim(store, key)

    # when / then: a missed briefing is preferred over a duplicate
    assert _claim(store, key) is False


def test_mark_failed_stores_the_reason(store: Engine, key: DeliveryKey) -> None:
    # given
    _claim(store, key)

    # when
    with session_scope(store) as session:
        mark_failed(session, key, "smtp timeout")

    # then
    assert _rows(store) == [(DeliveryStatus.FAILED, "smtp timeout")]


def test_mark_failed_cuts_an_overlong_reason(store: Engine, key: DeliveryKey) -> None:
    # given
    _claim(store, key)

    # when
    with session_scope(store) as session:
        mark_failed(session, key, "x" * (REASON_MAX_LENGTH + 50))

    # then
    reason = _rows(store)[0][1]
    assert reason is not None
    assert len(reason) == REASON_MAX_LENGTH


def test_migration_downgrade_then_upgrade_gives_the_same_schema(tmp_path: Path) -> None:
    # given: a database migrated to head
    url = f"sqlite:///{(tmp_path / 'roundtrip.db').as_posix()}"
    config = _alembic_config(url)
    command.upgrade(config, "head")
    before = _schema(url)

    # when
    command.downgrade(config, "base")
    emptied = _schema(url)
    command.upgrade(config, "head")

    # then
    assert emptied == {}
    assert _schema(url) == before


def test_migrated_schema_has_the_same_columns_as_the_table_definitions(tmp_path: Path) -> None:
    # given
    url = f"sqlite:///{(tmp_path / 'head.db').as_posix()}"

    # when
    command.upgrade(_alembic_config(url), "head")

    # then
    expected = {
        table.name: sorted(column.name for column in table.columns)
        for table in metadata.sorted_tables
    }
    assert _schema(url) == expected
