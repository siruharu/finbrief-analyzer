from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.collect.ports import QuoteProvider
from finbrief_analyzer.collect.quotes_fdr import FdrQuoteProvider

TODAY = date(2026, 10, 7)
NAN = float("nan")


def _frame(rows: dict[str, float]) -> pd.DataFrame:
    """Build a table shaped like the FinanceDataReader result seen in the PoC."""
    index = pd.DatetimeIndex(list(rows))
    return pd.DataFrame({"Open": 1.0, "Close": list(rows.values())}, index=index)


def _provider(fetch: Callable[[str, date], object]) -> FdrQuoteProvider:
    return FdrQuoteProvider(fetch=fetch, today=lambda: TODAY)


def test_last_row_becomes_close_and_the_row_before_becomes_prev_close() -> None:
    # given
    frame = _frame({"2026-10-02": 7003.74, "2026-10-06": 6941.39, "2026-10-07": 6803.90})
    provider = _provider(lambda symbol, start: frame)

    # when
    (quote,) = provider.get_quotes(["^KS11"])

    # then
    assert quote.symbol == "^KS11"
    assert quote.close == pytest.approx(6803.90)
    assert quote.prev_close == pytest.approx(6941.39)


def test_single_row_gives_quote_without_prev_close() -> None:
    # given
    provider = _provider(lambda symbol, start: _frame({"2026-10-07": 6803.90}))

    # when
    (quote,) = provider.get_quotes(["^KS11"])

    # then
    assert quote.prev_close is None
    assert quote.change_pct is None


def test_empty_result_raises_collect_error() -> None:
    # given: what the stale KS11 symbol returned in the PoC, columns but no rows
    provider = _provider(lambda symbol, start: _frame({}))

    # when / then
    with pytest.raises(CollectError, match="KS11"):
        provider.get_quotes(["KS11"])


def test_fetch_exception_is_translated_to_collect_error_with_cause() -> None:
    # given
    def fetch(symbol: str, start: date) -> object:
        raise ValueError("LOGOUT")

    provider = _provider(fetch)

    # when
    with pytest.raises(CollectError) as caught:
        provider.get_quotes(["KRX-INDEX:1001"])

    # then
    assert caught.value.source == "fdr"
    assert "LOGOUT" in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)


def test_rows_with_nan_close_are_skipped() -> None:
    # given: the USD/KRW table had a NaN close in the middle
    frame = _frame({"2026-10-05": 1343.75, "2026-10-06": NAN, "2026-10-07": 1337.18})
    provider = _provider(lambda symbol, start: frame)

    # when
    (quote,) = provider.get_quotes(["USD/KRW"])

    # then
    assert quote.close == pytest.approx(1337.18)
    assert quote.prev_close == pytest.approx(1343.75)


def test_as_of_is_the_date_of_the_last_valid_row() -> None:
    # given: today's row exists but has no close yet
    frame = _frame({"2026-10-05": 1343.75, "2026-10-06": 1340.0, "2026-10-07": NAN})
    provider = _provider(lambda symbol, start: frame)

    # when
    (quote,) = provider.get_quotes(["USD/KRW"])

    # then
    assert quote.as_of == date(2026, 10, 6)
    assert type(quote.as_of) is date
    assert type(quote.close) is float


def test_last_row_older_than_the_lookback_window_is_rejected_as_stale() -> None:
    # given: a source that stopped updating three weeks ago but still returns rows
    frame = _frame({"2026-09-16": 6717.97, "2026-09-17": 6724.34})
    provider = _provider(lambda symbol, start: frame)

    # when / then
    with pytest.raises(CollectError, match="stale"):
        provider.get_quotes(["KS11"])


def test_table_without_close_column_raises_collect_error() -> None:
    # given
    frame = pd.DataFrame({"DGS10": [5.31]}, index=pd.DatetimeIndex(["2026-10-05"]))
    provider = _provider(lambda symbol, start: frame)

    # when / then
    with pytest.raises(CollectError, match="Close"):
        provider.get_quotes(["FRED:DGS10"])


def test_failed_symbol_is_left_out_while_the_others_are_returned() -> None:
    # given
    def fetch(symbol: str, start: date) -> object:
        if symbol == "KS11":
            return _frame({})
        return _frame({"2026-10-05": 27477.31, "2026-10-06": 27599.79})

    provider = _provider(fetch)

    # when
    quotes = provider.get_quotes(["KS11", "IXIC"])

    # then
    assert [q.symbol for q in quotes] == ["IXIC"]


def test_fetch_is_asked_for_a_window_long_enough_to_span_a_holiday_week() -> None:
    # given
    starts: list[date] = []

    def fetch(symbol: str, start: date) -> object:
        starts.append(start)
        return _frame({"2026-10-06": 1.0, "2026-10-07": 2.0})

    # when
    _provider(fetch).get_quotes(["IXIC"])

    # then
    assert starts == [date(2026, 9, 27)]


def test_provider_satisfies_the_quote_port() -> None:
    # given / when
    provider: QuoteProvider = _provider(lambda symbol, start: _frame({"2026-10-07": 1.0}))

    # then
    assert provider.name == "fdr"
