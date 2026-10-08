from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.history import HistorySources, UpdateReport, differs, update_history
from finbrief_analyzer.screen.models import Bar, Exchange, Member
from finbrief_analyzer.screen.ranking import RankRow
from finbrief_analyzer.screen.sources import BatchResult
from finbrief_analyzer.store.price_bars import add_bars, history
from finbrief_analyzer.store.universe import replace_members

KST = timezone(timedelta(hours=9))
# Thursday. At 20:00 KST the Korean session of the 8th is over; New York is at 07:00,
# so the last completed US session is the 7th.
EVENING = datetime(2026, 10, 8, 20, 0, tzinfo=KST)
# At 11:00 KST the Korean market is open: the last completed session is the 7th.
MORNING = datetime(2026, 10, 8, 11, 0, tzinfo=KST)
D5, D6, D7, D8 = (date(2026, 10, day) for day in (5, 6, 7, 8))
SAMSUNG = "005930"


def bar(symbol: str, day: date, close: float = 100.0) -> Bar:
    return Bar(symbol, day, close, 1000)


def rank(code: str, day: date, close: float, prev_close: float) -> RankRow:
    return RankRow(code, code, "stock", close, prev_close, 2000, 1, day, "CLOSE")


class Ranking:
    def __init__(self, rows: Sequence[RankRow] = (), error: Exception | None = None) -> None:
        self.calls = 0
        self._rows = list(rows)
        self._error = error

    def fetch(self, exchange: Exchange, pages: int) -> list[RankRow]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._rows


class KrHistory:
    def __init__(self, bars: Sequence[Bar] = (), error: Exception | None = None) -> None:
        self.asked: list[tuple[str, date]] = []
        self._bars = list(bars)
        self._error = error

    def history(self, symbol: str, since: date) -> list[Bar]:
        self.asked.append((symbol, since))
        if self._error is not None:
            raise self._error
        return [b for b in self._bars if b.symbol == symbol]


class Batch:
    def __init__(self, bars: Sequence[Bar] = ()) -> None:
        self.calls: list[tuple[list[str], date]] = []
        self.bars = list(bars)

    def fetch(self, symbols: Sequence[str], since: date) -> BatchResult:
        self.calls.append((list(symbols), since))
        found = {
            symbol: [b for b in self.bars if b.symbol == symbol and b.day >= since]
            for symbol in symbols
        }
        found = {symbol: bars for symbol, bars in found.items() if bars}
        return BatchResult(found, tuple(s for s in symbols if s not in found))


@pytest.fixture
def kr(store: Engine) -> Engine:
    with session_scope(store) as session:
        replace_members(session, Exchange.KOSPI, [Member(Exchange.KOSPI, SAMSUNG, "삼성전자")], D5)
    return store


@pytest.fixture
def us(store: Engine) -> Engine:
    with session_scope(store) as session:
        replace_members(session, Exchange.SP500, [Member(Exchange.SP500, "NVDA", "Nvidia")], D5)
    return store


def _seed(engine: Engine, *bars: Bar) -> None:
    with session_scope(engine) as session:
        add_bars(session, bars)


def _stored(engine: Engine, symbol: str) -> list[tuple[date, float]]:
    with session_scope(engine) as session:
        return [(b.day, b.close) for b in history(session, symbol, date(2025, 1, 1))]


def _run(
    engine: Engine,
    now: datetime,
    ranking: Ranking | None = None,
    kr_history: KrHistory | None = None,
    batch: Batch | None = None,
    deadline: float | None = None,
) -> UpdateReport:
    sources = HistorySources(ranking or Ranking(), kr_history or KrHistory(), batch or Batch())
    return update_history(engine, sources, now, 400, deadline=deadline, clock=lambda: 100.0)


def test_differs_ignores_rounding_but_not_a_split() -> None:
    # given / when / then
    assert not differs(100.0, 100.3)
    assert differs(100.0, 101.0)
    assert differs(100.0, 50.0)


def test_kr_stock_without_history_is_loaded_whole(kr: Engine) -> None:
    # given
    source = KrHistory([bar(SAMSUNG, D6), bar(SAMSUNG, D7), bar(SAMSUNG, D8)])

    # when
    report = _run(kr, EVENING, kr_history=source)

    # then: asked for 400 days back
    assert source.asked == [(SAMSUNG, date(2025, 9, 3))]
    assert [day for day, _ in _stored(kr, SAMSUNG)] == [D6, D7, D8]
    assert (report.loaded, report.added) == (1, 3)


