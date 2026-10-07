"""Quote adapter backed by FinanceDataReader.

Every default symbol resolves to Yahoo behind this library, see
docs/01_research/2026-10-07_data-source-poc.md.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from finbrief_analyzer.collect.quotes_base import Fetch, FrameQuoteProvider

SOURCE = "fdr"


def _fdr_fetch(symbol: str, start: date) -> Any:  # pragma: no cover - network
    # Imported here so that importing this module does not load pandas.
    import FinanceDataReader as fdr

    return fdr.DataReader(symbol, start.isoformat())


class FdrQuoteProvider(FrameQuoteProvider):
    def __init__(self, fetch: Fetch = _fdr_fetch, today: Callable[[], date] = date.today) -> None:
        super().__init__(SOURCE, fetch, today)
