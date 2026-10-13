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
from pathlib import Path
from zoneinfo import ZoneInfo

from finbrief_analyzer.collect.factory import build_providers, make_client
from finbrief_analyzer.collect.models import MarketSnapshot, Slot
from finbrief_analyzer.collect.service import collect_snapshot
from finbrief_analyzer.compose.simple import compose_simple
from finbrief_analyzer.core.config import Settings, get_settings
from finbrief_analyzer.core.db import make_engine, session_scope
from finbrief_analyzer.deliver.dispatch import DispatchResult, dispatch
from finbrief_analyzer.deliver.models import Channel
from finbrief_analyzer.deliver.ports import Notifier
from finbrief_analyzer.deliver.smtp import SmtpNotifier
from finbrief_analyzer.screen.service import build_screen_service
from finbrief_analyzer.store.delivery_log import DeliveryLog
from finbrief_analyzer.store.recipients import Recipient, list_active
from finbrief_analyzer.summarize.claude import build_summarizer
from finbrief_analyzer.summarize.models import NewsDigest
from finbrief_analyzer.summarize.ports import Summarizer
from finbrief_analyzer.summarize.record import save_digest

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
    # None when no API key is configured: the news stays a plain list.
    summarize: Summarizer | None = None
    # Where the chosen lines are kept for review; None keeps nothing.
    digest_dir: Path | None = None


OpenJob = Callable[[Settings], AbstractContextManager[JobDeps]]


def briefing_date(slot: Slot, now: datetime) -> date:
    return now.astimezone(SLOT_ZONES[slot]).date()


def run(slot: Slot, now: datetime, deps: JobDeps) -> DispatchResult:
    day = briefing_date(slot, now)
    recipients = deps.recipients()
    if not deps.log.waiting(day, slot, Channel.EMAIL, [r.id for r in recipients]):
        # Everyone already has it (or another run is on it): no collection, no outside calls.
        result = DispatchResult(skipped=len(recipients))
    else:
        snapshot = deps.collect(slot, now)
        digest = _summarize(deps.summarize, snapshot, slot)
        if digest is not None and deps.digest_dir is not None:
            save_digest(deps.digest_dir, slot, day, digest)
        expected = deps.summarize is not None and bool(snapshot.news)
        briefing = compose_simple(snapshot, day, digest, summary_expected=expected)
        result = dispatch(briefing, recipients, deps.notifier, deps.log, deps.operator_email)
    logger.info(
        "briefing %s %s: sent=%d skipped=%d failed=%d aborted=%s %s",
        slot.value,
        day.isoformat(),
        result.sent,
        result.skipped,
        result.failed,
        result.aborted,
        result.abort_reason,
    )
    return result


def _summarize(
    summarizer: Summarizer | None, snapshot: MarketSnapshot, slot: Slot
) -> NewsDigest | None:
    """Ask for the digest when there is a summarizer and news. A failure warns, never aborts."""
    if summarizer is None or not snapshot.news:
        return None
    digest = summarizer.summarize(snapshot.news, slot)
    if digest is None:
        logger.warning("summary unavailable: listing the newest news instead")
        return None
    logger.info(
        "summary: picks=%d input_tokens=%d output_tokens=%d model=%s",
        len(digest.items),
        digest.input_tokens,
        digest.output_tokens,
        digest.model,
    )
    return digest


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
            summarize=build_summarizer(settings),
            digest_dir=settings.summary_log_dir,
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
