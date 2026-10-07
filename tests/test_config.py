from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from finbrief_analyzer.collect.models import Market
from finbrief_analyzer.core.config import Settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings reads ".env" relative to the working directory; keep the developer's file out.
    monkeypatch.chdir(tmp_path)
    for key in ("APP_MARKETAUX_TOKEN", "APP_DART_API_KEY", "APP_ECOS_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_marketaux_token_is_read_as_secret_and_hidden_from_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given
    monkeypatch.setenv("APP_MARKETAUX_TOKEN", "tok-very-secret")

    # when
    settings = Settings()

    # then
    assert isinstance(settings.marketaux_token, SecretStr)
    assert settings.marketaux_token.get_secret_value() == "tok-very-secret"
    assert "tok-very-secret" not in repr(settings)


def test_api_keys_are_none_when_not_configured() -> None:
    # given: no key in the environment
    # when
    settings = Settings()

    # then
    assert settings.marketaux_token is None
    assert settings.dart_api_key is None
    assert settings.ecos_api_key is None


def test_blank_api_key_is_treated_as_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # given: .env.example ships the names with empty values
    monkeypatch.setenv("APP_ECOS_API_KEY", "")

    # when
    settings = Settings()

    # then
    assert settings.ecos_api_key is None


def test_rss_feeds_have_defaults_and_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    # given
    defaults = Settings().kr_rss_feeds
    monkeypatch.setenv("APP_KR_RSS_FEEDS", '["https://example.com/feed.xml"]')

    # when
    overridden = Settings().kr_rss_feeds

    # then
    assert len(defaults) > 0
    assert all(url.startswith("https://") for url in defaults)
    assert overridden == ("https://example.com/feed.xml",)


def test_default_symbols_cover_two_kr_indices_three_us_indices_and_one_us_yield() -> None:
    # given / when
    symbols = Settings().quote_symbols

    # then: FX is not here, it comes from ECOS (PoC decision)
    by_market = [s.market for s in symbols]
    assert by_market.count(Market.KR) == 2
    assert by_market.count(Market.US) == 3
    assert by_market.count(Market.RATE) == 1
    assert by_market.count(Market.FX) == 0
    assert len({s.symbol for s in symbols}) == len(symbols)


def test_symbols_can_be_overridden_with_a_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    # given
    monkeypatch.setenv(
        "APP_QUOTE_SYMBOLS", '[{"symbol": "KS200", "name": "KOSPI 200", "market": "kr"}]'
    )

    # when
    symbols = Settings().quote_symbols

    # then
    assert [(s.symbol, s.name, s.market) for s in symbols] == [("KS200", "KOSPI 200", Market.KR)]


@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    # given
    monkeypatch.setenv("APP_HTTP_TIMEOUT_SECONDS", value)

    # when / then
    with pytest.raises(ValidationError):
        Settings()


def test_marketaux_calls_per_slot_stay_within_the_free_daily_quota() -> None:
    # given: two slots a day share 100 free requests
    # when
    settings = Settings()

    # then
    assert 0 < settings.marketaux_max_calls_per_slot * 2 <= 100
