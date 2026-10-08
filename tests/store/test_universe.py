from datetime import date

from sqlalchemy import Engine

from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.screen.models import Exchange, Member
from finbrief_analyzer.store.universe import built_on, members, replace_members

SAMSUNG = Member(Exchange.KOSPI, "005930", "삼성전자")
HYNIX = Member(Exchange.KOSPI, "000660", "SK하이닉스")
ALTEOGEN = Member(Exchange.KOSDAQ, "196170", "알테오젠")


def _replace(engine: Engine, exchange: Exchange, day: date, *new: Member) -> None:
    with session_scope(engine) as session:
        replace_members(session, exchange, new, day)


def _members(engine: Engine, exchange: Exchange) -> list[Member]:
    with session_scope(engine) as session:
        return members(session, exchange)


def test_members_come_back_in_the_order_they_were_given(store: Engine) -> None:
    # given: ranked by market value
    _replace(store, Exchange.KOSPI, date(2026, 10, 1), SAMSUNG, HYNIX)

    # when / then
    assert _members(store, Exchange.KOSPI) == [SAMSUNG, HYNIX]


def test_replacing_leaves_only_the_new_composition(store: Engine) -> None:
    # given
    _replace(store, Exchange.KOSPI, date(2026, 10, 1), SAMSUNG, HYNIX)

    # when: next month one stock dropped out
    _replace(store, Exchange.KOSPI, date(2026, 11, 2), HYNIX)

    # then
    assert _members(store, Exchange.KOSPI) == [HYNIX]


def test_replacing_one_exchange_leaves_the_others_alone(store: Engine) -> None:
    # given
    _replace(store, Exchange.KOSPI, date(2026, 10, 1), SAMSUNG)
    _replace(store, Exchange.KOSDAQ, date(2026, 10, 1), ALTEOGEN)

    # when
    _replace(store, Exchange.KOSPI, date(2026, 11, 2), HYNIX)

    # then
    assert _members(store, Exchange.KOSDAQ) == [ALTEOGEN]


def test_built_on_is_the_day_the_composition_was_stored(store: Engine) -> None:
    # given
    _replace(store, Exchange.KOSPI, date(2026, 10, 1), SAMSUNG)

    # when
    with session_scope(store) as session:
        found = built_on(session, Exchange.KOSPI)

    # then
    assert found == date(2026, 10, 1)


def test_built_on_is_none_before_the_first_composition(store: Engine) -> None:
    # given: nothing stored
    # when
    with session_scope(store) as session:
        found = built_on(session, Exchange.SP500)

    # then
    assert found is None


def test_same_symbol_listed_twice_is_stored_once(store: Engine) -> None:
    # given / when: a ranking page listed the same stock twice
    _replace(store, Exchange.KOSPI, date(2026, 10, 1), SAMSUNG, HYNIX, SAMSUNG)

    # then
    assert _members(store, Exchange.KOSPI) == [SAMSUNG, HYNIX]