def test_kr_first_load_is_not_repeated_on_the_next_run(kr: Engine) -> None:
    # given: a completed first load
    source = KrHistory([bar(SAMSUNG, D7), bar(SAMSUNG, D8)])
    _run(kr, EVENING, kr_history=source)

    # when
    report = _run(kr, EVENING, kr_history=source)

    # then
    assert len(source.asked) == 1
    assert report == UpdateReport()


def test_kr_session_still_in_progress_is_not_stored(kr: Engine) -> None:
    # given: 11:00, and the history already has a row for today with a moving price
    source = KrHistory([bar(SAMSUNG, D7), bar(SAMSUNG, D8, close=123.0)])

    # when
    _run(kr, MORNING, kr_history=source)

    # then
    assert [day for day, _ in _stored(kr, SAMSUNG)] == [D7]


def test_kr_ranking_row_of_a_session_in_progress_is_not_appended(kr: Engine) -> None:
    # given: stored up to yesterday, the ranking shows today's moving price
    _seed(kr, bar(SAMSUNG, D7, close=100.0))
    ranking = Ranking([rank(SAMSUNG, D8, close=105.0, prev_close=100.0)])
    source = KrHistory()

    # when
    report = _run(kr, MORNING, ranking=ranking, kr_history=source)

    # then: nothing to do, yesterday is the last completed session
    assert _stored(kr, SAMSUNG) == [(D7, 100.0)]
    assert source.asked == []
    assert report == UpdateReport()


def test_kr_next_day_is_appended_from_the_ranking_without_a_history_request(kr: Engine) -> None:
    # given
    _seed(kr, bar(SAMSUNG, D7, close=100.0))
    ranking = Ranking([rank(SAMSUNG, D8, close=105.0, prev_close=100.0)])
    source = KrHistory()

    # when
    report = _run(kr, EVENING, ranking=ranking, kr_history=source)

    # then
    assert _stored(kr, SAMSUNG) == [(D7, 100.0), (D8, 105.0)]
    assert source.asked == []
    assert (report.added, report.reloaded) == (1, 0)


def test_kr_previous_close_within_tolerance_still_appends(kr: Engine) -> None:
    # given: the ranking's previous close is off by rounding only
    _seed(kr, bar(SAMSUNG, D7, close=100.0))
    ranking = Ranking([rank(SAMSUNG, D8, close=105.0, prev_close=100.2)])

    # when
    report = _run(kr, EVENING, ranking=ranking)

    # then
    assert report.reloaded == 0
    assert len(_stored(kr, SAMSUNG)) == 2


def test_kr_stock_is_loaded_again_when_the_previous_close_no_longer_matches(kr: Engine) -> None:
    # given: stored 100, but after a 2-for-1 split yesterday's close is now quoted as 50
    _seed(kr, bar(SAMSUNG, D6, close=98.0), bar(SAMSUNG, D7, close=100.0))
    ranking = Ranking([rank(SAMSUNG, D8, close=52.0, prev_close=50.0)])
    adjusted = KrHistory([bar(SAMSUNG, D6, 49.0), bar(SAMSUNG, D7, 50.0), bar(SAMSUNG, D8, 52.0)])

    # when
    report = _run(kr, EVENING, ranking=ranking, kr_history=adjusted)

    # then: the whole history is replaced, not patched
    assert _stored(kr, SAMSUNG) == [(D6, 49.0), (D7, 50.0), (D8, 52.0)]
    assert report.reloaded == 1


def test_kr_stock_is_loaded_again_after_missing_more_days_than_a_long_weekend(kr: Engine) -> None:
    # given: the PC was off for a week
    _seed(kr, bar(SAMSUNG, date(2026, 9, 30), close=100.0))
    ranking = Ranking([rank(SAMSUNG, D8, close=105.0, prev_close=100.0)])
    source = KrHistory([bar(SAMSUNG, date(2026, 9, 30)), bar(SAMSUNG, D7), bar(SAMSUNG, D8)])

    # when
    report = _run(kr, EVENING, ranking=ranking, kr_history=source)

    # then: the days in between are filled, not skipped over
    assert [day for day, _ in _stored(kr, SAMSUNG)] == [date(2026, 9, 30), D7, D8]
    assert report.reloaded == 1


def test_kr_failed_reload_keeps_the_stored_history(kr: Engine) -> None:
    # given: a mismatch, and the history source is down
    _seed(kr, bar(SAMSUNG, D7, close=100.0))
    ranking = Ranking([rank(SAMSUNG, D8, close=52.0, prev_close=50.0)])
    broken = KrHistory(error=CollectError("fdr-history", "005930: fetch failed"))

    # when
    report = _run(kr, EVENING, ranking=ranking, kr_history=broken)

    # then: fetched first, deleted only afterwards
    assert _stored(kr, SAMSUNG) == [(D7, 100.0)]
    assert report.failed == (SAMSUNG,)


