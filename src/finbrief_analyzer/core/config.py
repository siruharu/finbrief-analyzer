"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from finbrief_analyzer.collect.models import Market
from finbrief_analyzer.screen.models import Exchange


class QuoteSymbol(BaseModel):
    """A symbol to collect, with the label and market the briefing shows it under."""

    symbol: str
    name: str
    market: Market
    # Multiplier for display: JPY/KRW is quoted per yen but read per 100 yen.
    scale: float = 1.0


# Confirmed in docs/01_research/2026-10-07_data-source-poc.md and 2026-10-08_quote-symbols-poc.md.
# KS11/KQ11 return stale data. Korean rates and the USD/KRW base rate come from ECOS, not here.
DEFAULT_QUOTE_SYMBOLS = (
    QuoteSymbol(symbol="^KS11", name="KOSPI", market=Market.KR),
    QuoteSymbol(symbol="^KQ11", name="KOSDAQ", market=Market.KR),
    QuoteSymbol(symbol="US500", name="S&P 500", market=Market.US),
    QuoteSymbol(symbol="IXIC", name="나스닥", market=Market.US),
    QuoteSymbol(symbol="DJI", name="다우존스", market=Market.US),
    QuoteSymbol(symbol="^SOX", name="필라델피아 반도체", market=Market.US),
    QuoteSymbol(symbol="^RUT", name="러셀 2000", market=Market.US),
    QuoteSymbol(symbol="^VIX", name="VIX", market=Market.US),
    QuoteSymbol(symbol="^N225", name="닛케이 225", market=Market.ASIA),
    QuoteSymbol(symbol="SSEC", name="상하이종합", market=Market.ASIA),
    QuoteSymbol(symbol="^HSI", name="항셍", market=Market.ASIA),
    QuoteSymbol(symbol="US10YT", name="미 국채 10년", market=Market.RATE),
    QuoteSymbol(symbol="DX-Y.NYB", name="달러 인덱스", market=Market.FX),
    QuoteSymbol(symbol="USD/JPY", name="엔/달러", market=Market.FX),
    QuoteSymbol(symbol="JPY/KRW", name="원/100엔", market=Market.FX, scale=100),
    QuoteSymbol(symbol="EUR/USD", name="유로/달러", market=Market.FX),
    QuoteSymbol(symbol="CL=F", name="WTI", market=Market.COMMODITY),
    QuoteSymbol(symbol="GC=F", name="금", market=Market.COMMODITY),
    QuoteSymbol(symbol="HG=F", name="구리", market=Market.COMMODITY),
    QuoteSymbol(symbol="BTC/USD", name="비트코인", market=Market.COMMODITY),
)

