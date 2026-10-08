import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from finbrief_analyzer.collect.models import Market, MarketSnapshot, NewsItem, Quote, Slot
from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.core.db import session_scope
from finbrief_analyzer.deliver.models import DeliveryError, RenderedEmail
from finbrief_analyzer.jobs.run_briefing import JobDeps, briefing_date, main, open_deps, run
from finbrief_analyzer.store.delivery_log import DeliveryLog
from finbrief_analyzer.store.recipients import Recipient, list_active

# 2026-10-08 00:00 UTC = 09:00 in Seoul, 20:00 the evening before in New York.
NOW = datetime(2026, 10, 8, 0, 0, tzinfo=UTC)
SECRET = "abcdefghijklmnop"
SP500 = Quote(
    "US500", 7818.93, date(2026, 10, 7), prev_close=7742.5, name="S&P 500", market=Market.US
)
NEWS = NewsItem("기사", "https://example.com/1", "연합뉴스", NOW)


class FakeNotifier:
    def __init__(self, errors: dict[str, DeliveryError] | None = None) -> None:
        self.delivered: list[tuple[str, RenderedEmail]] = []
        self._errors = errors or {}

    def send(self, recipient: str, email: RenderedEmail) -> None:
        if recipient in self._errors:
            raise self._errors[recipient]
        self.delivered.append((recipient, email))


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def deps(
    store: Engine, add_recipient: Callable[..., int], notifier: FakeNotifier
) -> Callable[..., JobDeps]:
    """Build job dependencies around the test database and a prepared snapshot."""
    add_recipient("first@example.com")
    add_recipient("second@example.com")

    def build(snapshot: MarketSnapshot | None = None) -> JobDeps:
        fixed = snapshot or MarketSnapshot(Slot.KR_OPEN, quotes=(SP500,), news=(NEWS,))

        def recipients() -> list[Recipient]:
            with session_scope(store) as session:
                return list_active(session)

        return JobDeps(
            collect=lambda slot, now: fixed,
            recipients=recipients,
            notifier=notifier,
            log=DeliveryLog(store),
        )

    return build


def _factory(job_deps: JobDeps) -> Callable[[Settings], AbstractContextManager[JobDeps]]:
    @contextmanager
    def opened(settings: Settings) -> Iterator[JobDeps]:
        yield job_deps

    return opened


def test_briefing_date_is_the_local_date_of_the_market_about_to_open() -> None:
    # given: the same instant
    # when / then: Seoul is already on the 8th, New York still on the 7th
    assert briefing_date(Slot.KR_OPEN, NOW) == date(2026, 10, 8)
    assert briefing_date(Slot.US_OPEN, NOW) == date(2026, 10, 7)


def test_successful_run_sends_to_every_recipient_and_exits_zero(
    deps: Callable[..., JobDeps], notifier: FakeNotifier, caplog: pytest.LogCaptureFixture
) -> None:
    # given
    job_deps = deps()

    # when
    with caplog.at_level(logging.INFO):
        code = main(["--slot", "kr_open"], open_job=_factory(job_deps), now=NOW)

    # then: both got it, and the summary is in the log
    assert code == 0
    assert [address for address, _ in notifier.delivered] == [
        "first@example.com",
        "second@example.com",
    ]
    assert "sent=2" in caplog.text
    assert "failed=0" in caplog.text


def test_sent_mail_contains_the_quotes_and_the_news_link(
    deps: Callable[..., JobDeps], notifier: FakeNotifier
) -> None:
    # given / when
    run(Slot.KR_OPEN, NOW, deps())

    # then
    email = notifier.delivered[0][1]
    assert "국내 개장" in email.subject
    assert "2026-10-08" in email.subject
    assert "S&P 500 7,818.93 (+0.99%)" in email.text
    assert "https://example.com/1" in email.text


def test_briefing_is_still_sent_when_the_reported_market_was_closed(
    deps: Callable[..., JobDeps], notifier: FakeNotifier
) -> None:
    # given: the US market was closed, so the values are from the session before
    closed = MarketSnapshot(Slot.KR_OPEN, quotes=(SP500,), closed_markets=frozenset({Market.US}))

    # when
    result = run(Slot.KR_OPEN, NOW, deps(closed))

    # then: sent, with the notice above the quotes
    assert result.sent == 2
    text = notifier.delivered[0][1].text
    assert "휴장" in text
    assert text.index("휴장") < text.index("S&P 500")


def test_unknown_slot_argument_exits_non_zero() -> None:
    # given / when
    with pytest.raises(SystemExit) as raised:
        main(["--slot", "lunch"])

    # then
    assert raised.value.code != 0


def test_aborted_dispatch_exits_non_zero(deps: Callable[..., JobDeps]) -> None:
    # given: every quote source failed, so there is nothing worth sending
    empty = MarketSnapshot(Slot.KR_OPEN, missing=("quotes",))

    # when
    code = main(["--slot", "kr_open"], open_job=_factory(deps(empty)), now=NOW)

    # then
    assert code != 0


def test_partial_failure_exits_zero_and_logs_the_failure_count(
    store: Engine,
    deps: Callable[..., JobDeps],
    notifier: FakeNotifier,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # given: one recipient is refused
    notifier._errors["second@example.com"] = DeliveryError("recipient refused", retryable=False)

    # when
    with caplog.at_level(logging.INFO):
        code = main(["--slot", "kr_open"], open_job=_factory(deps()), now=NOW)

    # then
    assert code == 0
    assert "sent=1" in caplog.text
    assert "failed=1" in caplog.text


def test_unhandled_error_is_logged_and_exits_non_zero(
    deps: Callable[..., JobDeps], caplog: pytest.LogCaptureFixture
) -> None:
    # given: collection blows up in a way nothing anticipated
    job_deps = deps()

    def explode(slot: Slot, now: datetime) -> MarketSnapshot:
        raise RuntimeError("unexpected")

    broken = JobDeps(explode, job_deps.recipients, job_deps.notifier, job_deps.log)

    # when
    with caplog.at_level(logging.ERROR):
        code = main(["--slot", "kr_open"], open_job=_factory(broken), now=NOW)

    # then
    assert code != 0
    assert "unexpected" in caplog.text


def test_log_has_no_full_recipient_address(
    deps: Callable[..., JobDeps], notifier: FakeNotifier, caplog: pytest.LogCaptureFixture
) -> None:
    # given: one success and one failure, so both log paths run
    notifier._errors["second@example.com"] = DeliveryError("recipient refused", retryable=False)

    # when
    with caplog.at_level(logging.DEBUG):
        main(["--slot", "kr_open"], open_job=_factory(deps()), now=NOW)

    # then
    assert "first@example.com" not in caplog.text
    assert "second@example.com" not in caplog.text


def test_open_deps_fails_before_collecting_when_smtp_is_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given: no account in the environment or in a .env file
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_SMTP_USER", raising=False)
    monkeypatch.delenv("APP_SMTP_PASSWORD", raising=False)

    # when / then
    with pytest.raises(ValueError, match="APP_SMTP_USER"), open_deps(Settings()):
        pass


def test_open_deps_error_for_a_missing_database_does_not_leak_the_smtp_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given: smtp is configured, the database is not
    monkeypatch.chdir(tmp_path)
    for key in ("HOST", "NAME", "USER", "PASSWORD"):
        monkeypatch.delenv(f"APP_DB_{key}", raising=False)
    settings = Settings(smtp_user="sender@gmail.com", smtp_password=SecretStr(SECRET))

    # when / then
    with pytest.raises(ValueError, match="APP_DB_HOST") as raised, open_deps(settings):
        pass
    assert SECRET not in str(raised.value)
