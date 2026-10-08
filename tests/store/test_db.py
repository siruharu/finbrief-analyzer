from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Column, Engine, Integer, MetaData, Table, create_engine, inspect, select

from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.core.db import make_engine, session_scope

REPO_ROOT = Path(__file__).resolve().parents[2]

metadata = MetaData()
numbers = Table("numbers", metadata, Column("value", Integer, primary_key=True))


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings reads ".env" relative to the working directory; keep the developer's file out.
    monkeypatch.chdir(tmp_path)
    for key in ("HOST", "PORT", "NAME", "USER", "PASSWORD"):
        monkeypatch.delenv(f"APP_DB_{key}", raising=False)


def _db_settings(password: str = "pw") -> Settings:
    return Settings(
        db_host="db.local", db_name="finbrief", db_user="app", db_password=SecretStr(password)
    )


def _stored_values(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        return list(connection.execute(select(numbers.c.value)).scalars())


def test_database_url_is_assembled_when_all_db_settings_are_present() -> None:
    # given
    settings = _db_settings()

    # when
    url = settings.database_url()

    # then
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database, url.username) == ("db.local", 5432, "finbrief", "app")


def test_database_url_keeps_reserved_characters_in_the_password_intact() -> None:
    # given: a password that would break a hand-built URL string
    settings = _db_settings(password="p@ss/w:rd")

    # when
    url = settings.database_url()

    # then
    assert url.password == "p@ss/w:rd"
    assert url.host == "db.local"


def test_db_password_is_hidden_from_settings_repr_and_from_the_printed_url() -> None:
    # given
    settings = _db_settings(password="very-secret-pw")

    # when / then
    assert "very-secret-pw" not in repr(settings)
    assert "very-secret-pw" not in str(settings.database_url())


def test_partial_db_settings_fail_naming_the_missing_variables() -> None:
    # given: only the host is configured
    settings = Settings(db_host="db.local")

    # when / then
    with pytest.raises(ValueError, match="APP_DB_NAME") as raised:
        settings.database_url()
    assert "APP_DB_USER" in str(raised.value)
    assert "APP_DB_PASSWORD" in str(raised.value)
    assert "APP_DB_HOST" not in str(raised.value)


def test_make_engine_does_not_connect_until_used() -> None:
    # given: a host that does not exist
    settings = _db_settings()

    # when
    engine = make_engine(settings)

    # then: building the engine alone raised nothing
    assert engine.url.host == "db.local"


def test_session_scope_commits_on_normal_exit(engine: Engine) -> None:
    # given
    metadata.create_all(engine)

    # when
    with session_scope(engine) as session:
        session.execute(numbers.insert().values(value=1))

    # then
    assert _stored_values(engine) == [1]


def test_session_scope_rolls_back_and_reraises_on_error(engine: Engine) -> None:
    # given
    metadata.create_all(engine)

    # when
    with pytest.raises(RuntimeError, match="boom"), session_scope(engine) as session:
        session.execute(numbers.insert().values(value=1))
        raise RuntimeError("boom")

    # then
    assert _stored_values(engine) == []


def test_app_and_health_work_without_db_settings(client: TestClient) -> None:
    # given: no APP_DB_* variable is set
    # when
    response = client.get("/health")

    # then
    assert response.status_code == 200


def test_migrations_apply_to_an_empty_database_up_to_head(tmp_path: Path) -> None:
    # given: an empty database file
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)

    # when
    command.upgrade(config, "head")

    # then
    assert "alembic_version" in inspect(create_engine(url)).get_table_names()
