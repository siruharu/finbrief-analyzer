"""Who gets the briefing and how many times: claim, send, record."""

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from finbrief_analyzer.deliver.models import Briefing, DeliveryError, RenderedEmail
from finbrief_analyzer.deliver.ports import Notifier
from finbrief_analyzer.deliver.render import SLOT_LABELS, render_email
from finbrief_analyzer.store.delivery_log import DeliveryKey, DeliveryLog
from finbrief_analyzer.store.recipients import Recipient

logger = logging.getLogger(__name__)

UNSENDABLE = "briefing has an empty required section"


@dataclass(frozen=True, slots=True)
class DispatchResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    # The run stopped early: nothing to send, or the channel itself is unusable.
    aborted: bool = False
    abort_reason: str = ""


def mask_email(address: str) -> str:
    """First two characters and the domain. Full addresses do not go into logs."""
    local, at, domain = address.partition("@")
    return f"{local[:2]}***@{domain}" if at and domain else "***"


def dispatch(
    briefing: Briefing,
    recipients: Sequence[Recipient],
    notifier: Notifier,
    log: DeliveryLog,
    operator_email: str | None = None,
) -> DispatchResult:
    """Send the briefing to every recipient who has not received it yet."""
    if not briefing.is_sendable:
        _notify_operator(notifier, operator_email, briefing)
        return DispatchResult(aborted=True, abort_reason=UNSENDABLE)
    email = render_email(briefing)
    counts: Counter[str] = Counter()
    for recipient in recipients:
        key = DeliveryKey.for_email(briefing, recipient.id)
        if not log.claim(key):
            counts["skipped"] += 1
            continue
        error = _deliver_one(notifier, log, key, recipient, email)
        counts["sent" if error is None else "failed"] += 1
        if error is not None and error.fatal:
            # Everyone after this would fail the same way; leave them unclaimed for the next run.
            return _result(counts, abort_reason=str(error))
    return _result(counts)


def _result(counts: Counter[str], abort_reason: str = "") -> DispatchResult:
    return DispatchResult(
        sent=counts["sent"],
        skipped=counts["skipped"],
        failed=counts["failed"],
        aborted=bool(abort_reason),
        abort_reason=abort_reason,
    )


def _deliver_one(
    notifier: Notifier,
    log: DeliveryLog,
    key: DeliveryKey,
    recipient: Recipient,
    email: RenderedEmail,
) -> DeliveryError | None:
    """Send to one claimed recipient and record the outcome. Returns the error, if any."""
    masked = mask_email(recipient.email)
    error = _send_with_one_retry(notifier, recipient.email, email)
    try:
        if error is None:
            log.mark_sent(key)
        else:
            logger.warning("delivery to %s failed: %s", masked, error)
            log.mark_failed(key, str(error))
    except SQLAlchemyError:
        # The row stays pending, so the next run will not send to this recipient again.
        logger.exception("could not record the delivery result for %s", masked)
    return error


def _send_with_one_retry(
    notifier: Notifier, address: str, email: RenderedEmail
) -> DeliveryError | None:
    try:
        notifier.send(address, email)
    except DeliveryError as first:
        if not first.retryable:
            return first
        try:
            notifier.send(address, email)
        except DeliveryError as second:
            return second
    return None


def _notify_operator(notifier: Notifier, operator_email: str | None, briefing: Briefing) -> None:
    """Tell the operator nothing went out. A failing notice must not fail the job."""
    if operator_email is None:
        logger.error("%s; no operator address is configured", UNSENDABLE)
        return
    label = f"{SLOT_LABELS[briefing.slot]} 브리핑 {briefing.briefing_date.isoformat()}"
    text = f"{label} 을(를) 보내지 못했습니다. 필수 섹션(시세)이 비어 있습니다."
    notice = RenderedEmail(
        subject=f"[finbrief] 발송 불가: {label}", text=text + "\n", html=f"<p>{text}</p>"
    )
    try:
        notifier.send(operator_email, notice)
    except DeliveryError as error:
        logger.error("operator notice to %s failed: %s", mask_email(operator_email), error)
