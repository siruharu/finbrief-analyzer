"""Combine a primary quote provider with backups for the symbols it could not answer."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from finbrief_analyzer.collect.models import CollectError, Quote
from finbrief_analyzer.collect.ports import QuoteProvider

logger = logging.getLogger(__name__)


class BackupQuoteProvider(QuoteProvider, Protocol):
    def supports(self, symbol: str) -> bool:
        """Whether this provider can answer the symbol at all."""
        ...


@dataclass(frozen=True, slots=True)
class QuoteResult:
    quotes: tuple[Quote, ...]
    # Symbols no provider could answer, in the requested order.
    missing: tuple[str, ...]


class FallbackQuoteProvider:
    """Not a QuoteProvider: it reports failures as `missing` and never raises."""

    def __init__(self, primary: QuoteProvider, backups: Sequence[BackupQuoteProvider]) -> None:
        self._primary = primary
        self._backups = backups

    def get_quotes(self, symbols: Sequence[str]) -> QuoteResult:
        found: dict[str, Quote] = {}
        if symbols:
            _merge(found, self._primary, symbols)
        for backup in self._backups:
            pending = [s for s in symbols if s not in found and backup.supports(s)]
            if pending:
                _merge(found, backup, pending)
        return QuoteResult(
            quotes=tuple(found[s] for s in symbols if s in found),
            missing=tuple(s for s in symbols if s not in found),
        )


def _merge(found: dict[str, Quote], provider: QuoteProvider, symbols: Sequence[str]) -> None:
    """Add the provider's answers for `symbols`; an earlier provider's quote is kept."""
    for quote in _ask(provider, symbols):
        if quote.symbol in symbols:
            found.setdefault(quote.symbol, quote)


def _ask(provider: QuoteProvider, symbols: Sequence[str]) -> Sequence[Quote]:
    try:
        return provider.get_quotes(symbols)
    except CollectError as error:
        logger.warning("quote provider failed: %s", error)
    except Exception:
        # A crash in a third-party library must not take the briefing down with it.
        logger.exception("quote provider crashed: %s", provider.name)
    return ()
