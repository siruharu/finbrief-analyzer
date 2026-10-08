import smtplib
from email.message import EmailMessage
from pathlib import Path

import pytest
from pydantic import SecretStr

from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.deliver.models import DeliveryError, RenderedEmail
from finbrief_analyzer.deliver.smtp import SmtpNotifier

PASSWORD = "abcdefghijklmnop"
EMAIL = RenderedEmail(subject="[finbrief] 국내 개장 브리핑", text="본문", html="<p>본문</p>")


class FakeSmtp:
    """Records what a notifier does to one SMTP connection."""

    def __init__(self, send_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.login_args: tuple[str, str] | None = None
        self.messages: list[EmailMessage] = []
        self.send_error = send_error
        self.login_error: Exception | None = None

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")
        self.login_args = (user, password)
        if self.login_error is not None:
            raise self.login_error

    def send_message(self, msg: EmailMessage) -> None:
        self.calls.append("send")
        if self.send_error is not None:
            raise self.send_error
        self.messages.append(msg)

    def quit(self) -> None:
        self.calls.append("quit")


class Connector:
    """Hands out prepared connections in order and remembers how it was called."""

    def __init__(self, *connections: FakeSmtp) -> None:
        self._pending = list(connections)
        self.opened: list[tuple[str, int, float]] = []

    def __call__(self, host: str, port: int, timeout: float) -> FakeSmtp:
        self.opened.append((host, port, timeout))
        return self._pending.pop(0)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings reads ".env" relative to the working directory; keep the developer's file out.
    monkeypatch.chdir(tmp_path)
    for key in ("USER", "PASSWORD", "HOST", "PORT"):
        monkeypatch.delenv(f"APP_SMTP_{key}", raising=False)


def _settings(password: str = PASSWORD) -> Settings:
    return Settings(
        smtp_user="sender@gmail.com",
        smtp_password=SecretStr(password),
        mail_from_name="핀브리프",
    )


def _notifier(*connections: FakeSmtp) -> tuple[SmtpNotifier, Connector]:
    connector = Connector(*connections)
    return SmtpNotifier(_settings(), connect=connector), connector


def test_message_is_multipart_with_a_text_and_an_html_part() -> None:
    # given
    smtp = FakeSmtp()
    notifier, _ = _notifier(smtp)

    # when
    notifier.send("to@example.com", EMAIL)

    # then
    message = smtp.messages[0]
    parts = [part.get_content_type() for part in message.iter_parts()]
    assert message.get_content_type() == "multipart/alternative"
    assert parts == ["text/plain", "text/html"]


def test_from_is_the_display_name_and_the_configured_account() -> None:
    # given
    smtp = FakeSmtp()
    notifier, _ = _notifier(smtp)

    # when
    notifier.send("to@example.com", EMAIL)

    # then
    sender = smtp.messages[0]["From"].addresses[0]
    assert (sender.display_name, sender.addr_spec) == ("핀브리프", "sender@gmail.com")


def test_to_is_the_single_recipient() -> None:
    # given
    smtp = FakeSmtp()
    notifier, _ = _notifier(smtp)

    # when
    notifier.send("to@example.com", EMAIL)

    # then
    message = smtp.messages[0]
    assert [address.addr_spec for address in message["To"].addresses] == ["to@example.com"]
    assert message["Cc"] is None
    assert message["Bcc"] is None


def test_korean_subject_survives_header_encoding() -> None:
    # given
    smtp = FakeSmtp()
    notifier, _ = _notifier(smtp)

    # when
    notifier.send("to@example.com", EMAIL)

    # then
    assert smtp.messages[0]["Subject"] == EMAIL.subject


def test_starttls_comes_before_login() -> None:
    # given
    smtp = FakeSmtp()
    notifier, _ = _notifier(smtp)

    # when
    notifier.send("to@example.com", EMAIL)

    # then
    assert smtp.calls == ["starttls", "login", "send"]


def test_connection_uses_the_configured_host_port_and_timeout() -> None:
    # given
    notifier, connector = _notifier(FakeSmtp())

    # when
    notifier.send("to@example.com", EMAIL)

    # then: never the library default of waiting forever
    assert connector.opened == [("smtp.gmail.com", 587, 30.0)]


def test_spaces_in_the_app_password_are_removed_before_login() -> None:
    # given: the password as Google displays it, in groups of four
    smtp = FakeSmtp()
    connector = Connector(smtp)
    notifier = SmtpNotifier(_settings("abcd efgh ijkl mnop"), connect=connector)

    # when
    notifier.send("to@example.com", EMAIL)

    # then
    assert smtp.login_args == ("sender@gmail.com", "abcdefghijklmnop")


def test_one_connection_is_reused_for_every_recipient() -> None:
    # given
    smtp = FakeSmtp()
    notifier, connector = _notifier(smtp)

    # when
    notifier.send("a@example.com", EMAIL)
    notifier.send("b@example.com", EMAIL)

    # then
    assert len(connector.opened) == 1
    assert smtp.calls == ["starttls", "login", "send", "send"]


def test_authentication_failure_becomes_a_fatal_non_retryable_error() -> None:
    # given
    smtp = FakeSmtp()
    smtp.login_error = smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
    notifier, _ = _notifier(smtp)

    # when
    with pytest.raises(DeliveryError) as raised:
        notifier.send("to@example.com", EMAIL)

    # then
    assert raised.value.retryable is False
    assert raised.value.fatal is True
    # and the half-open connection was released
    assert smtp.calls == ["starttls", "login", "quit"]


def test_temporary_server_response_becomes_a_retryable_error() -> None:
    # given
    smtp = FakeSmtp(send_error=smtplib.SMTPDataError(451, b"Temporary local problem"))
    notifier, _ = _notifier(smtp)

    # when
    with pytest.raises(DeliveryError) as raised:
        notifier.send("to@example.com", EMAIL)

    # then
    assert raised.value.retryable is True
    assert raised.value.fatal is False


def test_refused_recipient_fails_only_that_recipient() -> None:
    # given
    refused = smtplib.SMTPRecipientsRefused({"bad@example.com": (550, b"No such user")})
    smtp = FakeSmtp(send_error=refused)
    notifier, connector = _notifier(smtp)

    # when
    with pytest.raises(DeliveryError) as raised:
        notifier.send("bad@example.com", EMAIL)
    smtp.send_error = None
    notifier.send("good@example.com", EMAIL)

    # then: not retryable, not fatal, and the connection is still in use
    assert (raised.value.retryable, raised.value.fatal) == (False, False)
    assert len(connector.opened) == 1
    assert len(smtp.messages) == 1


def test_next_send_reconnects_after_the_connection_dropped() -> None:
    # given: the first connection dies mid-send
    broken = FakeSmtp(send_error=smtplib.SMTPServerDisconnected("Connection unexpectedly closed"))
    fresh = FakeSmtp()
    notifier, connector = _notifier(broken, fresh)

    # when
    with pytest.raises(DeliveryError) as raised:
        notifier.send("a@example.com", EMAIL)
    notifier.send("a@example.com", EMAIL)

    # then
    assert raised.value.retryable is True
    assert len(connector.opened) == 2
    assert fresh.calls == ["starttls", "login", "send"]


def test_failure_to_connect_is_a_retryable_error() -> None:
    # given: the network is down
    def unreachable(host: str, port: int, timeout: float) -> FakeSmtp:
        raise TimeoutError("timed out")

    notifier = SmtpNotifier(_settings(), connect=unreachable)

    # when / then
    with pytest.raises(DeliveryError) as raised:
        notifier.send("to@example.com", EMAIL)
    assert raised.value.retryable is True


def test_app_password_is_not_in_the_error_message() -> None:
    # given: a server that echoes the credentials back in its reply
    smtp = FakeSmtp()
    smtp.login_error = smtplib.SMTPAuthenticationError(535, f"bad {PASSWORD}".encode())
    notifier, _ = _notifier(smtp)

    # when
    with pytest.raises(DeliveryError) as raised:
        notifier.send("to@example.com", EMAIL)

    # then
    assert PASSWORD not in str(raised.value)
    assert PASSWORD not in repr(raised.value)


def test_recipient_with_a_line_break_is_rejected_before_connecting() -> None:
    # given: an address that would inject a header
    notifier, connector = _notifier(FakeSmtp())

    # when / then
    with pytest.raises(DeliveryError) as raised:
        notifier.send("to@example.com\nBcc: evil@example.com", EMAIL)
    assert raised.value.retryable is False
    assert connector.opened == []


def test_missing_smtp_settings_fail_at_construction_naming_the_variables() -> None:
    # given: no account configured
    settings = Settings()

    # when / then
    with pytest.raises(ValueError, match="APP_SMTP_USER") as raised:
        SmtpNotifier(settings)
    assert "APP_SMTP_PASSWORD" in str(raised.value)


def test_close_quits_the_open_connection_and_tolerates_a_dead_one() -> None:
    # given
    smtp = FakeSmtp()
    notifier, _ = _notifier(smtp)
    notifier.send("to@example.com", EMAIL)

    # when
    notifier.close()
    notifier.close()

    # then
    assert smtp.calls.count("quit") == 1
