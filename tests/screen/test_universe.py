from collections.abc import Mapping
from datetime import date

from sqlalchemy import Engine

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.models import Exchange, Member
from finbrief_analyzer.screen.ranking import RankRow
from finbrief_analyzer.screen.universe import (
    Sp500UniverseSource,
    UniverseSource,
    is_common_stock,
    members_from_sp500,
    pick,
    refresh_universe,
)
from finbrief_analyzer.store.universe import members

OCTOBER = date(2026, 10, 8)


def rank_row(code: str, name: str, value: int, kind: str = "stock") -> RankRow:
    return RankRow(code, name, kind, 1000.0, 1000.0, 1, value, date(2026, 10, 7), "CLOSE")


class FakeSource:
    def __init__(self, result: list[Member] | Exception) -> None:
        self.calls = 0
        self._result = result

    def members(self, exchange: Exchange, size: int) -> list[Member]:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result[:size]


def _kospi(*names: str) -> list[Member]:
    return [Member(Exchange.KOSPI, f"{index:05d}0", name) for index, name in enumerate(names)]


def _refresh(
    engine: Engine, today: date, sources: Mapping[Exchange, UniverseSource]
) -> list[Exchange]:
    with session_scope(engine) as session:
        return refresh_universe(session, today, sources, {Exchange.KOSPI: 2, Exchange.SP500: 2})


def _stored(engine: Engine, exchange: Exchange = Exchange.KOSPI) -> list[str]:
    with session_scope(engine) as session:
        return [member.name for member in members(session, exchange)]


def test_common_stock_is_kept() -> None:
    # given / when / then
    assert is_common_stock(rank_row("005930", "삼성전자", 1))


def test_preferred_share_is_left_out_by_its_code_not_its_name() -> None:
    # given: the code of a preferred share does not end in 0
    preferred = rank_row("005935", "삼성전자우", 1)
    lookalike = rank_row("015750", "성우", 1)

    # when / then
    assert not is_common_stock(preferred)
    assert is_common_stock(lookalike)


def test_etf_and_etn_are_left_out() -> None:
    # given / when / then
    assert not is_common_stock(rank_row("069500", "KODEX 200", 1, kind="etf"))
    assert not is_common_stock(rank_row("530000", "삼성 레버리지", 1, kind="etn"))


def test_spac_is_left_out() -> None:
    # given / when / then
    assert not is_common_stock(rank_row("400000", "하나스팩30호", 1))


def test_reit_is_left_out_but_a_name_merely_containing_the_word_is_kept() -> None:
    # given
    reit = rank_row("395400", "SK리츠", 1)
    insurer = rank_row("138040", "메리츠금융지주", 1)

    # when / then
    assert not is_common_stock(reit)
    assert is_common_stock(insurer)


def test_pick_takes_the_largest_common_stocks_in_rank_order() -> None:
    # given: rows already sorted by market value, with an ETF and a preferred share mixed in
    rows = [
        rank_row("000010", "가", 9),
        rank_row("069500", "KODEX 200", 8, kind="etf"),
        rank_row("000015", "가우", 7),
        rank_row("000020", "나", 6),
        rank_row("000030", "다", 5),
    ]

    # when
    picked = pick(Exchange.KOSPI, rows, size=2)

    # then
    assert picked == [
        Member(Exchange.KOSPI, "000010", "가"),
        Member(Exchange.KOSPI, "000020", "나"),
    ]


def test_sp500_listing_becomes_members_with_yahoo_style_tickers() -> None:
    # given: a share class written with a dot, and one with the dot already stripped
    listing = [("NVDA", "Nvidia"), ("BRK.B", "Berkshire Hathaway"), ("BFB", "Brown-Forman")]

    # when
    found = members_from_sp500(listing)

    # then
    assert found == [
        Member(Exchange.SP500, "NVDA", "Nvidia"),
        Member(Exchange.SP500, "BRK-B", "Berkshire Hathaway"),
        Member(Exchange.SP500, "BF-B", "Brown-Forman"),
    ]


