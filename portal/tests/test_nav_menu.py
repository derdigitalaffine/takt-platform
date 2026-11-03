"""Portal-Menü: neue Gruppen, nur Sichtbares, Favoriten (Stern und „Menü anpassen“), ausgeblendete Gruppen."""

import json

import pytest

from app import nav
from app.db import SessionLocal, User

from conftest import csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")


@pytest.fixture(autouse=True)
def reset():
    settings(module_tasks="1", module_forms="1", module_applications="1", module_laws="1", module_maps="1", module_polls="1")
    with SessionLocal() as db:
        for u in db.query(User):
            u.nav_json = ""
        db.commit()
    yield


def nav_html(html: str) -> str:
    start = html.index('id="app-nav"')
    return html[start:html.index("app-nav-custom", start) + 400]


def test_groups_and_single_active_entry():
    c = login(*ADMIN)
    html = nav_html(c.get("/forms/inbox").text)
    labels = [v for v in nav.GROUPS.values() if f"<span>{v.replace('&', '&amp;')}</span>" in html]
    assert labels[0] == "Zusammenarbeit" and labels[-1] == "Personal & Vertretung"
    assert html.count('aria-current="page"') == 1                 # nur „Zum Ausfüllen“, nicht auch „Formulare“
    assert 'href="/forms" aria-current="page"' in html
    assert 'data-nav-id="trash"' in html and 'href="/profile/menu"' in html
    # Abgeschaltete Module erscheinen nicht
    settings(module_laws="0")
    assert 'href="/laws"' not in nav_html(c.get("/").text)


def test_pin_and_customize():
    c = login(*ADMIN)
    page = c.get("/")
    token = csrf_of(page.text)
    r = c.post("/nav/pin", data={"csrf": token, "id": "recht", "on": "1"})
    assert r.json() == {"ok": True, "fav": ["recht"]}
    c.post("/nav/pin", data={"csrf": token, "id": "users", "on": "1"})
    assert c.post("/nav/pin", data={"csrf": token, "id": "gibtsnicht", "on": "1"}).json()["fav"] == ["recht", "users"]
    html = nav_html(c.get("/").text)
    favs = html[html.index('id="nav-favs"'):html.index("</ul>", html.index('id="nav-favs"'))]
    assert favs.index('data-nav-id="recht"') < favs.index('data-nav-id="users"')
    assert c.post("/nav/pin", data={"csrf": token, "id": "recht", "on": "0"}).json()["fav"] == ["users"]
    # Menü anpassen: Reihenfolge, Gruppe ausblenden
    page = c.get("/profile/menu")
    assert page.status_code == 200 and "Reihenfolge der Favoriten" in page.text
    shown = [g for g in nav.GROUPS if g != "schedule"]
    c.post("/profile/menu", data={"csrf": csrf_of(page.text), "fav": ["users", "map", "forms"],
                                  "fav_order": ["map", "users"], "show": shown})
    with SessionLocal() as db:
        data = json.loads(db.query(User).filter(User.email == ADMIN[0]).one().nav_json)
    assert data == {"fav": ["map", "users", "forms"], "hidden": ["schedule"], "closed": [g for g in nav.GROUPS if g != "work"]}
    html = nav_html(c.get("/").text)
    assert 'data-personal-hidden="1"' in html and "1 ausgeblendet" in html
    # auf einer Seite der ausgeblendeten Gruppe erscheint sie trotzdem
    assert "<span>Termine &amp; Veranstaltungen</span>" in nav_html(c.get("/meetings").text)
    c.post("/profile/menu", data={"csrf": csrf_of(page.text), "reset": "1"})
    assert "<span>Termine &amp; Veranstaltungen</span>" in nav_html(c.get("/").text)


def test_limited_user_sees_only_allowed_entries():
    c = login(*ADMIN)
    page = c.get("/admin/users")
    with SessionLocal() as db:
        from app.security import hash_password
        u = db.query(User).filter(User.email == "menu-user@example.org").one_or_none()
        if u is None:
            u = User(email="menu-user@example.org", name="Menü Nutzer", password_hash=hash_password("menu-passwort-123"),
                     permissions="video")
            db.add(u)
        u.must_change_password = False
        db.commit()
    assert page.status_code == 200
    html = nav_html(login("menu-user@example.org", "menu-passwort-123").get("/").text)
    assert 'href="/meetings"' in html and 'href="/admin/users"' not in html and "Administration" not in html


