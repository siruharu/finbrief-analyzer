"""Keep what the mail carried, so the summaries can be looked at again later.

The mail itself is gone once sent and the log only has the counts. One small JSON per
briefing in the local logs directory is enough to review quality over a few weeks.
"""

import json
import logging
from datetime import date
from pathlib import Path

from finbrief_analyzer.collect.models import Slot
from finbrief_analyzer.summarize.models import NewsDigest

logger = logging.getLogger(__name__)


def save_digest(directory: Path, slot: Slot, day: date, digest: NewsDigest) -> Path | None:
    """Write <day>_<slot>.json under `directory`. Returns the path, or None when it could not."""
    target = directory / f"{day.isoformat()}_{slot.value}.json"
    record = {
        "brief_date": day.isoformat(),
        "slot": slot.value,
        "model": digest.model,
        "input_tokens": digest.input_tokens,
        "output_tokens": digest.output_tokens,
        "items": [
            {
                "line": item.line,
                "title": item.news.title,
                "url": item.news.link,
                "source": item.news.source,
            }
            for item in digest.items
        ],
    }
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as error:
        # A review aid must never cost the briefing.
        logger.warning("digest not saved to %s: %s", target, type(error).__name__)
        return None
    return target
