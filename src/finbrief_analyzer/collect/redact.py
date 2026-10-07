"""Keep API keys out of the HTTP client's own request log.

httpx logs every request line at INFO, full URL included. ECOS carries its key in
the URL path and Marketaux and DART carry theirs in the query string.
"""

import logging
from urllib.parse import quote

from pydantic import SecretStr

MASK = "***"
_HTTP_LOGGER = "httpx"


class _SecretFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()

    def add(self, value: str) -> None:
        # The percent-encoded form is what appears in a URL when the value has reserved characters.
        self._secrets.update(v for v in (value, quote(value, safe="")) if v)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = message
        for secret in self._secrets:
            masked = masked.replace(secret, MASK)
        if masked != message:
            record.msg, record.args = masked, None
        return True


_filter = _SecretFilter()


def hide_from_http_log(secret: SecretStr) -> None:
    """Mask the secret wherever the HTTP client logs it. Safe to call repeatedly."""
    _filter.add(secret.get_secret_value())
    logger = logging.getLogger(_HTTP_LOGGER)
    if _filter not in logger.filters:
        logger.addFilter(_filter)
