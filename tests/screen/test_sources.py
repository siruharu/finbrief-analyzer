from collections.abc import Sequence
from datetime import date

import pandas as pd
import pytest

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.screen.models import Bar
from finbrief_analyzer.screen.ranking import RankRow
from finbrief_analyzer.screen.sources import (
    FdrHistorySource,
    YfBatchSource,
    frame_bars,
    rank_bar,
)

SINCE = date(2025, 9, 1)
NAN = float("nan")


def _frame(
    rows: dict[str, tuple[float, float, float, float, float]], tz: str | None = None
) -> pd.DataFrame:
    """A price table shaped like FinanceDataReader's (no timezone) or yfinance's (with one)."""
    index = pd.DatetimeIndex(list(rows), tz=tz)
    columns = ["Open", "High", "Low", "Close", "Volume"]
    return pd.DataFrame(list(rows.values()), index=index, columns=columns)


def _batch_frame(per_ticker: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """What yf.download(..., group_by="ticker") returns: columns keyed by (ticker, field)."""
    return pd.concat(per_ticker, axis=1)


def _one_day(close: float = 100.0) -> pd.DataFrame:
    return _frame({"2026-10-07": (99.0, 101.0, 98.0, close, 5000.0)}, tz="America/New_York")


class Downloads:
    """A fake batch download that answers from prepared frames and records what was asked."""

    def __init__(self, answers: dict[str, pd.DataFrame], fail: Sequence[int] = ()) -> None:
        self.batches: list[list[str]] = []
        self._answers = answers
        self._fail = fail

    def __call__(self, symbols: Sequence[str], since: date) -> pd.DataFrame:
        self.batches.append(list(symbols))
        if len(self.batches) in self._fail:
            raise RuntimeError("connection reset")
        found = {s: self._answers[s] for s in symbols if s in self._answers}
        return _batch_frame(found) if found else pd.DataFrame()


def _source(downloads: Downloads, size: int = 2, naps: list[float] | None = None) -> YfBatchSource:
    recorded = naps if naps is not None else []
    return YfBatchSource(downloads, batch_size=size, pause_seconds=1.5, sleep=recorded.append)


def test_table_row_becomes_a_bar_with_open_high_low_close_and_volume() -> None:
    # given
    frame = _frame({"2026-10-07": (267000.0, 269000.0, 265500.0, 268500.0, 6605757.0)})

    # when
    (bar,) = frame_bars("005930", frame)

    # then
    assert bar == Bar("005930", date(2026, 10, 7), 268500.0, 6605757, 267000.0, 269000.0, 265500.0)
    assert isinstance(bar.volume, int)


def test_row_without_a_close_is_dropped() -> None:
    # given: an unfinished row comes back with NaN
    frame = _frame(
        {"2026-10-06": (1.0, 1.0, 1.0, 100.0, 10.0), "2026-10-07": (1.0, 1.0, 1.0, NAN, 10.0)}
    )

    # when / then
    assert [bar.day for bar in frame_bars("X", frame)] == [date(2026, 10, 6)]


def test_missing_volume_is_read_as_zero() -> None:
    # given
    frame = _frame({"2026-10-07": (1.0, 1.0, 1.0, 100.0, NAN)})

    # when / then
    assert frame_bars("X", frame)[0].volume == 0


def test_missing_open_high_or_low_is_read_as_none() -> None:
    # given
    frame = _frame({"2026-10-07": (NAN, NAN, NAN, 100.0, 10.0)})

    # when
    (bar,) = frame_bars("X", frame)

    # then
    assert (bar.open, bar.high, bar.low) == (None, None, None)


def test_bar_day_is_the_market_local_date_of_a_timezone_aware_index() -> None:
    # given: midnight in New York is already the next day in Seoul
    frame = _frame({"2026-10-07": (1.0, 1.0, 1.0, 100.0, 10.0)}, tz="America/New_York")

    # when / then
    assert frame_bars("NVDA", frame)[0].day == date(2026, 10, 7)


def test_table_without_a_close_column_is_a_collect_error() -> None:
    # given: an empty answer has no columns at all
    # when / then
    with pytest.raises(CollectError, match="NVDA"):
        frame_bars("NVDA", pd.DataFrame())


def test_fdr_history_asks_for_the_symbol_since_the_given_day() -> None:
    # given
    asked: list[tuple[str, date]] = []

    def fetch(symbol: str, since: date) -> pd.DataFrame:
        asked.append((symbol, since))
        return _frame({"2026-10-07": (1.0, 1.0, 1.0, 100.0, 10.0)})

    # when
    bars = FdrHistorySource(fetch).history("005930", SINCE)

    # then
    assert asked == [("005930", SINCE)]
    assert [bar.symbol for bar in bars] == ["005930"]


def test_fdr_history_failure_becomes_a_collect_error() -> None:
    # given
    def fetch(symbol: str, since: date) -> pd.DataFrame:
        raise KeyError("timestamp")

    # when / then
    with pytest.raises(CollectError, match="005930"):
        FdrHistorySource(fetch).history("005930", SINCE)


def test_fdr_history_with_no_rows_is_a_collect_error() -> None:
    # given: the library answers an unknown code with an empty table
    source = FdrHistorySource(lambda symbol, since: _frame({}))

    # when / then
    with pytest.raises(CollectError, match="no data"):
        source.history("999999", SINCE)


def test_batch_source_splits_the_symbols_by_the_configured_size() -> None:
    # given
    downloads = Downloads({s: _one_day() for s in "ABCDE"})

    # when
    _source(downloads, size=2).fetch(list("ABCDE"), SINCE)

    # then
    assert downloads.batches == [["A", "B"], ["C", "D"], ["E"]]


def test_batch_source_pauses_between_batches_but_not_after_the_last() -> None:
    # given
    naps: list[float] = []
    downloads = Downloads({s: _one_day() for s in "ABCDE"})

    # when
    _source(downloads, size=2, naps=naps).fetch(list("ABCDE"), SINCE)

    # then: three batches, two pauses
    assert naps == [1.5, 1.5]


def test_batch_source_returns_the_bars_of_every_symbol_with_data() -> None:
    # given
    downloads = Downloads({"A": _one_day(10.0), "B": _one_day(20.0)})

    # when
    result = _source(downloads).fetch(["A", "B"], SINCE)

    # then
    assert {symbol: bars[0].close for symbol, bars in result.bars.items()} == {"A": 10.0, "B": 20.0}
    assert result.failed == ()


def test_symbol_missing_from_the_answer_is_reported_as_failed() -> None:
    # given: Yahoo knows A, not Z
    downloads = Downloads({"A": _one_day()})

    # when
    result = _source(downloads).fetch(["A", "Z"], SINCE)

    # then
    assert list(result.bars) == ["A"]
    assert result.failed == ("Z",)


def test_symbol_whose_rows_are_all_empty_is_reported_as_failed() -> None:
    # given: the column exists but every close is NaN
    hollow = _frame({"2026-10-07": (NAN, NAN, NAN, NAN, NAN)}, tz="America/New_York")
    downloads = Downloads({"A": _one_day(), "Z": hollow})

    # when
    result = _source(downloads).fetch(["A", "Z"], SINCE)

    # then
    assert result.failed == ("Z",)


def test_one_crashing_batch_still_returns_the_other_batches() -> None:
    # given: the second of three batches fails
    downloads = Downloads({s: _one_day() for s in "ABCDE"}, fail=[2])

    # when
    result = _source(downloads, size=2).fetch(list("ABCDE"), SINCE)

    # then
    assert sorted(result.bars) == ["A", "B", "E"]
    assert result.failed == ("C", "D")


def test_batch_that_returns_nothing_at_all_stops_the_remaining_batches() -> None:
    # given: Yahoo started refusing after the first batch
    downloads = Downloads({"A": _one_day(), "B": _one_day()})

    # when
    result = _source(downloads, size=2).fetch(list("ABCDEF"), SINCE)

    # then: the third batch is never sent, so a block is not made longer
    assert downloads.batches == [["A", "B"], ["C", "D"]]
    assert result.failed == ("C", "D", "E", "F")


def test_single_symbol_batch_goes_through_the_same_path() -> None:
    # given
    downloads = Downloads({"A": _one_day(42.0)})

    # when
    result = _source(downloads).fetch(["A"], SINCE)

    # then
    assert result.bars["A"][0].close == 42.0


def test_no_symbols_means_no_request() -> None:
    # given
    downloads = Downloads({})

    # when
    result = _source(downloads).fetch([], SINCE)

    # then
    assert downloads.batches == []
    assert (result.bars, result.failed) == ({}, ())


def test_ranking_row_becomes_a_bar_on_its_trading_day_without_open_high_low() -> None:
    # given
    row = RankRow(
        "005930", "삼성전자", "stock", 266750.0, 268500.0, 6605757, 1, date(2026, 10, 7), "CLOSE"
    )

    # when / then
    assert rank_bar(row) == Bar("005930", date(2026, 10, 7), 266750.0, 6605757)