def test_universe_is_built_when_there_is_none_yet(store: Engine) -> None:
    # given
    source = FakeSource(_kospi("가", "나", "다"))

    # when
    refreshed = _refresh(store, OCTOBER, {Exchange.KOSPI: source})

    # then: cut to the configured size
    assert refreshed == [Exchange.KOSPI]
    assert _stored(store) == ["가", "나"]


def test_universe_is_not_rebuilt_within_the_same_month(store: Engine) -> None:
    # given
    _refresh(store, date(2026, 10, 1), {Exchange.KOSPI: FakeSource(_kospi("가", "나"))})
    later = FakeSource(_kospi("다", "라"))

    # when
    refreshed = _refresh(store, date(2026, 10, 30), {Exchange.KOSPI: later})

    # then: a stock at the boundary does not drift in and out day by day
    assert refreshed == []
    assert later.calls == 0
    assert _stored(store) == ["가", "나"]


def test_universe_is_rebuilt_when_the_month_changes(store: Engine) -> None:
    # given
    _refresh(store, date(2026, 10, 30), {Exchange.KOSPI: FakeSource(_kospi("가", "나"))})

    # when
    _refresh(store, date(2026, 11, 2), {Exchange.KOSPI: FakeSource(_kospi("다", "라"))})

    # then
    assert _stored(store) == ["다", "라"]


def test_same_month_of_another_year_is_rebuilt(store: Engine) -> None:
    # given
    _refresh(store, date(2025, 10, 30), {Exchange.KOSPI: FakeSource(_kospi("가", "나"))})

    # when
    refreshed = _refresh(store, OCTOBER, {Exchange.KOSPI: FakeSource(_kospi("다", "라"))})

    # then
    assert refreshed == [Exchange.KOSPI]


def test_failing_source_keeps_the_previous_universe_and_does_not_raise(store: Engine) -> None:
    # given
    _refresh(store, date(2026, 9, 1), {Exchange.KOSPI: FakeSource(_kospi("가", "나"))})
    broken = FakeSource(CollectError("naver-ranking", "503"))

    # when
    refreshed = _refresh(store, OCTOBER, {Exchange.KOSPI: broken})

    # then
    assert refreshed == []
    assert _stored(store) == ["가", "나"]


def test_crashing_source_does_not_raise_either(store: Engine) -> None:
    # given: a library bug, not a CollectError
    broken = FakeSource(KeyError("timestamp"))

    # when
    refreshed = _refresh(store, OCTOBER, {Exchange.KOSPI: broken})

    # then
    assert refreshed == []


def test_short_answer_is_treated_as_partial_and_keeps_the_previous_universe(store: Engine) -> None:
    # given: the source answered with fewer stocks than the universe needs
    _refresh(store, date(2026, 9, 1), {Exchange.KOSPI: FakeSource(_kospi("가", "나"))})

    # when
    refreshed = _refresh(store, OCTOBER, {Exchange.KOSPI: FakeSource(_kospi("다"))})

    # then
    assert refreshed == []
    assert _stored(store) == ["가", "나"]


def test_one_failing_exchange_does_not_stop_the_others(store: Engine) -> None:
    # given
    us = FakeSource(
        [Member(Exchange.SP500, "NVDA", "Nvidia"), Member(Exchange.SP500, "AAPL", "Apple")]
    )
    sources = {Exchange.KOSPI: FakeSource(CollectError("naver-ranking", "503")), Exchange.SP500: us}

    # when
    refreshed = _refresh(store, OCTOBER, sources)

    # then
    assert refreshed == [Exchange.SP500]
    assert _stored(store, Exchange.SP500) == ["Nvidia", "Apple"]


def test_sp500_source_returns_the_whole_index_not_an_alphabetical_cut() -> None:
    # given: three constituents, a minimum size of two
    source = Sp500UniverseSource(lambda: [("AAPL", "Apple"), ("NVDA", "Nvidia"), ("ZTS", "Zoetis")])

    # when
    found = source.members(Exchange.SP500, 2)

    # then
    assert [member.symbol for member in found] == ["AAPL", "NVDA", "ZTS"]
