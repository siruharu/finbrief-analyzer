import logging
from collections.abc import Callable
from datetime import date

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import OperationalError

from finbrief_analyzer.collect.models import Slot
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.deliver.dispatch import DispatchResult, dispatch, mask_email
from finbrief_analyzer.deliver.models import (
    Briefing,
    DeliveryError,
    DeliveryStatus,
    RenderedEmail,
    Section,
)
from finbrief_analyzer.store.delivery_log import DeliveryKey, DeliveryLog
from finbrief_analyzer.store.recipients import Recipient, list_active
from finbrief_analyzer.store.tables import delivery_log, recipients

OPERATOR = "ops@example.com"
BRIEFING = Briefing(
    slot=Slot.KR_OPEN,
    briefing_date=date(2026, 10, 8),
    sections=(Section(title="시세", lines=("KOSPI 6,803.90",), required=True),),
)
EMPTY_BRIEFING = Briefing(
    slot=Slot.KR_OPEN,
    briefing_date=date(2026, 10, 8),
    sections=(Section(title="시세", required=True),),
)


class FakeNotifier:
    """Records every attempt; raises the scripted errors for an address, in order."""

    def __init__(self, errors: dict[str, list[DeliveryError]] | None = None) -> None:
        self.attempts: list[str] = []
        self.delivered: list[tuple[str, RenderedEmail]] = []
        self._errors = errors or {}

    def send(self, recipient: str, email: RenderedEmail) -> None:
        self.attempts.append(recipient)
        scripted = self._errors.get(recipient)
        if scripted:
            raise scripted.pop(0)
        self.delivered.append((recipient, email))


class LogThatCannotMarkSent(DeliveryLog):
    def mark_sent(self, key: DeliveryKey) -> None:
        raise OperationalError("UPDATE delivery_log", {}, Exception("connection lost"))


@pytest.fixture
def people(store: Engine, add_recipient: Callable[..., int]) -> list[Recipient]:
    for name in ("a", "b", "c"):
        add_recipient(f"{name}@example.com")
    with session_scope(store) as session:
        return list_active(session)


def _statuses(engine: Engine) -> dict[str, tuple[str, str | None]]:
    query = select(recipients.c.email, delivery_log.c.status, delivery_log.c.reason).join(
        delivery_log, delivery_log.c.recipient_id == recipients.c.id
    )
    with engine.connect() as connection:
        return {row.email: (row.status, row.reason) for row in connection.execute(query)}


def _temporary() -> DeliveryError:
    return DeliveryError("SMTPDataError code=451", retryable=True)


def test_every_claimed_recipient_gets_the_briefing(store: Engine, people: list[Recipient]) -> None:
    # given
    notifier = FakeNotifier()

    # when
    result = dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then
    assert result == DispatchResult(sent=3)
    assert [address for address, _ in notifier.delivered] == [p.email for p in people]
    assert {status for status, _ in _statuses(store).values()} == {DeliveryStatus.SENT}


def test_already_claimed_recipient_is_skipped_and_counted(
    store: Engine, people: list[Recipient]
) -> None:
    # given: another process already took the first recipient
    log = DeliveryLog(store)
    log.claim(DeliveryKey.for_email(BRIEFING, people[0].id))
    notifier = FakeNotifier()

    # when
    result = dispatch(BRIEFING, people, notifier, log)

    # then
    assert result == DispatchResult(sent=2, skipped=1)
    assert people[0].email not in notifier.attempts


def test_one_failed_recipient_does_not_stop_the_others(
    store: Engine, people: list[Recipient]
) -> None:
    # given: the middle recipient is refused
    refused = DeliveryError("SMTPRecipientsRefused: recipient refused", retryable=False)
    notifier = FakeNotifier({"b@example.com": [refused]})

    # when
    result = dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then
    assert result == DispatchResult(sent=2, failed=1)
    assert [address for address, _ in notifier.delivered] == ["a@example.com", "c@example.com"]


def test_failed_delivery_is_recorded_with_its_reason(
    store: Engine, people: list[Recipient]
) -> None:
    # given
    refused = DeliveryError("SMTPRecipientsRefused: recipient refused", retryable=False)
    notifier = FakeNotifier({"b@example.com": [refused]})

    # when
    dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then
    assert _statuses(store)["b@example.com"] == (
        DeliveryStatus.FAILED,
        "SMTPRecipientsRefused: recipient refused",
    )


def test_retryable_error_is_retried_once_and_can_succeed(
    store: Engine, people: list[Recipient]
) -> None:
    # given: the first attempt hits a temporary error
    notifier = FakeNotifier({"a@example.com": [_temporary()]})

    # when
    result = dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then
    assert result == DispatchResult(sent=3)
    assert notifier.attempts.count("a@example.com") == 2


