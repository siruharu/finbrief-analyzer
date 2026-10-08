"""Which stocks get screened: the largest common stocks per exchange, rebuilt once a month."""

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from typing import Protocol

from sqlalchemy.orm import Session

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.screen.models import Exchange, Member
from finbrief_analyzer.screen.ranking import NaverRanking, RankRow
from finbrief_analyzer.store.universe import built_on, replace_members

logger = logging.getLogger(__name__)

# KOSPI's ranking mixes in ETFs: 200 common stocks needed 278 rows in the PoC.
EXTRA_PAGES = 2
# The only two share-class tickers in the index, as the listing spells them (2026-10-08).
SHARE_CLASS_TICKERS = {"BRKB": "BRK-B", "BFB": "BF-B"}
# (symbol, name) pairs of the S&P 500.
Sp500Fetch = Callable[[], Sequence[tuple[str, str]]]


class UniverseSource(Protocol):
    def members(self, exchange: Exchange, size: int) -> list[Member]:
        """Up to `size` members, largest first. Raises CollectError on failure."""
        ...


def is_common_stock(row: RankRow) -> bool:
    """Leave out ETFs, ETNs, preferred shares, SPACs and REITs.

    Preferred shares are told by their code, not their name: "성우" is a common stock.
    A REIT's name ends with the word; "메리츠금융지주" merely contains it.
    """
    return (
        row.kind == "stock"
        and row.code.endswith("0")
        and "스팩" not in row.name
        and not row.name.endswith("리츠")
    )


def pick(exchange: Exchange, rows: Iterable[RankRow], size: int) -> list[Member]:
    """The first `size` common stocks of rows already sorted by market value."""
    common = [Member(exchange, row.code, row.name) for row in rows if is_common_stock(row)]
    return common[:size]


def members_from_sp500(listing: Iterable[tuple[str, str]]) -> list[Member]:
    return [Member(Exchange.SP500, _yahoo_ticker(symbol), name) for symbol, name in listing]


def _yahoo_ticker(symbol: str) -> str:
    # Share classes: Wikipedia writes BRK.B, the FinanceDataReader listing strips the
    # dot to BRKB, and Yahoo wants BRK-B.
    return SHARE_CLASS_TICKERS.get(symbol, symbol.replace(".", "-"))


def pages_for(size: int) -> int:
    """How many ranking pages of 100 it takes to find `size` common stocks."""
    return -(-size // 100) + EXTRA_PAGES


class NaverUniverseSource:
    def __init__(self, ranking: NaverRanking) -> None:
        self._ranking = ranking

    def members(self, exchange: Exchange, size: int) -> list[Member]:
        return pick(exchange, self._ranking.fetch(exchange, pages_for(size)), size)


def _fdr_sp500() -> Sequence[tuple[str, str]]:  # pragma: no cover - network
    # Imported here so that importing this module does not load pandas.
    import FinanceDataReader as fdr

    frame = fdr.StockListing("S&P500")
    return [
        (str(symbol), str(name))
        for symbol, name in zip(frame["Symbol"], frame["Name"], strict=True)
    ]


class Sp500UniverseSource:
    def __init__(self, fetch: Sp500Fetch = _fdr_sp500) -> None:
        self._fetch = fetch

    def members(self, exchange: Exchange, size: int) -> list[Member]:
        # The whole index, not a cut: the listing is alphabetical, so slicing it would
        # drop stocks by name. `size` only serves as the minimum a full answer must reach.
        return members_from_sp500(self._fetch())


def refresh_universe(
    session: Session,
    today: date,
    sources: Mapping[Exchange, UniverseSource],
    sizes: Mapping[Exchange, int],
) -> list[Exchange]:
    """Rebuild each exchange's composition once a month. Returns the ones rebuilt.

    A failing or short answer keeps the stored composition; nothing raises from here.
    """
    rebuilt: list[Exchange] = []
    for exchange, source in sources.items():
        built = built_on(session, exchange)
        if built is not None and (built.year, built.month) == (today.year, today.month):
            continue
        found = _attempt(exchange, source, sizes[exchange])
        if len(found) < sizes[exchange]:
            # Fewer than asked for means a partial answer, not a smaller market.
            logger.warning("universe kept as is: %s gave %d stocks", exchange.value, len(found))
            continue
        replace_members(session, exchange, found, today)
        rebuilt.append(exchange)
    return rebuilt


def _attempt(exchange: Exchange, source: UniverseSource, size: int) -> list[Member]:
    try:
        return source.members(exchange, size)
    except CollectError as error:
        logger.warning("universe source failed: %s", error)
    except Exception:
        # A crash in a third-party library must not take the briefing down with it.
        logger.exception("universe source crashed: %s", exchange.value)
    return []
