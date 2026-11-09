"""Rights UI regression: same POST contract, improved grouped presentation."""
from conftest import login, settings


def test_user_editor_contains_search_and_grouped_permissions():
    settings(module_ai="1", module_tasks="1", module_calendars="1")
    c = login("admin@example.org", "admin-passwort-123")
    page = c.get("/admin/users")
    assert page.status_code == 200
    html = page.text
    assert 'data-permission-editor' in html
    assert 'data-permission-search' in html
    assert 'data-permission-action="select-group"' in html
    assert "KI &amp; Assistenz" in html or "KI & Assistenz" in html
    assert "Kalender, Termine &amp; Ressourcen" in html or "Kalender, Termine & Ressourcen" in html
    assert 'name="perm" value="ai_chat"' in html
    assert 'name="perm" value="tasks"' in html
    assert "/static/permission-editor.css" in html
    assert "/static/permission-editor.js" in html


def test_permission_editor_preserves_unmodified_backend_contract():
    c = login("admin@example.org", "admin-passwort-123")
    page = c.get("/admin/users")
    html = page.text
    assert 'name="action" value="edit"' in html
    assert 'name="is_admin" value="1"' in html
    assert 'name="groups"' in html
    assert 'name="perm" value="video"' in html
    # Selection buttons have type=button, so they cannot submit an incomplete form.
    assert 'type="button" class="btn btn-sm btn-link" data-permission-action="clear-group"' in html
