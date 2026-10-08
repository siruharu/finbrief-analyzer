"""The contract between whatever writes a briefing and whatever delivers it."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from finbrief_analyzer.collect.models import Slot


class Channel(StrEnum):
    EMAIL = "email"


class DeliveryStatus(StrEnum):
    """State of one (briefing, recipient, channel) delivery."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class DeliveryError(Exception):
    """A notifier could not deliver.

    `retryable`: trying the same message again can help.
    `fatal`: the channel itself is unusable (bad credentials), so other recipients will fail too.
    """

    def __init__(self, message: str, *, retryable: bool, fatal: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.fatal = fatal


@dataclass(frozen=True, slots=True)
class LinkItem:
    """One headline. The title and url come from outside and are not trusted."""

    title: str
    url: str | None = None
    source: str = ""

    @property
    def safe_url(self) -> str | None:
        """The url if it is plain http(s), otherwise None so it is never rendered as a link."""
        if self.url is None or not self.url.lower().startswith(("http://", "https://")):
            return None
        return self.url


@dataclass(frozen=True, slots=True)
class Section:
    """A titled block: free-form lines, a list of headlines, or both."""

    title: str
    lines: tuple[str, ...] = ()
    links: tuple[LinkItem, ...] = ()
    # A briefing whose required section is empty must not be sent.
    required: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.lines and not self.links


@dataclass(frozen=True, slots=True)
class Briefing:
    """What one slot's briefing says, independent of the channel it goes out on."""

    slot: Slot
    briefing_date: date
    sections: tuple[Section, ...] = ()
    # Shown above the first section: missing sources, closed markets.
    notices: tuple[str, ...] = ()

    @property
    def is_sendable(self) -> bool:
        """True when there is at least one required section and none of them is empty."""
        required = [section for section in self.sections if section.required]
        return bool(required) and not any(section.is_empty for section in required)


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str
