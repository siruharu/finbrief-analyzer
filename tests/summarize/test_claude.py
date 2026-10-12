import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import anthropic
import httpx2
import pytest
from pydantic import SecretStr, ValidationError

from finbrief_analyzer.collect.models import NewsItem, Slot
from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.summarize.claude import (
    MAX_LINE_CHARS,
    ClaudeSummarizer,
    ParseCall,
    Pick,
    Picks,
    build_summarizer,
)

NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
SECRET = "sk-ant-very-secret-key"


def _news(n: int) -> NewsItem:
    return NewsItem(f"기사 {n}", f"https://example.com/{n}", "yna.co.kr", NOW)


@dataclass
class _Usage:
    input_tokens: int = 6000
    output_tokens: int = 400


@dataclass
class _Response:
    """The parts of a ParsedMessage the adapter reads."""

    parsed_output: Picks | None
    stop_reason: str = "end_turn"
    model: str = "claude-opus-5-5"
    usage: _Usage = field(default_factory=_Usage)


class FakeParse:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        # Any: the fake stands in for the SDK's ParsedMessage, which is not worth constructing.
        self.calls: list[dict[str, Any]] = []
        self._response = response
        self._error = error

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


def _summarizer(fake: FakeParse, **overrides: Any) -> ClaudeSummarizer:
    settings = Settings(anthropic_api_key=SecretStr(SECRET), **overrides)
    return ClaudeSummarizer(cast(ParseCall, fake), settings)


def _picks(*pairs: tuple[int, str]) -> Picks:
    return Picks(picks=[Pick(index=i, line=line) for i, line in pairs])


def _api_error(status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    message = f"status {status} body with {SECRET}"
    return anthropic.APIStatusError(message, response=response, body=None)


def test_valid_picks_become_digest_items_in_the_model_order_with_usage() -> None:
    # given
    news = (_news(1), _news(2), _news(3))
    fake = FakeParse(_Response(_picks((3, "셋째 기사 요약"), (1, "첫째 기사 요약"))))

    # when
    digest = _summarizer(fake).summarize(news, Slot.KR_OPEN)

    # then
    assert digest is not None
    assert [(item.news.title, item.line) for item in digest.items] == [
        ("기사 3", "셋째 기사 요약"),
        ("기사 1", "첫째 기사 요약"),
    ]
    assert digest.model == "claude-opus-5-5"
    assert (digest.input_tokens, digest.output_tokens) == (6000, 400)


def test_out_of_range_duplicate_blank_and_overlong_picks_are_dropped() -> None:
    # given
    news = (_news(1), _news(2))
    fake = FakeParse(
        _Response(
            _picks(
                (0, "범위 밖"),
                (3, "범위 밖"),
                (1, "첫째"),
                (1, "첫째 다시"),
                (2, "   "),
                (2, "가" * (MAX_LINE_CHARS + 1)),
            )
        )
    )

    # when
    digest = _summarizer(fake).summarize(news, Slot.KR_OPEN)

    # then
    assert digest is not None
    assert [(item.news.title, item.line) for item in digest.items] == [("기사 1", "첫째")]


def test_nothing_usable_is_none_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    # given
    fake = FakeParse(_Response(_picks((9, "범위 밖"))))

    # when
    with caplog.at_level(logging.WARNING):
        digest = _summarizer(fake).summarize((_news(1),), Slot.KR_OPEN)

    # then
    assert digest is None
    assert "no usable picks" in caplog.text


def test_more_picks_than_configured_keeps_the_first_ones() -> None:
    # given
    news = tuple(_news(n) for n in range(1, 6))
    fake = FakeParse(_Response(_picks(*((n, f"요약 {n}") for n in range(1, 6)))))

    # when
    digest = _summarizer(fake, summary_picks=2).summarize(news, Slot.KR_OPEN)

    # then
    assert digest is not None
    assert [item.news.title for item in digest.items] == ["기사 1", "기사 2"]


@pytest.mark.parametrize(
    "error",
    [
        _api_error(429),
        _api_error(529),
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")),
        anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com")),
    ],
    ids=["rate-limit", "overloaded", "connection", "timeout"],
)
def test_api_errors_give_none_and_one_warning_without_the_key(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    # given
    fake = FakeParse(error=error)

    # when
    with caplog.at_level(logging.WARNING):
        digest = _summarizer(fake).summarize((_news(1),), Slot.KR_OPEN)

    # then
    assert digest is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert type(error).__name__ in caplog.text
    assert SECRET not in caplog.text


def test_invalid_json_from_the_model_gives_none() -> None:
    # given: the SDK raises when the answer does not fit the schema
    try:
        Picks.model_validate({"picks": "not a list"})
    except ValidationError as invalid:
        fake = FakeParse(error=invalid)

    # when / then
    assert _summarizer(fake).summarize((_news(1),), Slot.KR_OPEN) is None


def test_refusal_gives_none(caplog: pytest.LogCaptureFixture) -> None:
    # given
    fake = FakeParse(_Response(parsed_output=None, stop_reason="refusal"))

    # when
    with caplog.at_level(logging.WARNING):
        digest = _summarizer(fake).summarize((_news(1),), Slot.KR_OPEN)

    # then
    assert digest is None
    assert "refusal" in caplog.text


def test_request_carries_the_configured_model_effort_tokens_and_numbered_input() -> None:
    # given
    fake = FakeParse(_Response(_picks((1, "요약"))))
    summarizer = _summarizer(fake, summary_model="claude-haiku-5-5", summary_effort="medium")

    # when
    summarizer.summarize((_news(1), _news(2)), Slot.US_OPEN)

    # then
    call = fake.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] == 2000
    assert call["output_config"] == {"effort": "medium"}
    assert call["output_format"] is Picks
    assert "최대 7건" in call["system"]
    assert call["messages"][0]["content"] == "[1] (yna.co.kr) 기사 1\n[2] (yna.co.kr) 기사 2"


def test_empty_news_is_none_without_a_request() -> None:
    # given
    fake = FakeParse(_Response(_picks()))

    # when / then
    assert _summarizer(fake).summarize((), Slot.KR_OPEN) is None
    assert fake.calls == []


def test_build_summarizer_is_none_without_a_key(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given: no key in the environment or a .env file
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_ANTHROPIC_API_KEY", raising=False)

    # when / then
    assert build_summarizer(Settings()) is None


def test_build_summarizer_returns_an_adapter_when_a_key_is_set() -> None:
    # given / when
    summarizer = build_summarizer(Settings(anthropic_api_key=SecretStr(SECRET)))

    # then
    assert isinstance(summarizer, ClaudeSummarizer)