def test_retryable_error_twice_in_a_row_is_recorded_as_failed(
    store: Engine, people: list[Recipient]
) -> None:
    # given
    notifier = FakeNotifier({"a@example.com": [_temporary(), _temporary()]})

    # when
    result = dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then: no third attempt; the next run can claim it again
    assert result == DispatchResult(sent=2, failed=1)
    assert notifier.attempts.count("a@example.com") == 2
    assert _statuses(store)["a@example.com"][0] == DeliveryStatus.FAILED


def test_fatal_error_stops_the_run_as_aborted(store: Engine, people: list[Recipient]) -> None:
    # given: the app password was revoked
    auth = DeliveryError("SMTPAuthenticationError code=535", retryable=False, fatal=True)
    notifier = FakeNotifier({"a@example.com": [auth]})

    # when
    result = dispatch(BRIEFING, people, notifier, DeliveryLog(store), operator_email=OPERATOR)

    # then: nobody after the first was tried, and no notice went through the broken channel
    assert result.aborted is True
    assert (result.sent, result.failed) == (0, 1)
    assert notifier.attempts == ["a@example.com"]


def test_recipients_not_tried_in_an_aborted_run_are_left_unclaimed(
    store: Engine, people: list[Recipient]
) -> None:
    # given
    auth = DeliveryError("SMTPAuthenticationError code=535", retryable=False, fatal=True)
    notifier = FakeNotifier({"a@example.com": [auth]})

    # when
    dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then: only the one that was tried has a row, and it can be claimed again
    assert list(_statuses(store)) == ["a@example.com"]
    assert _statuses(store)["a@example.com"][0] == DeliveryStatus.FAILED


def test_unsendable_briefing_goes_to_nobody_but_the_operator(
    store: Engine, people: list[Recipient]
) -> None:
    # given: the required section is empty
    notifier = FakeNotifier()

    # when
    result = dispatch(EMPTY_BRIEFING, people, notifier, DeliveryLog(store), operator_email=OPERATOR)

    # then
    assert result.aborted is True
    assert notifier.attempts == [OPERATOR]
    assert _statuses(store) == {}


def test_unsendable_briefing_without_an_operator_address_sends_nothing(
    store: Engine, people: list[Recipient]
) -> None:
    # given
    notifier = FakeNotifier()

    # when
    result = dispatch(EMPTY_BRIEFING, people, notifier, DeliveryLog(store))

    # then
    assert result.aborted is True
    assert notifier.attempts == []


def test_failing_operator_notice_does_not_raise(store: Engine, people: list[Recipient]) -> None:
    # given: the notice itself cannot be delivered
    notifier = FakeNotifier({OPERATOR: [_temporary()]})

    # when
    result = dispatch(EMPTY_BRIEFING, people, notifier, DeliveryLog(store), operator_email=OPERATOR)

    # then
    assert result.aborted is True


def test_second_run_with_the_same_input_sends_nothing(
    store: Engine, people: list[Recipient]
) -> None:
    # given: a completed run
    log = DeliveryLog(store)
    dispatch(BRIEFING, people, FakeNotifier(), log)
    notifier = FakeNotifier()

    # when
    result = dispatch(BRIEFING, people, notifier, log)

    # then
    assert result == DispatchResult(skipped=3)
    assert notifier.attempts == []


def test_no_recipients_is_a_normal_empty_run(store: Engine) -> None:
    # given
    notifier = FakeNotifier()

    # when
    result = dispatch(BRIEFING, [], notifier, DeliveryLog(store))

    # then
    assert result == DispatchResult()
    assert notifier.attempts == []


def test_delivery_stays_pending_and_counts_as_sent_when_recording_fails(
    store: Engine, people: list[Recipient]
) -> None:
    # given: the mail goes out but the database drops before the result is written
    notifier = FakeNotifier()

    # when
    result = dispatch(BRIEFING, people[:1], notifier, LogThatCannotMarkSent(store))

    # then: pending blocks a second send on the next run
    assert result == DispatchResult(sent=1)
    assert _statuses(store)["a@example.com"][0] == DeliveryStatus.PENDING


def test_log_output_never_contains_a_full_recipient_address(
    store: Engine, people: list[Recipient], caplog: pytest.LogCaptureFixture
) -> None:
    # given
    refused = DeliveryError("SMTPRecipientsRefused: recipient refused", retryable=False)
    notifier = FakeNotifier({"b@example.com": [refused]})

    # when
    with caplog.at_level(logging.DEBUG):
        dispatch(BRIEFING, people, notifier, DeliveryLog(store))

    # then
    assert "b@example.com" not in caplog.text
    assert "b***@example.com" in caplog.text


def test_mask_email_keeps_two_characters_and_the_domain() -> None:
    # given / when / then
    assert mask_email("hotman@naver.com") == "ho***@naver.com"
    assert mask_email("a@b.com") == "a***@b.com"
    assert mask_email("not-an-address") == "***"
