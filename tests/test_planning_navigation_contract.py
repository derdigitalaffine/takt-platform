"""Structural regression checks for calendar planning navigation.

Browser coverage is still required before release; these checks guard the
progressive-enhancement contract and prevent accidental hard navigation.
"""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "portal" / "app" / "static"
TEMPLATES = Path(__file__).resolve().parents[1] / "portal" / "app" / "templates"


def test_calendar_mode_switch_is_progressive_and_client_side():
    js = (STATIC / "calendars.js").read_text(encoding="utf-8")
    template = (TEMPLATES / "calendars.html").read_text(encoding="utf-8")

    assert 'data-calendar-mode-link' in template
    assert 'href="/kalender/jahr' in template
    assert 'href="/kalender?ansicht=termine' in template
    assert "event.preventDefault()" in js
    assert "calendar.changeView(view)" in js
    assert "history.pushState(" in js
    assert 'window.addEventListener("popstate"' in js
    assert "calendar.gotoDate(date)" in js
    assert 'link.removeAttribute("aria-current")' in js


def test_planning_style_remains_scoped():
    css = (STATIC / "planning-polish.css").read_text(encoding="utf-8")
    assert ".planning-workspace .planning-context" in css
    assert ".planning-workspace .calendar-mode-choice" in css
    assert "[data-density=\"compact\"] .planning-workspace" in css
