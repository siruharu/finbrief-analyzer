import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from finbrief_analyzer.collect.models import NewsItem, Slot
from finbrief_analyzer.summarize.models import DigestItem, NewsDigest
from finbrief_analyzer.summarize.record import save_digest

NOW = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)
DAY = date(2026, 10, 13)
DIGEST = NewsDigest(
    (
        DigestItem(NewsItem("기사 1", "https://example.com/1", "yna.co.kr", NOW), "첫 줄"),
        DigestItem(NewsItem("기사 2", "https://example.com/2", "mk.co.kr", NOW), "둘째 줄"),
    ),
    "claude-opus-5-5",
    input_tokens=7000,
    output_tokens=400,
)


def test_digest_is_saved_as_json_named_by_day_and_slot(tmp_path: Path) -> None:
    # given
    directory = tmp_path / "digests"

    # when
    saved = save_digest(directory, Slot.KR_OPEN, DAY, DIGEST)

    # then: the file carries what the mail carried, plus what it cost
    assert saved == directory / "2026-10-13_kr_open.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["slot"] == "kr_open"
    assert data["brief_date"] == "2026-10-13"
    assert data["model"] == "claude-opus-5-5"
    assert (data["input_tokens"], data["output_tokens"]) == (7000, 400)
    assert data["items"] == [
        {"line": "첫 줄", "title": "기사 1", "url": "https://example.com/1", "source": "yna.co.kr"},
        {
            "line": "둘째 줄",
            "title": "기사 2",
            "url": "https://example.com/2",
            "source": "mk.co.kr",
        },
    ]


def test_saving_again_overwrites_the_same_day_and_slot(tmp_path: Path) -> None:
    # given
    first = save_digest(tmp_path, Slot.KR_OPEN, DAY, DIGEST)
    assert first is not None

    # when
    second = save_digest(tmp_path, Slot.KR_OPEN, DAY, NewsDigest((), "m"))

    # then
    assert second == first
    assert json.loads(first.read_text(encoding="utf-8"))["items"] == []


def test_unwritable_directory_is_a_warning_not_an_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # given: the "directory" is an existing file
    blocker = tmp_path / "digests"
    blocker.write_text("not a directory", encoding="utf-8")

    # when
    with caplog.at_level(logging.WARNING):
        saved = save_digest(blocker, Slot.US_OPEN, DAY, DIGEST)

    # then
    assert saved is None
    assert "digest not saved" in caplog.text
