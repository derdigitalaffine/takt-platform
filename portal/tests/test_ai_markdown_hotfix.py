"""Hotfix regressions: safe Markdown and scrollable user-edit forms."""
from pathlib import Path

from app.routes_ai import _ai_markdown
from conftest import login

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


def test_ai_markdown_renders_structured_content_and_escapes_raw_html():
    html = _ai_markdown("# Überschrift\n\n**fett** und `code`\n\n- Eintrag\n\n| A | B |\n|---|---|\n| 1 | 2 |")
    assert "<h1>Überschrift</h1>" in html
    assert "<strong>fett</strong>" in html
    assert "<code>code</code>" in html
    assert "<li>Eintrag</li>" in html
    assert "<table>" in html
    malicious = _ai_markdown('<script>alert("x")</script>\n\n[bad](javascript:alert(1))\n\n![remote](https://example.org/img.png)')
    assert "<script" not in malicious
    assert "<img" not in malicious
    assert 'href="javascript:' not in malicious


def test_edit_user_modal_has_bootstrap_scrollable_body_and_footer():
    html = login("admin@example.org", "admin-passwort-123").get("/admin/users").text
    assert 'modal-dialog modal-xl modal-dialog-scrollable' in html
    assert '<form class="modal-content" method="post" action="/admin/users/' in html
    assert '<div class="modal-body"><div class="row g-3">' in html
    assert 'class="modal-footer"' in html
    assert 'data-permission-group open' not in html
    template = (TEMPLATES / "_macros.html").read_text(encoding="utf-8")
    assert '<details class="perm-editor-group" data-permission-group>' in template