# Ten largest common stocks per country on 2026-10-08, see
# docs/01_research/2026-10-08_screening-poc.md. A fixed list: it does not follow the ranking.
DEFAULT_WATCHLIST = (
    QuoteSymbol(symbol="005930", name="삼성전자", market=Market.KR_STOCK),
    QuoteSymbol(symbol="000660", name="SK하이닉스", market=Market.KR_STOCK),
    QuoteSymbol(symbol="402340", name="SK스퀘어", market=Market.KR_STOCK),
    QuoteSymbol(symbol="009150", name="삼성전기", market=Market.KR_STOCK),
    QuoteSymbol(symbol="373220", name="LG에너지솔루션", market=Market.KR_STOCK),
    QuoteSymbol(symbol="005380", name="현대차", market=Market.KR_STOCK),
    QuoteSymbol(symbol="105560", name="KB금융", market=Market.KR_STOCK),
    QuoteSymbol(symbol="207940", name="삼성바이오로직스", market=Market.KR_STOCK),
    QuoteSymbol(symbol="032830", name="삼성생명", market=Market.KR_STOCK),
    QuoteSymbol(symbol="028260", name="삼성물산", market=Market.KR_STOCK),
    QuoteSymbol(symbol="NVDA", name="엔비디아", market=Market.US_STOCK),
    QuoteSymbol(symbol="AAPL", name="애플", market=Market.US_STOCK),
    QuoteSymbol(symbol="GOOGL", name="알파벳", market=Market.US_STOCK),
    QuoteSymbol(symbol="MSFT", name="마이크로소프트", market=Market.US_STOCK),
    QuoteSymbol(symbol="AMZN", name="아마존", market=Market.US_STOCK),
    QuoteSymbol(symbol="META", name="메타", market=Market.US_STOCK),
    QuoteSymbol(symbol="AVGO", name="브로드컴", market=Market.US_STOCK),
    QuoteSymbol(symbol="TSLA", name="테슬라", market=Market.US_STOCK),
    QuoteSymbol(symbol="BRK-B", name="버크셔 해서웨이", market=Market.US_STOCK),
    QuoteSymbol(symbol="LLY", name="일라이 릴리", market=Market.US_STOCK),
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
    # Individual stocks shown under their own headings. An empty array turns them off.
    watchlist: tuple[QuoteSymbol, ...] = DEFAULT_WATCHLIST
    kr_rss_feeds: tuple[str, ...] = DEFAULT_KR_RSS_FEEDS

    # Marketaux free plan: 3 articles per request, 100 requests a day, two slots a day.
    marketaux_max_calls_per_slot: int = Field(default=3, ge=1, le=50)
    # Marketaux timed out at 15s in the PoC, and a timed-out request still costs quota.
    http_timeout_seconds: float = Field(default=30.0, gt=0)

    # Screening universe: the largest common stocks by market value.
    screen_kospi_size: int = Field(default=200, ge=1)
    screen_kosdaq_size: int = Field(default=150, ge=1)
    # The S&P 500 is taken whole; a listing shorter than this is treated as a partial answer.
    screen_sp500_min_size: int = Field(default=400, ge=1)

    # US bars come from Yahoo in batches. Sizes measured in the screening PoC.
    screen_batch_size: int = Field(default=100, ge=1)
    screen_batch_pause_seconds: float = Field(default=1.0, ge=0)
    # First load: the 52-week rule needs a little more than a year of history.
    screen_history_days: int = Field(default=400, ge=375)

    # Optional as a group: the web app starts without a database, the briefing job needs it.
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_password: SecretStr | None = None

    # Gmail with an app password. Unset means the briefing job cannot send.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_timeout_seconds: float = Field(default=30.0, gt=0)
    mail_from_name: str = "finbrief"
    # Gets a notice when a briefing could not be sent at all.
    operator_email: str | None = None

    @field_validator(
        "marketaux_token", "dart_api_key", "ecos_api_key",
        "db_host", "db_name", "db_user", "db_password",
        "smtp_user", "smtp_password", "operator_email",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    def universe_sizes(self) -> dict[Exchange, int]:
        """How many stocks each exchange contributes to the screening universe."""
        return {
            Exchange.KOSPI: self.screen_kospi_size,
            Exchange.KOSDAQ: self.screen_kosdaq_size,
            Exchange.SP500: self.screen_sp500_min_size,
        }

    def all_symbols(self) -> tuple[QuoteSymbol, ...]:
        """Everything to quote: indices first, then the watchlist."""
        return (*self.quote_symbols, *self.watchlist)

    def database_url(self) -> URL:
        """Connection URL built from APP_DB_*. Raises ValueError naming what is missing."""
        required = {
            "APP_DB_HOST": self.db_host,
            "APP_DB_NAME": self.db_name,
            "APP_DB_USER": self.db_user,
            "APP_DB_PASSWORD": self.db_password,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing or self.db_password is None:
            raise ValueError(f"database is not configured, missing: {', '.join(missing)}")
        # URL.create escapes reserved characters; never build this by string concatenation.
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is read once per process."""
    return Settings()