def test_kr_falls_back_to_per_stock_history_when_the_ranking_is_down(kr: Engine) -> None:
    # given
    _seed(kr, bar(SAMSUNG, D7, close=100.0))
    ranking = Ranking(error=CollectError("naver-ranking", "503"))
    source = KrHistory([bar(SAMSUNG, D7, 100.0), bar(SAMSUNG, D8, 105.0)])

    # when
    _run(kr, EVENING, ranking=ranking, kr_history=source)

    # then
    assert _stored(kr, SAMSUNG) == [(D7, 100.0), (D8, 105.0)]


def test_kr_stock_that_has_not_traded_since_is_left_alone(kr: Engine) -> None:
    # given: suspended; the ranking still shows its last trade from the 6th
    _seed(kr, bar(SAMSUNG, D6, close=100.0))
    ranking = Ranking([rank(SAMSUNG, D6, close=100.0, prev_close=99.0)])
    source = KrHistory()

    # when
    report = _run(kr, EVENING, ranking=ranking, kr_history=source)

    # then: no reload every single run
    assert source.asked == []
    assert report == UpdateReport()


def test_past_the_deadline_loads_are_skipped_and_counted(kr: Engine, us: Engine) -> None:
    # given: the time limit is already behind us (the clock reads 100)
    source, batch = KrHistory([bar(SAMSUNG, D7)]), Batch([bar("NVDA", D7)])

    # when
    report = _run(kr, EVENING, kr_history=source, batch=batch, deadline=50.0)

    # then: one Korean and one US stock left for the next run
    assert source.asked == []
    assert batch.calls == []
    assert report.skipped == 2


def test_us_stock_without_history_is_loaded_whole(us: Engine) -> None:
    # given: Yahoo already has a row for today's unfinished session
    batch = Batch([bar("NVDA", D6), bar("NVDA", D7), bar("NVDA", D8)])

    # when
    report = _run(us, EVENING, batch=batch)

    # then: 400 days back, and only completed sessions
    assert batch.calls == [(["NVDA"], date(2025, 9, 3))]
    assert [day for day, _ in _stored(us, "NVDA")] == [D6, D7]
    assert report.loaded == 1


def test_us_new_days_are_appended_from_the_last_stored_day(us: Engine) -> None:
    # given
    _seed(us, bar("NVDA", D5, 190.0), bar("NVDA", D6, 200.0))
    batch = Batch([bar("NVDA", D5, 190.0), bar("NVDA", D6, 200.0), bar("NVDA", D7, 210.0)])

    # when
    report = _run(us, EVENING, batch=batch)

    # then: one request starting at the stored last day
    assert batch.calls == [(["NVDA"], D6)]
    assert _stored(us, "NVDA") == [(D5, 190.0), (D6, 200.0), (D7, 210.0)]
    assert (report.added, report.reloaded) == (1, 0)


def test_us_stock_that_is_up_to_date_is_not_requested(us: Engine) -> None:
    # given: stored through the last completed session
    _seed(us, bar("NVDA", D7, 210.0))
    batch = Batch()

    # when
    report = _run(us, EVENING, batch=batch)

    # then
    assert batch.calls == []
    assert report == UpdateReport()


def test_us_stock_is_loaded_again_when_the_overlapping_day_changed(us: Engine) -> None:
    # given: stored 200 for the 6th; after a split Yahoo now says 100 for that day
    _seed(us, bar("NVDA", D5, 190.0), bar("NVDA", D6, 200.0))
    batch = Batch([bar("NVDA", D5, 95.0), bar("NVDA", D6, 100.0), bar("NVDA", D7, 105.0)])

    # when
    report = _run(us, EVENING, batch=batch)

    # then: a recent request, then a full one
    assert [since for _, since in batch.calls] == [D6, date(2025, 9, 3)]
    assert _stored(us, "NVDA") == [(D5, 95.0), (D6, 100.0), (D7, 105.0)]
    assert report.reloaded == 1


def test_us_stock_that_yahoo_does_not_answer_keeps_its_history_and_is_reported(us: Engine) -> None:
    # given
    _seed(us, bar("NVDA", D6, 200.0))

    # when
    report = _run(us, EVENING, batch=Batch())

    # then
    assert _stored(us, "NVDA") == [(D6, 200.0)]
    assert report.failed == ("NVDA",)