def test_expansion_account_persistence_preserved_when_pinning():
    c=login(*ADMIN);page=c.get('/');token=csrf_of(page.text)
    assert c.post('/nav/expand',data={'closed':['know']}).status_code==400
    r=c.post('/nav/expand',data={'csrf':token,'closed':['know','invalid']});assert r.status_code==200
    c.post('/nav/pin',data={'csrf':token,'id':'map','on':'1'})
    with SessionLocal() as db:
        u=db.query(User).filter(User.email==ADMIN[0]).one()
        assert nav.prefs(u)['closed']==['know'] and nav.prefs(u)['fav']==['map']
        old=u.nav_json;u.nav_json='{"fav": [null, {}], "closed": null}';assert nav.prefs(u)['fav']==[];u.nav_json=old
    page=login(*ADMIN).get('/karte');assert page.status_code==200 and 'Meine Karten' in page.text


def test_catalog_discovery_filter_favorite_and_disabled_modules():
    c = login(*ADMIN)
    page = c.get('/module')
    assert page.status_code == 200
    assert 'Ihre Module' in page.text and 'Kanbanboards' in page.text
    assert 'Dokumentenablage' in c.get('/module?q=DMS').text
    assert 'Keine passenden Module' in c.get('/module?q=nothingmatches123').text
    assert 'Räume &amp; Ressourcen' not in c.get('/module?category=work').text.split('module-catalog')[1]
    token = csrf_of(page.text)
    c.post('/module/favorite', data={'csrf': token, 'id': 'kanban', 'on': '1'})
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == ADMIN[0]).one()
        assert 'kanban' in nav.prefs(u)['fav']
        u.nav_json = nav.dump(['kanban'], ['work'])
        db.commit()
    assert 'Kanbanboards' in c.get('/module').text
    assert 'data-personal-hidden="1"' in c.get('/').text
    settings(module_tasks='0')
    assert 'Kanbanboards' not in c.get('/module').text
    assert c.post('/module/favorite', data={'csrf':token,'id':'kanban','on':'1'}).status_code == 403
    settings(module_tasks='1')


def test_catalog_and_administration_require_login():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get('/module', follow_redirects=False).status_code in (302, 303)
        assert c.get('/admin', follow_redirects=False).status_code in (302, 303)


def test_family_catalog_covers_every_entry_and_preserves_legacy_ids():
    covered = {i for f in nav.FAMILIES for i in f}
    covered.update(i for ids in nav.ADMIN_SECTIONS.values() for i in ids)
    assert covered == set(nav.BY_ID)
    class Account:
        nav_json = '{"fav":["meeting_plan","krank_mine"],"hidden":["comm"],"closed":["comm"]}'
    p = nav.prefs(Account())
    assert p['fav'] == ['meeting_plan','krank_mine']
    assert not p['hidden']


def test_restricted_user_catalog_and_delegated_admin():
    from app.security import hash_password
    with SessionLocal() as db:
        u=User(email='nav-delegate@example.org',name='Delegate',password_hash=hash_password('delegate-pass-123'),permissions='users',must_change_password=False)
        db.add(u);db.commit()
    c=login('nav-delegate@example.org','delegate-pass-123')
    html=c.get('/admin').text.split('id="inhalt"')[1]
    assert 'Benutzer &amp; Gruppen' in html
    assert 'HTTPS &amp; Zertifikat' not in html
    assert c.get('/admin/domains').status_code==403
    with SessionLocal() as db:
        u=db.query(User).filter_by(email='nav-delegate@example.org').one();u.permissions='';db.commit()
    assert c.get('/admin').status_code==403
    assert 'Administration öffnen' not in c.get('/module').text
    assert c.post('/module/favorite',data={'csrf':csrf_of(c.get('/module').text),'id':'users','on':'1'}).status_code==403


def test_navigation_context_is_request_scoped(monkeypatch):
    from app import main
    from starlette.requests import Request
    from types import SimpleNamespace
    calls=[]
    for name in ('_shared_nav','_task_badge','_dms_nav','_res_nav','_krank_nav'):
        monkeypatch.setattr(main,name,lambda user,name=name: calls.append((name,user.id)) or False)
    req=Request({'type':'http'})
    one=SimpleNamespace(id=1)
    assert main._navigation_context(req,one) is main._navigation_context(req,one)
    assert len(calls)==5
    main._navigation_context(req,SimpleNamespace(id=2))
    assert len(calls)==10
    main._navigation_context(Request({'type':'http'}),one)
    assert len(calls)==15
