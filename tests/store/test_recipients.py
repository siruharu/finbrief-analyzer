from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.store.recipients import Recipient, list_active


def test_inactive_recipient_is_not_listed(store: Engine, add_recipient: Callable[..., int]) -> None:
    # given
    active_id = add_recipient("a@example.com", name="가")
    add_recipient("b@example.com", active=False)

    # when
    with session_scope(store) as session:
        found = list_active(session)

    # then
    assert found == [Recipient(id=active_id, email="a@example.com", name="가")]


def test_active_recipients_come_back_in_registration_order(
    store: Engine, add_recipient: Callable[..., int]
) -> None:
    # given
    add_recipient("z@example.com")
    add_recipient("a@example.com")

    # when
    with session_scope(store) as session:
        emails = [recipient.email for recipient in list_active(session)]

    # then
    assert emails == ["z@example.com", "a@example.com"]


def test_the_same_email_cannot_be_registered_twice(
    store: Engine, add_recipient: Callable[..., int]
) -> None:
    # given
    add_recipient("a@example.com")

    # when / then
    with pytest.raises(IntegrityError):
        add_recipient("a@example.com")
