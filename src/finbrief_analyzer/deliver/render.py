"""Turn a Briefing into an email: subject, plain-text body and HTML body."""

from html import escape

from finbrief_analyzer.collect.models import Slot
from finbrief_analyzer.deliver.models import Briefing, LinkItem, RenderedEmail, Section

SLOT_LABELS = {Slot.KR_OPEN: "국내 개장", Slot.US_OPEN: "미국 개장"}


def render_email(briefing: Briefing) -> RenderedEmail:
    return RenderedEmail(
        subject=_subject(briefing),
        text=_text_body(briefing),
        html=_html_body(briefing),
    )


def _subject(briefing: Briefing) -> str:
    return f"[finbrief] {SLOT_LABELS[briefing.slot]} 브리핑 {briefing.briefing_date.isoformat()}"


def _visible_sections(briefing: Briefing) -> list[Section]:
    return [section for section in briefing.sections if not section.is_empty]


def _label(item: LinkItem) -> str:
    return f"{item.title} ({item.source})" if item.source else item.title


def _text_body(briefing: Briefing) -> str:
    blocks = ["\n".join(f"※ {notice}" for notice in briefing.notices)]
    blocks += [_text_section(section) for section in _visible_sections(briefing)]
    blocks.append("\n".join(f"※ {note}" for note in briefing.footnotes))
    return "\n\n".join(block for block in blocks if block) + "\n"


def _text_section(section: Section) -> str:
    rows = [f"■ {section.title}", *section.lines]
    for item in section.links:
        rows.append(f"- {_label(item)}")
        if item.safe_url is not None:
            rows.append(f"  {item.safe_url}")
    return "\n".join(rows)


def _html_body(briefing: Briefing) -> str:
    notices = "".join(f"<p><strong>※ {escape(notice)}</strong></p>" for notice in briefing.notices)
    sections = "".join(_html_section(section) for section in _visible_sections(briefing))
    notes = "".join(
        f'<p style="color:#666;font-size:0.9em">※ {escape(note)}</p>' for note in briefing.footnotes
    )
    return f'<html><body style="font-family:sans-serif">{notices}{sections}{notes}</body></html>'


def _html_section(section: Section) -> str:
    parts = [f"<h3>{escape(section.title)}</h3>"]
    if section.lines:
        parts.append("<p>" + "<br>".join(escape(line) for line in section.lines) + "</p>")
    if section.links:
        parts.append("<ul>" + "".join(_html_item(item) for item in section.links) + "</ul>")
    return "".join(parts)


def _html_item(item: LinkItem) -> str:
    title = escape(item.title)
    if item.safe_url is not None:
        title = f'<a href="{escape(item.safe_url, quote=True)}">{title}</a>'
    source = f" ({escape(item.source)})" if item.source else ""
    return f"<li>{title}{source}</li>"
