"""Where daily bars come from. Each source turns a library's table into Bar values.

No pandas value leaves this module. Confirmed in docs/01_research/2026-10-08_screening-poc.md:
one FinanceDataReader call per Korean stock, one yfinance download per batch of US stocks.
"""

import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.screen.models import Bar
from finbrief_analyzer.screen.ranking import RankRow

logger = logging.getLogger(__name__)

FDR = "fdr-history"
YF = "yfinance-batch"

# Any: the result is a pandas DataFrame and pandas ships no type stubs this project uses.
HistoryFetch = Callable[[str, date], Any]
BatchDownload = Callable[[Sequence[str], date], Any]


def _fdr_fetch(symbol: str, since: date) -> Any:  # pragma: no cover - network
    # Imported here so that importing this module does not load pandas.
    import FinanceDataReader as fdr

    return fdr.DataReader(symbol, since.isoformat())


def _yf_download(symbols: Sequence[str], since: date) -> Any:  # pragma: no cover - network
    import yfinance as yf

    # auto_adjust: splits and dividends are folded into the prices, so a 52-week high
    # compares like with like. A list of one keeps the (ticker, field) column layout.
    return yf.download(
        list(symbols),
        start=since.isoformat(),
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )


def _optional(value: float) -> float | None:
    return None if math.isnan(value) else value


def frame_bars(symbol: str, frame: Any) -> list[Bar]:
    """Read bars out of a price table. Rows without a close are dropped."""
    if "Close" not in frame.columns:
        raise CollectError(FDR, f"{symbol}: no Close column")
    bars: list[Bar] = []
    for stamp, row in frame.iterrows():
        close = float(row["Close"])
        if math.isnan(close):
            continue  # an unfinished or missing day
        volume = float(row["Volume"])
        bars.append(
            Bar(
                symbol=symbol,
                # The index holds the market-local trading day, with or without a timezone.
                day=date(stamp.year, stamp.month, stamp.day),
                close=close,
                volume=0 if math.isnan(volume) else int(volume),
                open=_optional(float(row["Open"])),
                high=_optional(float(row["High"])),
                low=_optional(float(row["Low"])),
            )
        )
    return bars


def rank_bar(row: RankRow) -> Bar:
    """A ranking row as the bar of its trading day. The ranking has no open, high or low."""
    return Bar(symbol=row.code, day=row.traded_on, close=row.close, volume=row.volume)


class FdrHistorySource:
    """One stock's history per request. Used for Korean stocks."""

    def __init__(self, fetch: HistoryFetch = _fdr_fetch) -> None:
        self._fetch = fetch

    def history(self, symbol: str, since: date) -> list[Bar]:
        try:
            frame = self._fetch(symbol, since)
        except Exception as error:
            detail = f"{symbol}: fetch failed ({type(error).__name__})"
            raise CollectError(FDR, detail) from error
        bars = frame_bars(symbol, frame) if len(frame) else []
        if not bars:
            raise CollectError(FDR, f"{symbol}: no data")
        return bars


@dataclass(frozen=True, slots=True)
class BatchResult:
    bars: dict[str, list[Bar]]
    # Symbols that got no data, in the requested order.
    failed: tuple[str, ...]


class YfBatchSource:
    """Many stocks per request. Used for US stocks."""

    def __init__(
        self,
        download: BatchDownload = _yf_download,
        batch_size: int = 100,
        pause_seconds: float = 1.0,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        self._download = download
        self._batch_size = batch_size
        self._pause_seconds = pause_seconds
        self._sleep = sleep

    def fetch(self, symbols: Sequence[str], since: date) -> BatchResult:
        """Bars per symbol since the given day. Never raises; failures are listed."""
        bars: dict[str, list[Bar]] = {}
        failed: list[str] = []
        batches = [
            symbols[start : start + self._batch_size]
            for start in range(0, len(symbols), self._batch_size)
        ]
        for index, batch in enumerate(batches):
            if index:
                self._sleep(self._pause_seconds)
            answer = self._one_batch(batch, since)
            found = answer or {}
            bars.update(found)
            failed += [symbol for symbol in batch if symbol not in found]
            if answer == {}:
                # Answered, but not one stock had data: Yahoo is refusing. Asking again
                # only prolongs it.
                failed += [symbol for later in batches[index + 1 :] for symbol in later]
                break
        return BatchResult(bars=bars, failed=tuple(failed))

    def _one_batch(self, batch: Sequence[str], since: date) -> dict[str, list[Bar]] | None:
        """Bars per symbol that had data, or None when the request itself crashed."""
        try:
            frame = self._download(batch, since)
        except Exception:
            # One bad batch must not lose the others.
            logger.exception("%s: batch of %d failed", YF, len(batch))
            return None
        answered = set(frame.columns.get_level_values(0)) if len(frame.columns) else set()
        found: dict[str, list[Bar]] = {}
        for symbol in batch:
            rows = frame_bars(symbol, frame[symbol]) if symbol in answered else []
            if rows:
                found[symbol] = rows
        return found
