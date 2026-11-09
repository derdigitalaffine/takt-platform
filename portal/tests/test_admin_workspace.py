"""Admin workspace regression: large directories stay bounded and existing permissions hold."""
from sqlalchemy import delete, select

from app.db import SessionLocal, User
from conftest import login

ADMIN = ("admin@example.org", "admin-passwort-123")
PREFIX = "ux-scale-admin-"


def test_user_directory_server_pagination_search_and_status():
    ids = []
    try:
        with SessionLocal() as db:
            for i in range(57):
                row = User(
                    name=f"UX-Scale Person {i:03d}",
                    email=f"{PREFIX}{i:03d}@example.org",
                    password_hash="fixture-password-never-used",
                    password_set=(i % 3 != 0),
                    permissions="video",
                    active=(i % 5 != 0),
                    is_admin=False,
                )
                db.add(row)
                db.flush()
                ids.append(row.id)
            db.commit()
        c = login(*ADMIN)
        response = c.get("/admin/users?q=UX-Scale%20Person&per_page=25")
        assert response.status_code == 200, response.text[:300]
        html = response.text
        assert 'id="admin-user-query"' in html
        assert 'id="admin-user-status"' in html
        assert 'id="admin-user-group"' in html
        assert 'class="admin-user-row"' in html
        assert html.count('class="admin-user-row"') == 25
        assert f"{PREFIX}000@example.org" in html
        assert f"{PREFIX}050@example.org" not in html
        assert "57 passende Konten" in html
        assert "page=2" in html

        page2 = c.get("/admin/users?q=UX-Scale%20Person&per_page=25&page=2")
        assert page2.status_code == 200
        assert page2.text.count('class="admin-user-row"') == 25
        assert f"{PREFIX}025@example.org" in page2.text
        assert f"{PREFIX}000@example.org" not in page2.text

        blocked = c.get("/admin/users?q=UX-Scale%20Person&status=blocked")
        assert blocked.status_code == 200
        assert blocked.text.count('class="admin-user-row"') == 12

        invited = c.get("/admin/users?q=UX-Scale%20Person&status=invited")
        assert invited.status_code == 200
        assert invited.text.count('class="admin-user-row"') == 19

        empty = c.get("/admin/users?q=NoSuchUserZZZZ")
        assert empty.status_code == 200
        assert "Keine passenden Benutzer gefunden" in empty.text
        assert "0 passende Konten" in empty.text
    finally:
        with SessionLocal() as db:
            db.execute(delete(User).where(User.id.in_(ids)))
            db.commit()


def test_group_editor_is_lazy_and_rights_checked():
    c = login(*ADMIN)
    page = c.get("/admin/users")
    assert page.status_code == 200
    assert 'class="workspace-head"' in page.text
    assert 'id="admin-users-page-title"' in page.text
    assert '/static/workspace-heading.css' in page.text
    assert 'class="admin-welcome"' not in page.text
    assert 'data-admin-group-editor="0"' in page.text
    assert 'id="admin-group-editor-modal"' not in page.text
    editor = c.get("/admin/groups/editor/0")
    assert editor.status_code == 200
    assert 'id="admin-group-editor-modal"' in editor.text
    assert 'name="members"' in editor.text
    assert 'name="csrf"' in editor.text
    assert c.get("/admin/groups/editor/99999999").status_code == 404


def test_organization_workflows_have_visible_sections_and_search():
    c = login(*ADMIN)
    page = c.get("/admin/organization")
    assert page.status_code == 200
    assert 'id="admin-org-page-title"' in page.text
    assert 'class="workspace-head"' in page.text
    assert '/static/workspace-heading.css' in page.text
    assert 'admin-org-workspace' in page.text
    assert 'id="org-structure"' in page.text
    assert 'aria-label="Organisation verwalten"' in page.text
    assert 'data-org-member-search' in page.text
    assert 'data-org-member-list' in page.text or "Keine Organisationseinheit freigegeben." in page.text
    assert 'data-org-role-search' in page.text or 'id="org-roles"' in page.text


def test_admin_landing_uses_shell_title_and_keeps_navigation():
    c = login(*ADMIN)
    page = c.get("/admin")
    assert page.status_code == 200
    assert 'id="admin-page-title"' in page.text
    assert 'class="workspace-head"' in page.text
    assert 'class="admin-welcome"' not in page.text
    assert '/static/workspace-heading.css' in page.text
    assert 'class="admin-settings-grid"' in page.text
