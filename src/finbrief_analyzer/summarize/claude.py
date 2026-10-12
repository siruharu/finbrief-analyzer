"""Claude adapter: one structured-output request that picks items by number and writes a line each.

Anything that goes wrong with the API ends in None and one warning; the briefing then falls
back to the plain list. Programming errors still raise.
"""

import logging
from collections.abc import Callable, Sequence

import anthropic
from anthropic.types import ParsedMessage
from pydantic import BaseModel, ValidationError

from finbrief_analyzer.collect.models import NewsItem, Slot
from finbrief_analyzer.core.config import Settings
from finbrief_analyzer.summarize.models import DigestItem, NewsDigest
from finbrief_analyzer.summarize.ports import Summarizer
from finbrief_analyzer.summarize.prepare import Candidate, candidates, render_input, resolve

logger = logging.getLogger(__name__)

# Lines longer than this are dropped, not cut: a cut sentence reads worse than one item fewer.
MAX_LINE_CHARS = 60

# Prompt as settled in docs/01_research/2026-10-12_news-summary-poc.md. {picks} is the item count.
SYSTEM_PROMPT = """당신은 한국의 개인 투자자를 위한 아침 금융 브리핑의 뉴스 편집자다.
입력은 지난 밤 수집된 기사 목록이다. 각 항목은 [번호] (출처) 제목 — 리드 형식이고, \
리드는 없을 수 있다.

할 일:
1. 브리핑 독자에게 영향이 큰 기사를 최대 {picks}건 고른다. 기준: 시장 전체(지수·금리·환율·원자재), \
정책·규제, 대형 기업 실적과 공시, 거시 지표. 국내와 미국을 함께 다룬다. \
연예·사건사고·광고성 기사는 제외한다.
2. 같은 사건을 다룬 기사가 여러 개면 하나만 고른다.
3. 고른 기사마다 한국어 한 문장({max_chars}자 이내)으로 핵심을 쓴다. 영문 기사도 한국어로 쓴다.

규칙:
- 입력에 없는 사실·수치·해석을 쓰지 않는다. 리드가 없는 항목은 제목이 말하는 것만 쓴다.
- 원문 문장을 그대로 옮기거나 단순히 줄이지 말고, 새 문장으로 쓴다.
- 번호(index)는 입력의 번호를 그대로 쓴다. 제목이나 URL 을 다시 쓰지 않는다.
- 고를 만한 기사가 없으면 빈 목록을 돌려준다."""


class Pick(BaseModel):
    index: int
    line: str


class Picks(BaseModel):
    picks: list[Pick]


# `client.messages.parse` or a stand-in with the same keyword interface.
ParseCall = Callable[..., ParsedMessage[Picks]]


class ClaudeSummarizer:
    def __init__(self, parse: ParseCall, settings: Settings) -> None:
        self._parse = parse
        self._settings = settings

    def summarize(self, news: Sequence[NewsItem], slot: Slot) -> NewsDigest | None:
        found = candidates(news)
        if not found:
            return None
        try:
            response = self._request(render_input(found))
        except (anthropic.APIError, ValidationError) as error:
            # str(error) can carry the request body; the class name is enough to act on.
            logger.warning("news summary skipped: %s", type(error).__name__)
            return None
        if response.stop_reason == "refusal" or response.parsed_output is None:
            logger.warning("news summary skipped: stop_reason=%s", response.stop_reason)
            return None
        return _digest(response, found, self._settings.summary_picks)

    def _request(self, text: str) -> ParsedMessage[Picks]:
        settings = self._settings
        system = SYSTEM_PROMPT.format(picks=settings.summary_picks, max_chars=MAX_LINE_CHARS)
        return self._parse(
            model=settings.summary_model,
            max_tokens=settings.summary_max_tokens,
            system=system,
            output_config={"effort": settings.summary_effort},
            messages=[{"role": "user", "content": text}],
            output_format=Picks,
        )


def _digest(
    response: ParsedMessage[Picks], found: Sequence[Candidate], limit: int
) -> NewsDigest | None:
    """Keep the picks that point at real items, once each, with a usable line."""
    assert response.parsed_output is not None  # checked by the caller
    items: list[DigestItem] = []
    seen: set[int] = set()
    for pick in response.parsed_output.picks:
        news = resolve(found, pick.index)
        line = pick.line.strip()
        if news is None or pick.index in seen or not line or len(line) > MAX_LINE_CHARS:
            continue
        seen.add(pick.index)
        items.append(DigestItem(news, line))
    if not items:
        logger.warning("news summary skipped: no usable picks")
        return None
    return NewsDigest(
        tuple(items[:limit]),
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )


def build_summarizer(settings: Settings) -> Summarizer | None:
    """The summarising step for the briefing job, or None when no key is configured."""
    if settings.anthropic_api_key is None:
        return None
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.summary_timeout_seconds,
        max_retries=2,
    )
    return ClaudeSummarizer(client.messages.parse, settings)
