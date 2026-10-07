"""Korean news from publisher RSS feeds. Only feed entries are read, never article pages."""

import html
import logging
import re
from collections.abc import Sequence
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, ParseError

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from finbrief_analyzer.collect.models import CollectError, NewsItem

logger = logging.getLogger(__name__)

SOURCE = "rss"
# hankyung.com and mk.co.kr answer 403 to the default "python-httpx" agent.
USER_AGENT = "finbrief-analyzer/0.1"
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
# mk.co.kr writes "+09:00"; RFC 822 wants "+0900" and the parser drops the zone otherwise.
_COLON_ZONE = re.compile(r"([+-]\d{2}):(\d{2})$")
_DECLARATION = re.compile(rb"\s*<\?xml[^>]*?encoding=[\"']([\w.-]+)[\"'][^>]*\?>")


class RssNewsProvider:
    name = SOURCE

    def __init__(self, client: httpx.Client, feeds: Sequence[str]) -> None:
        self._client = client
        self._feeds = feeds

    def get_news(self, since: datetime) -> Sequence[NewsItem]:
        """Return items from every readable feed, newest first; raise only if all fail."""
        by_link: dict[str, NewsItem] = {}
        failed = 0
        for url in self._feeds:
            try:
                items = self._read_feed(url)
            except CollectError as error:
                logger.warning("feed skipped: %s", error)
                failed += 1
                continue
            for item in items:
                if item.published_at >= since:
                    by_link.setdefault(item.link, item)
        if self._feeds and failed == len(self._feeds):
            raise CollectError(SOURCE, "every feed failed")
        return sorted(by_link.values(), key=lambda item: item.published_at, reverse=True)

    def _read_feed(self, url: str) -> list[NewsItem]:
        host = _host(url)
        try:
            response = self._client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        except httpx.HTTPError as error:
            detail = f"{host}: request failed ({type(error).__name__})"
            raise CollectError(SOURCE, detail) from error
        # Bytes, not text: the XML declaration names the encoding.
        return _parse_feed(response.content, host)


def _parse_feed(xml: bytes, source: str) -> list[NewsItem]:
    try:
        root = fromstring(_to_utf8(xml))
    except (ParseError, DefusedXmlException, ValueError, LookupError) as error:
        detail = f"{source}: unreadable feed ({type(error).__name__})"
        raise CollectError(SOURCE, detail) from error
    items = (_to_item(element, source) for element in root.findall("./channel/item"))
    return [item for item in items if item is not None]


def _to_utf8(xml: bytes) -> bytes:
    """Transcode feeds declared in another encoding; expat cannot read EUC-KR and the like."""
    declaration = _DECLARATION.match(xml)
    if declaration is None:
        return xml
    encoding = declaration.group(1).decode("ascii")
    if encoding.lower() in ("utf-8", "utf8"):
        return xml
    return xml[declaration.end() :].decode(encoding).encode("utf-8")


def _to_item(element: Element, source: str) -> NewsItem | None:
    """Build a NewsItem, or None when the entry lacks a title, a web link or a usable time."""
    title = _strip_html(element.findtext("title") or "")
    link = (element.findtext("link") or "").strip()
    published_at = _parse_time(element.findtext("pubDate") or "")
    if not title or published_at is None or urlsplit(link).scheme not in ("http", "https"):
        return None
    summary = _strip_html(element.findtext("description") or "")
    return NewsItem(
        title=title,
        link=link,
        source=source,
        published_at=published_at,
        summary=summary if summary and summary != title else None,
    )


def _parse_time(text: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(_COLON_ZONE.sub(r"\1\2", text.strip()))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.utcoffset() is not None else None


def _strip_html(text: str) -> str:
    """Remove tags, decode entities and collapse whitespace. Output is plain text, not safe HTML."""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def _host(url: str) -> str:
    return (urlsplit(url).hostname or url).removeprefix("www.")
