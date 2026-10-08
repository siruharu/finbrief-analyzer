"""One-off job: build the screening universe and load its daily price history.

    python -m finbrief_analyzer.jobs.backfill_prices

Safe to run again: stocks that already have history are only brought up to date. The
briefing job does the same update with a time limit; this one has none.
"""

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime

from finbrief_analyzer.collect.factory import make_client
from finbrief_analyzer.core.config import Settings, get_settings
from finbrief_analyzer.core.db import make_engine, session_scope
from finbrief_analyzer.screen.history import UpdateReport, update_history
from finbrief_analyzer.screen.service import ScreenDeps, build_screen_deps
from finbrief_analyzer.screen.universe import refresh_universe

logger = logging.getLogger(__name__)


OpenJob = Callable[[Settings], AbstractContextManager[ScreenDeps]]


@contextmanager
def open_deps(settings: Settings) -> Iterator[ScreenDeps]:
    """Wire the real sources and release them afterwards. Fails here without a database."""
    engine = make_engine(settings)
    client = make_client(settings)
    try:
        yield build_screen_deps(settings, engine, client)
    finally:
        client.close()
        engine.dispose()


def run(deps: ScreenDeps, settings: Settings, now: datetime) -> UpdateReport:
    with session_scope(deps.engine) as session:
        rebuilt = refresh_universe(session, now.date(), deps.universe, settings.universe_sizes())
    logger.info("universe rebuilt: %s", ", ".join(e.value for e in rebuilt) or "none")
    report = update_history(deps.engine, deps.sources, now, settings.screen_history_days)
    logger.info(
        "price history: added=%d loaded=%d reloaded=%d failed=%d %s",
        report.added,
        report.loaded,
        report.reloaded,
        len(report.failed),
        " ".join(report.failed[:20]),
    )
    return report


def main(
    open_job: OpenJob = open_deps,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    try:
        with open_job(settings) as deps:
            run(deps, settings, now or datetime.now(UTC))
    except Exception:
        # The stack goes to the log; whoever started the job sees the exit code.
        logger.exception("price backfill crashed")
        return 1
    # Stocks a source could not answer are retried on the next run; that is not a failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
