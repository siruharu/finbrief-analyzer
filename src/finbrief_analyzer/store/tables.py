"""Table definitions. Portable types only: tests run on SQLite, the real database is Postgres."""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

REASON_MAX_LENGTH = 500


def _now() -> datetime:
    return datetime.now(UTC)


metadata = MetaData()

recipients = Table(
    "recipients",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("name", String(100), nullable=False, default=""),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_now),
)

delivery_log = Table(
    "delivery_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("brief_date", Date, nullable=False),
    Column("slot", String(20), nullable=False),
    Column("recipient_id", Integer, ForeignKey("recipients.id"), nullable=False),
    Column("channel", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("reason", String(REASON_MAX_LENGTH), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=_now, onupdate=_now),
    # The defence against sending twice. Two processes inserting the same key: one fails.
    UniqueConstraint("brief_date", "slot", "recipient_id", "channel", name="uq_delivery_log_key"),
)

price_bars = Table(
    "price_bars",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("symbol", String(20), nullable=False),
    Column("day", Date, nullable=False),
    # Open, high and low are missing on rows that came from the daily ranking snapshot.
    Column("open", Float, nullable=True),
    Column("high", Float, nullable=True),
    Column("low", Float, nullable=True),
    Column("close", Float, nullable=False),
    # US mega-caps trade more shares in a day than 32 bits hold.
    Column("volume", BigInteger, nullable=False),
    UniqueConstraint("symbol", "day", name="uq_price_bars_symbol_day"),
)

universe_members = Table(
    "universe_members",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("exchange", String(20), nullable=False),
    Column("symbol", String(20), nullable=False),
    Column("name", String(100), nullable=False),
    # Rank inside the exchange when the composition was built.
    Column("position", Integer, nullable=False),
    Column("as_of", Date, nullable=False),
    UniqueConstraint("exchange", "symbol", name="uq_universe_members_exchange_symbol"),
)
