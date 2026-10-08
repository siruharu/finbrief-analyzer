"""SMTP notifier. One connection is opened on first use and reused until close()."""

import contextlib
import smtplib
from collections.abc import Callable
from email.headerregistry import Address
from email.message import EmailMessage
from typing import Protocol

from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.deliver.models import DeliveryError, RenderedEmail


class SmtpConnection(Protocol):
    """The part of smtplib.SMTP this module uses."""

    def starttls(self) -> object: ...
    def login(self, user: str, password: str) -> object: ...
    def send_message(self, msg: EmailMessage) -> object: ...
    def quit(self) -> object: ...


Connect = Callable[[str, int, float], SmtpConnection]


def _open(host: str, port: int, timeout: float) -> SmtpConnection:
    # Debug output stays off: it prints the encoded credentials.
    return smtplib.SMTP(host, port, timeout=timeout)


def _quit_quietly(connection: SmtpConnection) -> None:
    # The server may already be gone; there is nothing left to release then.
    with contextlib.suppress(smtplib.SMTPException, OSError):
        connection.quit()


def _classify(exc: Exception) -> DeliveryError:
    """Translate a library error. The message is built here; server text is never copied in."""
    name = type(exc).__name__
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return DeliveryError(f"{name} code={exc.smtp_code}", retryable=False, fatal=True)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return DeliveryError(f"{name}: recipient refused", retryable=False)
    if isinstance(exc, smtplib.SMTPResponseException):
        temporary = 400 <= exc.smtp_code < 500
        return DeliveryError(f"{name} code={exc.smtp_code}", retryable=temporary)
    if isinstance(exc, smtplib.SMTPServerDisconnected | OSError):
        return DeliveryError(f"{name}: connection failed", retryable=True)
    return DeliveryError(name, retryable=False)


class SmtpNotifier:
    def __init__(self, settings: Settings, connect: Connect = _open) -> None:
        missing = [
            name
            for name, value in (
                ("APP_SMTP_USER", settings.smtp_user),
                ("APP_SMTP_PASSWORD", settings.smtp_password),
            )
            if value is None
        ]
        if missing or settings.smtp_user is None or settings.smtp_password is None:
            raise ValueError(f"smtp is not configured, missing: {', '.join(missing)}")
        self._user = settings.smtp_user
        # Google shows app passwords in groups of four; the spaces are not part of it.
        self._password = settings.smtp_password.get_secret_value().replace(" ", "")
        self._sender = Address(display_name=settings.mail_from_name, addr_spec=self._user)
        self._endpoint = (settings.smtp_host, settings.smtp_port, settings.smtp_timeout_seconds)
        self._connect = connect
        self._connection: SmtpConnection | None = None

    def send(self, recipient: str, email: RenderedEmail) -> None:
        """Deliver one message to one recipient. Raises DeliveryError on failure."""
        if "\n" in recipient or "\r" in recipient:
            raise DeliveryError("recipient address contains a line break", retryable=False)
        message = self._build_message(recipient, email)
        try:
            self._connected().send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            error = _classify(exc)
            if error.retryable or error.fatal:
                # The connection is in an unknown state; the next send starts a new one.
                self.close()
            raise error from None

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            _quit_quietly(connection)

    def _connected(self) -> SmtpConnection:
        if self._connection is None:
            connection = self._connect(*self._endpoint)
            try:
                connection.starttls()
                connection.login(self._user, self._password)
            except (smtplib.SMTPException, OSError):
                _quit_quietly(connection)
                raise
            self._connection = connection
        return self._connection

    def _build_message(self, recipient: str, email: RenderedEmail) -> EmailMessage:
        # EmailMessage encodes non-ASCII headers; no header string is assembled by hand.
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = recipient
        message["Subject"] = email.subject
        message.set_content(email.text)
        message.add_alternative(email.html, subtype="html")
        return message
