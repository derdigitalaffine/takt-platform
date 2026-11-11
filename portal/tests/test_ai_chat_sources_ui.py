"""Regression tests for the compact sources component in saved and streamed chat."""
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def test_saved_chat_sources_are_collapsed_by_default():
    html = (APP / "templates" / "ai_chat.html").read_text(encoding="utf-8")
    assert '<details class="ai-message-sources" data-ai-sources>' in html
    assert 'class="ai-sources-summary"' in html
    assert '{{ item.sources|length }}' in html
    assert 'class="ai-sources-list"' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert 'class="ai-message-sources" open' not in html


def test_streamed_chat_sources_are_safe_collapsed_and_deduplicated():
    js = (APP / "static" / "ai-chat.js").read_text(encoding="utf-8")
    assert "document.createElement('details')" in js
    assert "block.setAttribute('data-ai-sources', '')" in js
    assert "var seen = new Set()" in js
    assert "if (seen.has(href)) return" in js
    assert "count.textContent = String(list.children.length)" in js
    assert "new URL(source.url, window.location.origin)" in js
    assert "url.protocol !== 'https:'" in js
    assert "url.origin !== window.location.origin" in js
    assert "link.textContent = source.title" not in js
    assert "label.textContent = source.title" in js


def test_sources_tray_is_accessible_and_scoped():
    css = (APP / "static" / "ai-chat.css").read_text(encoding="utf-8")
    assert "[data-ai-workspace] .ai-sources-summary:focus-visible" in css
    assert "[data-ai-workspace] .ai-message-sources[open] .ai-sources-chevron" in css
    assert "[data-ai-workspace] .ai-sources-list" in css
