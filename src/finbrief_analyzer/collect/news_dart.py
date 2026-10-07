"""Major corporate filings from the Korean regulator's DART API, as supporting news.

DART reports errors with HTTP 200 and a body `status` code, and gives a receipt
date without a time. See docs/01_research/2026-10-07_data-source-poc.md.
"""

import re
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import SecretStr

from finbrief_analyzer.collect.models import CollectError, NewsItem
from finbrief_analyzer.collect.redact import MASK, hide_from_http_log
from finbrief_analyzer.collect.text import plain_text

SOURCE = "dart"
URL = "https://opendart.fss.or.kr/api/list.json"
VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
KST = timezone(timedelta(hours=9))
STATUS_OK = "000"
STATUS_NO_RESULT = "013"
# Major-matter reports of KOSPI-listed companies; unfiltered, most filings are fund prospectuses.
REPORT_TYPE = "B"
CORP_CLASS = "Y"
PAGE_SIZE = 100
_RECEIPT_NO = re.compile(r"\d{14}")


class DartNewsProvider:
    name = SOURCE

    def __init__(self, client: httpx.Client, api_key: SecretStr) -> None:
        self._client = client
        self._api_key = api_key
        hide_from_http_log(api_key)

    def get_news(self, since: datetime) -> Sequence[NewsItem]:
        """Return filings received on or after the KST date of `since`, latest receipt first."""
        day = since.astimezone(KST).date()
        records = _records(self._request(day.strftime("%Y%m%d")), self._api_key)
        records.sort(key=lambda record: str(record.get("rcept_no")), reverse=True)
        items = (_to_item(record) for record in records)
        # Filings carry a date only, so the cut-off is by day rather than by instant.
        return [item for item in items if item is not None and item.published_at.date() >= day]

    def _request(self, begin: str) -> Any:
        """Fetch the listing. Any: the decoded JSON document, validated in _records."""
        params = {
            "crtfc_key": self._api_key.get_secret_value(),
            "bgn_de": begin,
            "pblntf_ty": REPORT_TYPE,
            "corp_cls": CORP_CLASS,
            "page_count": str(PAGE_SIZE),
        }
        try:
            response = self._client.get(URL, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            reason = type(error).__name__
        # Raised outside the except block on purpose: the original error quotes the URL,
        # the key is in the URL, and a chained exception would carry it along.
        raise CollectError(SOURCE, f"request failed ({reason})")


def _records(payload: Any, api_key: SecretStr) -> list[dict[str, Any]]:
    """Check the status code and return the filing rows. Any: external JSON."""
    if not isinstance(payload, dict):
        raise CollectError(SOURCE, "unexpected response layout")
    status = str(payload.get("status"))
    if status == STATUS_NO_RESULT:
        return []
    if status != STATUS_OK:
        # The server's message is kept for diagnosis, minus anything that echoes the key.
        message = str(payload.get("message") or "").replace(api_key.get_secret_value(), MASK)
        raise CollectError(SOURCE, f"rejected with status {status}: {message}")
    rows = payload.get("list")
    if not isinstance(rows, list):
        raise CollectError(SOURCE, "unexpected response layout")
    return [row for row in rows if isinstance(row, dict)]


def _to_item(record: dict[str, Any]) -> NewsItem | None:
    """Build a NewsItem, or None when the row lacks a title, a receipt number or a date."""
    receipt_no = str(record.get("rcept_no") or "")
    company = plain_text(str(record.get("corp_name") or ""))
    report = plain_text(str(record.get("report_nm") or ""))
    if not _RECEIPT_NO.fullmatch(receipt_no) or not company or not report:
        return None
    try:
        received = datetime.strptime(str(record.get("rcept_dt")), "%Y%m%d")
    except ValueError:
        return None
    return NewsItem(
        title=f"{company} {report}",
        link=VIEWER_URL + receipt_no,
        source=SOURCE,
        published_at=received.replace(tzinfo=KST),
    )
