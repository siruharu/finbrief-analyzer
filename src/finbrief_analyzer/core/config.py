"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from finbrief_analyzer.collect.models import Market


class QuoteSymbol(BaseModel):
    """A symbol to collect, with the label and market the briefing shows it under."""

    symbol: str
    name: str
    market: Market


# Confirmed in docs/01_research/2026-10-07_data-source-poc.md. KS11/KQ11 return stale data.
DEFAULT_QUOTE_SYMBOLS = (
    QuoteSymbol(symbol="^KS11", name="KOSPI", market=Market.KR),
    QuoteSymbol(symbol="^KQ11", name="KOSDAQ", market=Market.KR),
    QuoteSymbol(symbol="US500", name="S&P 500", market=Market.US),
    QuoteSymbol(symbol="IXIC", name="나스닥", market=Market.US),
    QuoteSymbol(symbol="DJI", name="다우존스", market=Market.US),
    QuoteSymbol(symbol="US10YT", name="미 국채 10년", market=Market.RATE),
)

DEFAULT_KR_RSS_FEEDS = (
    "https://www.hankyung.com/feed/economy",
    "https://www.hankyung.com/feed/finance",
    "https://www.mk.co.kr/rss/30100041/",
    "https://www.mk.co.kr/rss/50200011/",
    "https://www.yna.co.kr/rss/economy.xml",
    "https://www.yna.co.kr/rss/market.xml",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    name: str = "finbrief-analyzer"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # A provider whose key is None is disabled; collection skips it instead of failing.
    marketaux_token: SecretStr | None = None
    dart_api_key: SecretStr | None = None
    ecos_api_key: SecretStr | None = None

    # List-valued variables are JSON arrays in the environment.
    quote_symbols: tuple[QuoteSymbol, ...] = DEFAULT_QUOTE_SYMBOLS
    kr_rss_feeds: tuple[str, ...] = DEFAULT_KR_RSS_FEEDS

    # Marketaux free plan: 3 articles per request, 100 requests a day, two slots a day.
    marketaux_max_calls_per_slot: int = Field(default=3, ge=1, le=50)
    # Marketaux timed out at 15s in the PoC, and a timed-out request still costs quota.
    http_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("marketaux_token", "dart_api_key", "ecos_api_key", mode="before")
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is read once per process."""
    return Settings()
