"""Alembic environment. The connection URL comes from Settings, never from the ini file."""

from alembic import context
from sqlalchemy import URL, create_engine

from finbrief_analyzer.core.config import get_settings
from finbrief_analyzer.store.tables import metadata as target_metadata


def _url() -> str | URL:
    # Tests set sqlalchemy.url on the Config object to target a throwaway database.
    override = context.config.get_main_option("sqlalchemy.url")
    return override or get_settings().database_url()


def run_migrations() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
