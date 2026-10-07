from collections.abc import Sequence
from datetime import date

from finbrief_analyzer.collect.models import CollectError, Quote
from finbrief_analyzer.collect.quotes_fallback import FallbackQuoteProvider, QuoteResult


class _Fake:
    """Provider that answers for `has` and records what it was asked."""

    def __init__(
        self,
        name: str,
        has: Sequence[str] = (),
        supported: Sequence[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.calls: list[list[str]] = []
        self._has = has
        self._supported = supported
        self._error = error

    def supports(self, symbol: str) -> bool:
        return self._supported is None or symbol in self._supported

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        self.calls.append(list(symbols))
        if self._error is not None:
            raise self._error
        found = [_quote(s, self.name) for s in symbols if s in self._has]
        if not found:
            raise CollectError(self.name, "no data")
        return found


def _quote(symbol: str, source: str) -> Quote:
    # The close encodes which provider answered.
    return Quote(symbol=symbol, close=float(len(source)), as_of=date(2026, 10, 7))


def test_backup_is_not_called_when_primary_answers_every_symbol() -> None:
    # given
    primary = _Fake("primary", has=["^KS11", "IXIC"])
    backup = _Fake("backup", has=["^KS11", "IXIC"])

    # when
    result = FallbackQuoteProvider(primary, [backup]).get_quotes(["^KS11", "IXIC"])

    # then
    assert backup.calls == []
    assert [q.symbol for q in result.quotes] == ["^KS11", "IXIC"]
    assert result.missing == ()


def test_only_symbols_the_primary_failed_go_to_the_backup() -> None:
    # given
    primary = _Fake("primary", has=["IXIC"])
    backup = _Fake("backup", has=["^KS11", "IXIC"])

    # when
    result = FallbackQuoteProvider(primary, [backup]).get_quotes(["^KS11", "IXIC"])

    # then
    assert backup.calls == [["^KS11"]]
    assert {q.symbol for q in result.quotes} == {"^KS11", "IXIC"}


def test_symbol_failed_by_both_is_left_out_and_reported_missing() -> None:
    # given
    primary = _Fake("primary", has=["IXIC"])
    backup = _Fake("backup", has=[])

    # when
    result = FallbackQuoteProvider(primary, [backup]).get_quotes(["^KS11", "IXIC", "DJI"])

    # then
    assert [q.symbol for q in result.quotes] == ["IXIC"]
    assert result.missing == ("^KS11", "DJI")


def test_symbol_the_backup_does_not_support_is_not_sent_to_it() -> None:
    # given
    primary = _Fake("primary", has=[])
    backup = _Fake("backup", has=["IXIC"], supported=["IXIC"])

    # when
    result = FallbackQuoteProvider(primary, [backup]).get_quotes(["^KS11", "IXIC"])

    # then
    assert backup.calls == [["IXIC"]]
    assert result.missing == ("^KS11",)


def test_each_symbol_goes_to_the_backup_that_supports_it() -> None:
    # given: the real wiring, Naver for Korean indices and yfinance for US ones
    primary = _Fake("primary", has=[])
    naver = _Fake("naver", has=["^KS11"], supported=["^KS11", "^KQ11"])
    yahoo = _Fake("yf", has=["IXIC"], supported=["IXIC"])

    # when
    result = FallbackQuoteProvider(primary, [naver, yahoo]).get_quotes(["^KS11", "IXIC"])

    # then
    assert naver.calls == [["^KS11"]]
    assert yahoo.calls == [["IXIC"]]
    assert result.missing == ()


def test_quotes_keep_the_requested_order_whoever_answered() -> None:
    # given
    primary = _Fake("primary", has=["DJI"])
    backup = _Fake("backup", has=["^KS11", "IXIC"])

    # when
    result = FallbackQuoteProvider(primary, [backup]).get_quotes(["^KS11", "DJI", "IXIC"])

    # then
    assert [q.symbol for q in result.quotes] == ["^KS11", "DJI", "IXIC"]


def test_primary_quote_wins_over_a_backup_quote_for_the_same_symbol() -> None:
    # given: a backup that answers more than it was asked
    primary = _Fake("primary", has=["IXIC"])

    class _Chatty(_Fake):
        def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
            return [_quote("IXIC", "chatty-backup"), _quote("^KS11", "chatty-backup")]

    # when
    result = FallbackQuoteProvider(primary, [_Chatty("b")]).get_quotes(["^KS11", "IXIC"])

    # then
    by_symbol = {q.symbol: q.close for q in result.quotes}
    assert by_symbol["IXIC"] == float(len("primary"))


def test_quote_for_a_symbol_nobody_asked_for_is_dropped() -> None:
    # given
    class _Extra(_Fake):
        def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
            return [_quote("IXIC", "x"), _quote("UNASKED", "x")]

    # when
    result = FallbackQuoteProvider(_Extra("primary"), []).get_quotes(["IXIC"])

    # then
    assert [q.symbol for q in result.quotes] == ["IXIC"]


def test_never_raises_whatever_the_providers_raise() -> None:
    # given: a domain error from one provider, an unexpected crash from the other
    primary = _Fake("primary", error=CollectError("primary", "blocked"))
    backup = _Fake("backup", error=RuntimeError("bug in the library"))

    # when
    result = FallbackQuoteProvider(primary, [backup]).get_quotes(["^KS11", "IXIC"])

    # then
    assert result == QuoteResult(quotes=(), missing=("^KS11", "IXIC"))


def test_no_symbols_means_no_calls() -> None:
    # given
    primary = _Fake("primary", has=["IXIC"])

    # when
    result = FallbackQuoteProvider(primary, []).get_quotes([])

    # then
    assert primary.calls == []
    assert result == QuoteResult(quotes=(), missing=())
