from datetime import date

from finbrief_analyzer.collect.models import Slot
from finbrief_analyzer.deliver.models import Briefing, LinkItem, Section
from finbrief_analyzer.deliver.render import render_email

QUOTES = Section(title="시세", lines=("KOSPI 6,803.90 (-1.98%)",), required=True)


def _news(*links: LinkItem) -> Section:
    return Section(title="뉴스", links=links)


def _briefing(*sections: Section, notices: tuple[str, ...] = ()) -> Briefing:
    return Briefing(
        slot=Slot.KR_OPEN,
        briefing_date=date(2026, 10, 8),
        sections=sections,
        notices=notices,
    )


def test_briefing_is_not_sendable_when_a_required_section_is_empty() -> None:
    # given: the required quote section has nothing in it, news does
    empty_quotes = Section(title="시세", required=True)
    news = _news(LinkItem(title="기사", url="https://example.com/a"))

    # when
    briefing = _briefing(empty_quotes, news)

    # then
    assert briefing.is_sendable is False


def test_briefing_is_not_sendable_without_any_required_section() -> None:
    # given: only an optional section
    briefing = _briefing(_news(LinkItem(title="기사", url="https://example.com/a")))

    # when / then
    assert briefing.is_sendable is False


def test_briefing_with_quotes_but_no_news_is_sendable() -> None:
    # given: news collection returned nothing
    briefing = _briefing(QUOTES, _news())

    # when / then
    assert briefing.is_sendable is True


def test_subject_contains_the_slot_name_and_the_briefing_date() -> None:
    # given
    briefing = _briefing(QUOTES)

    # when
    email = render_email(briefing)

    # then
    assert "국내 개장" in email.subject
    assert "2026-10-08" in email.subject


def test_subject_names_the_us_slot_differently() -> None:
    # given
    briefing = Briefing(slot=Slot.US_OPEN, briefing_date=date(2026, 10, 8), sections=(QUOTES,))

    # when
    email = render_email(briefing)

    # then
    assert "미국 개장" in email.subject


def test_every_news_item_carries_its_link_in_both_bodies() -> None:
    # given
    links = (
        LinkItem(title="첫 기사", url="https://example.com/a", source="연합뉴스"),
        LinkItem(title="둘째 기사", url="https://example.com/b"),
    )

    # when
    email = render_email(_briefing(QUOTES, _news(*links)))

    # then
    for item in links:
        assert item.url is not None
        assert item.url in email.text
        assert f'href="{item.url}"' in email.html


def test_html_body_escapes_markup_in_external_titles() -> None:
    # given: a title that came from a feed
    hostile = LinkItem(title='<script>alert("x")</script> A&B', url="https://example.com/a")

    # when
    email = render_email(_briefing(QUOTES, _news(hostile)))

    # then
    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html
    assert "A&amp;B" in email.html


def test_html_body_escapes_quotes_inside_the_link_attribute() -> None:
    # given: a url that tries to close the href attribute
    hostile = LinkItem(title="기사", url='https://example.com/a"onmouseover="x')

    # when
    email = render_email(_briefing(QUOTES, _news(hostile)))

    # then
    assert '"onmouseover="' not in email.html


def test_item_without_an_http_link_is_listed_by_title_only() -> None:
    # given: a javascript url and a missing url
    links = (
        LinkItem(title="수상한 기사", url="javascript:alert(1)"),
        LinkItem(title="링크 없는 기사"),
    )

    # when
    email = render_email(_briefing(QUOTES, _news(*links)))

    # then
    assert "javascript:" not in email.text
    assert "javascript:" not in email.html
    assert "<a " not in email.html
    assert "수상한 기사" in email.text
    assert "링크 없는 기사" in email.html


def test_text_and_html_bodies_list_the_same_number_of_items() -> None:
    # given: three items, one of them without a usable link
    links = (
        LinkItem(title="하나", url="https://example.com/1"),
        LinkItem(title="둘", url="https://example.com/2"),
        LinkItem(title="셋"),
    )

    # when
    email = render_email(_briefing(QUOTES, _news(*links)))

    # then
    text_items = [line for line in email.text.splitlines() if line.startswith("- ")]
    assert len(text_items) == 3
    assert email.html.count("<li>") == 3


def test_section_lines_appear_in_both_bodies() -> None:
    # given
    briefing = _briefing(QUOTES)

    # when
    email = render_email(briefing)

    # then
    assert "KOSPI 6,803.90 (-1.98%)" in email.text
    assert "KOSPI 6,803.90 (-1.98%)" in email.html


def test_notices_are_shown_above_the_first_section() -> None:
    # given: a closed-market notice
    notice = "미국 시장은 휴장이었습니다. 직전 거래일 값입니다."

    # when
    email = render_email(_briefing(QUOTES, notices=(notice,)))

    # then
    assert notice in email.text
    assert email.text.index(notice) < email.text.index("시세")
    assert email.html.index(notice) < email.html.index("시세")


def test_empty_optional_section_is_left_out() -> None:
    # given: news came back empty
    briefing = _briefing(QUOTES, _news())

    # when
    email = render_email(briefing)

    # then
    assert "뉴스" not in email.text
    assert "뉴스" not in email.html
