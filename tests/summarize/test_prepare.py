from datetime import UTC, datetime

from finbrief_analyzer.collect.models import NewsItem
from finbrief_analyzer.summarize.prepare import candidates, render_input, resolve, strip_byline

NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)


def _news(n: int, summary: str | None = None, source: str = "yna.co.kr") -> NewsItem:
    return NewsItem(f"기사 {n}", f"https://example.com/{n}", source, NOW, summary=summary)


def test_yonhap_byline_is_removed_and_the_lead_kept() -> None:
    # given / when / then
    assert strip_byline("(서울=연합뉴스) 홍길동 기자 = 코스피가 급락했다.") == "코스피가 급락했다."
    assert strip_byline("(세종=연합뉴스) 홍길동 김철수 기자 = 물가가 올랐다.") == "물가가 올랐다."
    assert strip_byline("(서울=연합뉴스) = 환율이 내렸다.") == "환율이 내렸다."


def test_lead_without_a_byline_is_unchanged() -> None:
    # given / when / then
    assert strip_byline("코스피가 급락했다 = 외국인 매도") == "코스피가 급락했다 = 외국인 매도"


def test_candidates_are_numbered_from_one_and_resolve_back_to_the_item() -> None:
    # given
    items = (_news(1), _news(2), _news(3))

    # when
    found = candidates(items)

    # then
    assert [c.index for c in found] == [1, 2, 3]
    assert resolve(found, 2) is items[1]


def test_index_outside_the_candidates_resolves_to_nothing() -> None:
    # given
    found = candidates((_news(1),))

    # when / then
    assert resolve(found, 0) is None
    assert resolve(found, 2) is None


def test_input_line_has_number_source_title_and_cleaned_lead_but_no_url() -> None:
    # given
    item = _news(1, summary="(서울=연합뉴스) 홍길동 기자 = 코스피가 급락했다.")

    # when
    text = render_input(candidates((item,)))

    # then
    assert text == "[1] (yna.co.kr) 기사 1 — 코스피가 급락했다."
    assert "https://" not in text


def test_item_without_a_lead_is_rendered_as_its_title_only() -> None:
    # given
    item = _news(7, source="hankyung.com")

    # when
    text = render_input(candidates((item,)))

    # then
    assert text == "[1] (hankyung.com) 기사 7"


def test_empty_news_gives_no_candidates_and_an_empty_input() -> None:
    # given / when / then
    assert candidates(()) == ()
    assert render_input(()) == ""
