"""Notifier interface. Channels satisfy it structurally; nothing here does I/O."""

from typing import Protocol

from finbrief_analyzer.deliver.models import RenderedEmail


class Notifier(Protocol):
    def send(self, recipient: str, email: RenderedEmail) -> None:
        """Deliver one message to one recipient. Raises DeliveryError on failure."""
        ...
