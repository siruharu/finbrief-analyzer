from datetime import date

from sqlalchemy import Engine

from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.models import Bar
from finbrief_analyzer.store.price_bars import (
    add_bars,
    delete_symbol,
    histories,
    history,
    last_bars,
    last_days,
)


def _bar(symbol: str, day: int, close: float = 100.0, volume: int = 1000) -> Bar:
    return Bar(symbol=symbol, day=date(2026, 10, day), close=close, volume=volume)


def _add(engine: Engine, *bars: Bar) -> int:
    with session_scope(engine) as session:
        return add_bars(session, bars)


def _history(engine: Engine, symbol: str, since: date = date(2026, 1, 1)) -> list[Bar]:
    with session_scope(engine) as session:
        return history(session, symbol, since)


def test_bar_is_stored_and_read_back_with_every_field(store: Engine) -> None:
    # given: a bar from the first load, which has open, high and low
    bar = Bar("005930", date(2026, 10, 7), close=268500.0, volume=6_605_757, open=267000.0)

    # when
    _add(store, bar)

    # then
    assert _history(store, "005930") == [bar]


def test_adding_the_same_symbol_and_day_twice_keeps_one_row_with_the_first_value(
    store: Engine,
) -> None:
    # given
    _add(store, _bar("005930", 7, close=100.0))

    # when
    added = _add(store, _bar("005930", 7, close=999.0))

    # then
    assert added == 0
    assert [bar.close for bar in _history(store, "005930")] == [100.0]


def test_only_the_new_days_of_a_mixed_batch_are_added(store: Engine) -> None:
    # given
    _add(store, _bar("005930", 6), _bar("005930", 7))

    # when
    added = _add(store, _bar("005930", 7), _bar("005930", 8))

    # then
    assert added == 1
    assert [bar.day.day for bar in _history(store, "005930")] == [6, 7, 8]


def test_duplicate_days_inside_one_batch_are_added_once(store: Engine) -> None:
    # given / when: a ranking page listed the same stock twice
    added = _add(store, _bar("005930", 7), _bar("005930", 7))

    # then
    assert added == 1


def test_history_comes_back_in_ascending_day_order(store: Engine) -> None:
    # given: stored out of order
    _add(store, _bar("005930", 8), _bar("005930", 6), _bar("005930", 7))

    # when / then
    assert [bar.day.day for bar in _history(store, "005930")] == [6, 7, 8]


def test_history_leaves_out_days_before_since(store: Engine) -> None:
    # given
    _add(store, _bar("005930", 6), _bar("005930", 7), _bar("005930", 8))

    # when
    found = _history(store, "005930", since=date(2026, 10, 7))

    # then
    assert [bar.day.day for bar in found] == [7, 8]


def test_history_of_one_symbol_does_not_include_another(store: Engine) -> None:
    # given
    _add(store, _bar("005930", 7), _bar("NVDA", 7))

    # when / then
    assert [bar.symbol for bar in _history(store, "NVDA")] == ["NVDA"]


def test_last_days_reads_the_latest_day_of_every_symbol_at_once(store: Engine) -> None:
    # given
    _add(store, _bar("005930", 6), _bar("005930", 8), _bar("NVDA", 7))

    # when
    with session_scope(store) as session:
        found = last_days(session, ["005930", "NVDA", "AAPL"])

    # then: a symbol without history is simply absent
    assert found == {"005930": date(2026, 10, 8), "NVDA": date(2026, 10, 7)}


def test_last_days_of_no_symbols_is_empty(store: Engine) -> None:
    # given / when
    with session_scope(store) as session:
        found = last_days(session, [])

    # then
    assert found == {}


def test_deleting_one_symbol_keeps_the_others(store: Engine) -> None:
    # given
    _add(store, _bar("005930", 7), _bar("NVDA", 7))

    # when
    with session_scope(store) as session:
        delete_symbol(session, "005930")

    # then
    assert _history(store, "005930") == []
    assert len(_history(store, "NVDA")) == 1


def test_volume_beyond_32_bits_survives(store: Engine) -> None:
    # given: a heavy day for a US mega-cap
    _add(store, _bar("NVDA", 7, volume=5_000_000_000))

    # when / then
    assert _history(store, "NVDA")[0].volume == 5_000_000_000


def test_last_bars_reads_the_latest_bar_of_every_symbol_at_once(store: Engine) -> None:
    # given
    _add(
        store,
        _bar("005930", 6, close=1.0),
        _bar("005930", 8, close=3.0),
        _bar("NVDA", 7, close=9.0),
    )

    # when
    with session_scope(store) as session:
        found = last_bars(session, ["005930", "NVDA", "AAPL"])

    # then: the close of the last day, and nothing for a symbol without history
    assert {symbol: (bar.day.day, bar.close) for symbol, bar in found.items()} == {
        "005930": (8, 3.0),
        "NVDA": (7, 9.0),
    }


def test_histories_reads_many_symbols_in_one_go_each_oldest_first(store: Engine) -> None:
    # given
    _add(store, _bar("005930", 8), _bar("005930", 6), _bar("NVDA", 7), _bar("AAPL", 7))

    # when
    with session_scope(store) as session:
        found = histories(session, ["005930", "NVDA", "TSLA"], date(2026, 10, 7))

    # then: only what was asked for, from `since` on
    assert {symbol: [bar.day.day for bar in bars] for symbol, bars in found.items()} == {
        "005930": [8],
        "NVDA": [7],
    }
