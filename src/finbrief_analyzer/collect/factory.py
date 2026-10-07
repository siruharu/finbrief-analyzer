"""Wire the real sources from settings. A source without its API key is left out."""

import httpx

from finbrief_analyzer.collect.news_dart import DartNewsProvider
from finbrief_analyzer.collect.news_marketaux import MarketauxNewsProvider
from finbrief_analyzer.collect.news_rss import RssNewsProvider
from finbrief_analyzer.collect.ports import NewsProvider
from finbrief_analyzer.collect.quotes_fallback import FallbackQuoteProvider
from finbrief_analyzer.collect.quotes_fdr import FdrQuoteProvider
from finbrief_analyzer.collect.quotes_naver import NaverQuoteProvider
from finbrief_analyzer.collect.quotes_yf import YfQuoteProvider
from finbrief_analyzer.collect.rates import EcosRateProvider
from finbrief_analyzer.collect.service import Providers
from finbrief_analyzer.core.config import Settings


def make_client(settings: Settings) -> httpx.Client:
    """HTTP client for the collectors. The caller closes it."""
    return httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True)


def build_providers(settings: Settings, client: httpx.Client) -> Providers:
    # Naver backs up the Korean indices, yfinance the US symbols.
    quotes = FallbackQuoteProvider(
        FdrQuoteProvider(), [NaverQuoteProvider(client), YfQuoteProvider()]
    )
    rates = None
    if settings.ecos_api_key is not None:
        rates = EcosRateProvider(client, settings.ecos_api_key)
    return Providers(quotes=quotes, rates=rates, news=tuple(_news_providers(settings, client)))


def _news_providers(settings: Settings, client: httpx.Client) -> list[NewsProvider]:
    providers: list[NewsProvider] = []
    if settings.kr_rss_feeds:
        providers.append(RssNewsProvider(client, settings.kr_rss_feeds))
    if settings.marketaux_token is not None:
        calls = settings.marketaux_max_calls_per_slot
        providers.append(MarketauxNewsProvider(client, settings.marketaux_token, calls))
    if settings.dart_api_key is not None:
        providers.append(DartNewsProvider(client, settings.dart_api_key))
    return providers
