"""US market news from Marketaux.

Free plan: 3 articles per request and 100 requests a day; a timed-out request
still costs one. See docs/01_research/2026-10-07_data-source-poc.md.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from finbrief_analyzer.collect.models import CollectError, NewsItem
from finbrief_analyzer.collect.redact import hide_from_http_log
from finbrief_analyzer.collect.text import plain_text

logger = logging.getLogger(__name__)

SOURCE = "marketaux"
URL = "https://api.marketaux.com/v1/news/all"
ARTICLES_PER_PAGE = 3


class MarketauxNewsProvider:
    name = SOURCE

    def __init__(self, client: httpx.Client, token: SecretStr, max_calls: int) -> None:
        self._client = client
        self._token = token
        self._max_calls = max_calls
        hide_from_http_log(token)

    def get_news(self, since: datetime) -> Sequence[NewsItem]:
        """Page until the call limit, an empty page or a failure.

        Only a failure of the first call raises; later ones end the paging.
        """
        by_link: dict[str, NewsItem] = {}
        for page in range(1, self._max_calls + 1):
            try:
                items = self._fetch_page(since, page)
            except CollectError as error:
                if page == 1:
                    raise
                # No retry: every request counts against the daily quota.
                logger.warning("paging stopped: %s", error)
                break
            if not items:
                break
            for item in items:
                if item.published_at >= since:
                    by_link.setdefault(item.link, item)
        return sorted(by_link.values(), key=lambda item: item.published_at, reverse=True)

    def _fetch_page(self, since: datetime, page: int) -> list[NewsItem]:
        params = {
            "api_token": self._token.get_secret_value(),
            "language": "en",
            # The country of the companies an article is about, not of the publisher.
            "countries": "us",
            "limit": str(ARTICLES_PER_PAGE),
            "published_after": since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M"),
            "page": str(page),
        }
        payload: Any = None  # Any: decoded JSON, validated in _parse
        reason: str | None = None
        try:
            response = self._client.get(URL, params=params)
            if response.status_code == httpx.codes.OK:
                payload = response.json()
            else:
                reason = f"HTTP {response.status_code}"
        except (httpx.HTTPError, ValueError) as error:
            reason = type(error).__name__
        if reason is not None:
            # Raised outside the except block on purpose: the original error quotes the
            # URL, the token is in the URL, and a chained exception would carry it along.
            raise CollectError(SOURCE, f"page {page}: request failed ({reason})")
        return _parse(page, payload)


def _parse(page: int, payload: Any) -> list[NewsItem]:
    """Read the articles of one page. Any: external JSON; every access is checked."""
    articles = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        raise CollectError(SOURCE, f"page {page}: unexpected response layout")
    items = (_to_item(article) for article in articles)
    return [item for item in items if item is not None]


def _to_item(article: Any) -> NewsItem | None:
    """Build a NewsItem, or None when the article lacks a title, a web link or a usable time."""
    if not isinstance(article, dict):
        return None
    title = plain_text(str(article.get("title") or ""))
    link = str(article.get("url") or "").strip()
    try:
        published_at = datetime.fromisoformat(str(article.get("published_at")))
    except ValueError:
        return None
    if not title or published_at.utcoffset() is None:
        return None
    if urlsplit(link).scheme not in ("http", "https"):
        return None
    # "description" only: the "snippet" field often holds anti-bot boilerplate.
    summary = plain_text(str(article.get("description") or ""))
    return NewsItem(
        title=title,
        link=link,
        source=str(article.get("source") or SOURCE),
        published_at=published_at,
        summary=summary or None,
    )
