"""Module hub: server-side permission boundaries, filters and personal shortcuts."""

import json
from urllib.parse import parse_qs, urlsplit

from app import nav
from app.db import SessionLocal, User
from app.main import templates
from app.security import hash_password
from conftest import csrf_of, login, settings


ADMIN = ("admin@example.org", "admin-passwort-123")


def test_hub_template_compiles_and_uses_accessible_sections():
    assert templates.env.get_template("module_catalog.html") is not None
    settings(module_tasks="1", module_forms="1")
    page = login(*ADMIN).get("/module")
    assert page.status_code == 200
    html = page.text
    assert 'class="module-hub"' in html
    assert 'id="module-discovery"' in html
    assert 'aria-label="Nach Fachbereichen filtern"' in html
    assert 'role="search"' in html
    assert 'id="module-results"' in html
    assert "Ihre Module" in html
    assert 'id="module-kanban"' in html
    assert 'name="sort"' in html


def test_hub_search_category_and_sort_return_only_authorized_families():
    settings(module_tasks="1", module_laws="1")
    client = login(*ADMIN)
    page = client.get("/module?q=DMS")
    assert page.status_code == 200
    assert "Dokumentenablage" in page.text
    assert "Keine passenden Module" not in page.text
    page = client.get("/module?category=work&sort=az")
    assert page.status_code == 200
    card_section = page.text.split('id="module-results"', 1)[1]
    assert "Räume &amp; Ressourcen" not in card_section
    assert 'value="az" selected' in page.text
    # Unknown filter parameters never produce a new category or hidden module.
    page = client.get("/module?category=unknown&sort=unexpected")
    assert page.status_code == 200
    assert 'class="module-hub-category is-selected"' in page.text
    assert 'value="unexpected"' not in page.text


def test_hub_favorite_keeps_search_context_and_shows_exact_pinned_shortcut():
    client = login(*ADMIN)
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=ADMIN[0]).one()
        old = user.nav_json
        user.nav_json = ""
        db.commit()
    try:
        page = client.get("/module?q=Besprechung&category=schedule&sort=favorites")
        assert page.status_code == 200
        response = client.post(
            "/module/favorite",
            data={
                "csrf": csrf_of(page.text), "id": "meetings", "on": "1",
                "q": "Besprechung", "category": "schedule", "sort": "favorites",
            },
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)
        loc = urlsplit(response.headers["location"])
        assert loc.path == "/module" and loc.fragment == "module-meetings"
        assert parse_qs(loc.query) == {
            "q": ["Besprechung"], "category": ["schedule"], "sort": ["favorites"]
        }
        assert 'aria-pressed="true"' in client.get(response.headers["location"]).text
        # Pinned submodule entries must also be listed by their own authorized ID.
        with SessionLocal() as db:
            user = db.query(User).filter_by(email=ADMIN[0]).one()
            user.nav_json = nav.dump(["meeting_plan"], [], [], user=user)
            db.commit()
        page = client.get("/module")
        favorites = page.text.split('class="module-hub-favorite-list"', 1)[1].split("</nav>", 1)[0]
        assert "Besprechung planen" in favorites
        assert 'href="/meetings/plan"' in favorites
    finally:
        with SessionLocal() as db:
            user = db.query(User).filter_by(email=ADMIN[0]).one()
            user.nav_json = old
            db.commit()


def test_hub_restricted_user_sees_no_admin_and_cannot_pin_admin():
    email = "hub-restricted@example.org"
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).one_or_none()
        if user is None:
            user = User(email=email, name="Hub Restricted",
                        password_hash=hash_password("hub-password-123"),
                        permissions="video", must_change_password=False)
            db.add(user)
        user.permissions = "video"
        user.is_admin = False
        user.nav_json = ""
        user.must_change_password = False
        db.commit()
    client = login(email, "hub-password-123")
    response = client.get("/module")
    assert response.status_code == 200
    html = response.text.split('class="module-hub"', 1)[1]
    assert 'href="/admin"' not in html
    assert 'id="module-users"' not in html
    assert 'id="module-meetings"' in html
    assert client.get("/module?q=Benutzerverwaltung").status_code == 200
    assert "Keine passenden Module gefunden" in client.get("/module?q=Benutzerverwaltung").text
    result = client.post("/nav/pin", data={
        "csrf": csrf_of(response.text), "id": "users", "on": "1"
    })
    assert result.status_code == 200
    assert "users" not in result.json()["fav"]
    assert client.post("/module/favorite", data={
        "csrf": csrf_of(response.text), "id": "users", "on": "1"
    }).status_code == 403
