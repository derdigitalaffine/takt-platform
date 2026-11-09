"""Regression tests for the KI menu shortcut and module settings UI."""
from pathlib import Path
from sqlalchemy import select

from app.db import SessionLocal, User
from app.security import hash_password
from conftest import login, settings


def _member(email: str, permissions: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email, name="KI Testperson", password_hash=hash_password("test-passwort-123"),
                permissions=permissions, active=True, is_admin=False, must_change_password=False,
            )
            db.add(user)
        else:
            user.permissions, user.active, user.is_admin = permissions, True, False
            user.must_change_password = False
        db.commit()


def _shortcut_before_groups(html: str) -> bool:
    # The dock launcher must be in the GLOBAL header (not hidden in the
    # sidebar, on the page, or as a floating button).
    header = html.split('<nav class="navbar app-navbar', 1)[-1].split('</nav>', 1)[0]
    return 'data-agent-dock' in header and 'data-agent-open' in header


def test_ki_chat_is_visible_as_primary_link_when_module_is_enabled():
    settings(module_ai="1")
    admin = login("admin@example.org", "admin-passwort-123")
    assert _shortcut_before_groups(admin.get("/").text)

    settings(module_ai="0")
    assert not _shortcut_before_groups(admin.get("/").text)


def test_ki_chat_shortcut_respects_user_permission():
    _member("hotfix-ai-allowed@example.org", "ai_chat")
    _member("hotfix-ai-denied@example.org", "")
    settings(module_ai="1")
    allowed = login("hotfix-ai-allowed@example.org", "test-passwort-123")
    denied = login("hotfix-ai-denied@example.org", "test-passwort-123")

    assert _shortcut_before_groups(allowed.get("/").text)
    assert not _shortcut_before_groups(denied.get("/").text)
    assert denied.get("/ki").status_code == 403
    assert allowed.get("/ki").status_code == 200


def test_agent_header_launcher_uses_compact_button_not_floating_overlay():
    settings(module_ai="1")
    html = login("admin@example.org", "admin-passwort-123").get("/").text
    assert 'class="agent-header-control"' in html
    assert 'class="btn btn-link agent-dock-launch"' in html
    assert 'aria-controls="agent-dock-panel"' in html
    assert 'aria-expanded="false"' in html
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "agent.css").read_text()
    assert ".agent-dock-launch{position:fixed" not in css
    assert ".app-navbar .agent-dock-launch{" in css



def test_module_cards_have_distinct_descriptions_and_stats_for_ki_tasks_calendars():
    admin = login("admin@example.org", "admin-passwort-123")
    response = admin.get("/admin/modules")
    assert response.status_code == 200
    content = response.text
    assert "Zentraler TAKT Agent mit ausgefüllten Fachvorschlägen" in content
    assert "Persönliche und gemeinsame Aufgaben" in content
    assert "Persönliche, freigegebene und organisationsbezogene Kalender" in content
    assert "TAKT Agent und internes Wissen" in content
    assert "Aufgaben und Aufgabenboards" in content
    assert "Kalender und Urlaubsplanung" in content
    assert content.count("Formularbaukasten (wie Nextcloud Forms)") == 1


def test_task_hover_keeps_layout_stable():
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.css").read_text()
    assert ".app-nav .nav-item:hover > .nav-link .badge { margin-right: 1.5rem; }" not in css
    assert "Reserve the pin's space permanently" in css
    assert "white-space: nowrap; min-height: 2.6rem" in css
