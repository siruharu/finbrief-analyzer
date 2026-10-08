"""One-off job: collect, compose and send the briefing for one slot.

    python -m finbrief_analyzer.jobs.run_briefing --slot kr_open

Exit code 0 when the run finished (some recipients may have failed), 1 when it was aborted.
"""

import argparse
import logging
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from finbrief_analyzer.collect.factory import build_providers, make_client
from finbrief_analyzer.collect.models import MarketSnapshot, Slot
from finbrief_analyzer.collect.service import collect_snapshot
from finbrief_analyzer.compose.simple import compose_simple
from finbrief_analyzer.core.config import Settings, get_settings
from finbrief_analyzer.core.db import make_engine, session_scope
from finbrief_analyzer.deliver.dispatch import DispatchResult, dispatch
from finbrief_analyzer.deliver.ports import Notifier
from finbrief_analyzer.deliver.smtp import SmtpNotifier
from finbrief_analyzer.screen.service import build_screen_service
from finbrief_analyzer.store.delivery_log import DeliveryLog
from finbrief_analyzer.store.recipients import Recipient, list_active

logger = logging.getLogger(__name__)

# The briefing is dated in the time zone of the market that is about to open.
SLOT_ZONES = {Slot.KR_OPEN: ZoneInfo("Asia/Seoul"), Slot.US_OPEN: ZoneInfo("America/New_York")}


@dataclass(frozen=True, slots=True)
class JobDeps:
    """Everything the job touches outside its own process."""

    collect: Callable[[Slot, datetime], MarketSnapshot]
    recipients: Callable[[], Sequence[Recipient]]
    notifier: Notifier
    log: DeliveryLog
    operator_email: str | None = None


OpenJob = Callable[[Settings], AbstractContextManager[JobDeps]]


def briefing_date(slot: Slot, now: datetime) -> date:
    return now.astimezone(SLOT_ZONES[slot]).date()


def run(slot: Slot, now: datetime, deps: JobDeps) -> DispatchResult:
    snapshot = deps.collect(slot, now)
    briefing = compose_simple(snapshot, briefing_date(slot, now))
    result = dispatch(briefing, deps.recipients(), deps.notifier, deps.log, deps.operator_email)
    logger.info(
        "briefing %s %s: sent=%d skipped=%d failed=%d aborted=%s %s",
        slot.value,
        briefing.briefing_date.isoformat(),
        result.sent,
        result.skipped,
        result.failed,
        result.aborted,
        result.abort_reason,
    )
    return result


@contextmanager
def open_deps(settings: Settings) -> Iterator[JobDeps]:
    """Wire the real dependencies and release them afterwards."""
    # Both fail here when unconfigured, before any time is spent collecting.
    notifier = SmtpNotifier(settings)
    engine = make_engine(settings)
    client = make_client(settings)
    # None unless APP_SCREEN_ENABLED is set; then it joins the collection as one more source.
    providers = replace(
        build_providers(settings, client),
        screens=build_screen_service(settings, engine, client),
    )

    def recipients() -> list[Recipient]:
        with session_scope(engine) as session:
            return list_active(session)

    try:
        yield JobDeps(
            collect=lambda slot, now: collect_snapshot(
                slot, now, providers, settings.all_symbols()
            ),
            recipients=recipients,
            notifier=notifier,
            log=DeliveryLog(engine),
            operator_email=settings.operator_email,
        )
    finally:
        notifier.close()
        client.close()
        engine.dispose()


def _parse_args(argv: Sequence[str] | None) -> Slot:
    parser = argparse.ArgumentParser(description="Send the briefing for one slot.")
    parser.add_argument("--slot", required=True, choices=[slot.value for slot in Slot])
    return Slot(parser.parse_args(argv).slot)


def _exit_code(result: DispatchResult) -> int:
    return 1 if result.aborted else 0


def main(
    argv: Sequence[str] | None = None,
    open_job: OpenJob = open_deps,
    now: datetime | None = None,
) -> int:
    slot = _parse_args(argv)
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    try:
        with open_job(settings) as deps:
            return _exit_code(run(slot, now or datetime.now(UTC), deps))
    except Exception:
        # The stack goes to the log; whoever scheduled the job sees the exit code.
        logger.exception("briefing job crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
