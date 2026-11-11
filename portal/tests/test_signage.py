"""Digital Signage acceptance and privacy regressions."""
import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select

from conftest import client, csrf_of, login, settings
from app import signage
from app.db import LOCAL_TZ, Resource, ResourceBooking, SessionLocal, User, utcnow
from app.calendar_models import Calendar, CalendarEvent
from app.signage_models import (SignageBuilding, SignageDevice, SignageFloor, SignageLink,
                                SignageOffice, SignageRoom, SignageScreen, SignageRevision)


ADMIN = ("admin@example.org", "admin-passwort-123")


def _admin():
    settings(module_signage="1")
    return login(*ADMIN)


def _screen(admin, name="Signage Test", kind="agenda", visibility="private", data_level="busy", resource_id=None):
    page = admin.get("/signage")
    csrf = csrf_of(page.text)
    result = admin.post("/signage/new", data={"csrf": csrf, "name": name, "kind": kind})
    assert result.status_code == 303, result.text
    match = re.search(r"/signage/(\d+)/edit", result.headers["location"])
    assert match
    sid = int(match.group(1))
    if visibility != "private" or resource_id:
        csrf = csrf_of(admin.get(f"/signage/{sid}/edit").text)
        response = admin.post(f"/signage/{sid}/save", data={
            "csrf": csrf, "name": name, "kind": kind, "visibility": visibility,
            "data_level": data_level, "resource_id": str(resource_id or ""),
            "enabled": "1", "background": "#111e30", "foreground": "#f8fafc",
            "accent": "#42d4ad", "layout_json": '["clock","agenda","status"]',
        })
        assert response.status_code == 303, response.text
    return sid


def test_module_disabled_blocks_even_public_routes():
    settings(module_signage="0")
    assert client().get("/signage/view/10").status_code == 404


def test_admin_studio_and_default_private_screen():
    c = _admin()
    sid = _screen(c, "Sitzungszimmer")
    assert "Signage Studio" in c.get(f"/signage/{sid}/edit").text
    assert client().get(f"/signage/view/{sid}").status_code == 404
    assert c.get(f"/signage/{sid}/preview").status_code == 200
    assert "Sitzungszimmer" in c.get(f"/signage/{sid}/preview").text


def test_public_display_never_shows_booking_titles_or_applicants():
    c = _admin()
    with SessionLocal() as db:
        resource = Resource(name="Sitzungsraum Signage", slug="signage-privacy-room")
        db.add(resource)
        db.flush()
        row = ResourceBooking(ref="signage-confidential", token="signage-fixture-secret", resource_id=resource.id,
            starts_at=utcnow() - timedelta(minutes=5),
            ends_at=utcnow() + timedelta(minutes=45), status="confirmed",
            title="VERTRAULICHE PERSONALBERATUNG", name="DATENSCHUTZ TESTPERSON",
            email="private@example.org")
        db.add(row)
        db.commit()
        resource_id = resource.id
    sid = _screen(c, name="Sitzungsanzeige", kind="room", visibility="public",
                  data_level="title", resource_id=resource_id)
    r = client().get(f"/signage/view/{sid}")
    assert r.status_code == 200
    assert "Belegt" in r.text
    assert "VERTRAULICHE PERSONALBERATUNG" not in r.text
    assert "DATENSCHUTZ TESTPERSON" not in r.text
    assert "private@example.org" not in r.text
    assert r.headers["cache-control"].startswith("no-store")
    assert r.headers["referrer-policy"] == "no-referrer"


def test_secure_link_is_hash_only_and_revocable():
    c = _admin()
    sid = _screen(c, "Link Display", visibility="link")
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    response = c.post(f"/signage/{sid}/share", data={"csrf": csrf, "days": "7"})
    assert response.status_code == 200
    secret = re.search(r'<pre id="sg-secret">([^<]+)</pre>', response.text)
    assert secret
    url = secret.group(1)
    token = url.rsplit("/", 1)[-1]
    with SessionLocal() as db:
        row = db.scalar(select(SignageLink).where(SignageLink.screen_id == sid))
        assert row and row.token_hash == signage.digest(token)
        assert token not in row.token_hash
        key_id = row.id
    path = urlsplit(url).path
    visitor = client()
    exchange = visitor.get(path)
    assert exchange.status_code == 303
    assert exchange.headers["location"] == f"/signage/access/{sid}"
    assert "httponly" in exchange.headers["set-cookie"].lower()
    assert "secure" in exchange.headers["set-cookie"].lower()
    assert visitor.get(f"/signage/access/{sid}").status_code == 200
    assert client().get(f"/signage/access/{sid}").status_code == 404
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    revoked = c.post(f"/signage/{sid}/link/{key_id}/revoke", data={"csrf": csrf})
    assert revoked.status_code == 303
    assert client().get(path).status_code == 404
    assert visitor.get(f"/signage/access/{sid}").status_code == 404


def test_directory_requires_explicit_public_approval():
    with SessionLocal() as db:
        user = User(name="Nur intern hinterlegt", email="sg-internal@example.org", password_hash="unused")
        building = SignageBuilding(name="Rathaus Test")
        db.add_all([user, building])
        db.flush()
        floor = SignageFloor(building_id=building.id, name="EG", level=0)
        db.add(floor)
        db.flush()
        room = SignageRoom(floor_id=floor.id, name="Büro", number="0.1")
        db.add(room)
        db.flush()
        office = SignageOffice(user_id=user.id, room_id=room.id, public=False)
        db.add(office)
        screen = SignageScreen(name="Wegweiser", kind="directory")
        db.add(screen)
        db.commit()
        rows = signage.staff_directory(db, screen)
        assert not any("Nur intern hinterlegt" == item["name"] for item in rows)
        office.public = True
        db.commit()
        assert any("Nur intern hinterlegt" == item["name"] for item in signage.staff_directory(db, screen))


def test_widget_and_theme_whitelists():
    assert signage.widgets('["clock","<script>","agenda","clock"]') == ["clock", "agenda"]
    assert signage.widgets('{"not":"a-list"}', "room") == signage.TEMPLATES["room"]
    colors = signage.theme({"background": "red; x", "foreground": "#123456", "accent": "#42d4ad"})
    assert colors["background"] == signage.THEME_DEFAULTS["background"]
    assert colors["foreground"] == "#123456"


def test_device_heartbeat_needs_valid_bearer():
    c = _admin()
    sid = _screen(c, "Device Display")
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    response = c.post(f"/signage/{sid}/device", data={"csrf": csrf, "name": "Lobby"})
    assert response.status_code == 200
    m = re.search(r"Gerät-ID: (\d+)\s+Bearer: ([\w-]+)", response.text)
    assert m
    did, secret = int(m.group(1)), m.group(2)
    assert client().post(f"/signage/api/device/{did}/heartbeat").status_code == 403
    ok = client().post(f"/signage/api/device/{did}/heartbeat", headers={"Authorization": f"Bearer {secret}"})
    assert ok.status_code == 200 and ok.json()["screen_id"] == sid
    feed = client().get(f"/signage/api/device/{did}/manifest",
                        headers={"Authorization": f"Bearer {secret}"})
    assert feed.status_code == 200 and feed.json()["screen"]["id"] == sid
    assert feed.headers["cache-control"] == "no-store"
    assert client().get(f"/signage/api/device/{did}/manifest").status_code == 403
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    assert c.post(f"/signage/{sid}/device/{did}/revoke",
                  data={"csrf": csrf}).status_code == 303
    assert client().get(f"/signage/api/device/{did}/manifest",
                        headers={"Authorization": f"Bearer {secret}"}).status_code == 403

def test_calendar_event_occupancy_requires_explicit_room_binding_and_does_not_leak_title():
    c = _admin()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == ADMIN[0]))
        cal = Calendar(owner_id=admin.id, title="Vertraulicher Raumkalender", visibility="private", source="free")
        building = SignageBuilding(name="Kalender Testgebäude")
        db.add_all([cal, building]); db.flush()
        floor = SignageFloor(building_id=building.id, name="EG", level=0)
        db.add(floor); db.flush()
        room = SignageRoom(floor_id=floor.id, number="K1", name="Konferenz")
        db.add(room); db.flush()
        from datetime import datetime
        local_now = datetime.now(LOCAL_TZ)
        event = CalendarEvent(
            calendar_id=cal.id, uid="private-signage-room-event",
            title="GEHEIMER PERSONALTERMIN", starts_at=(local_now - timedelta(minutes=10)).isoformat(),
            ends_at=(local_now + timedelta(minutes=60)).isoformat())
        db.add(event); db.commit()
        room_id, calendar_id = room.id, cal.id
    sid = _screen(c, name="Kalenderraum", kind="room", visibility="public", data_level="title")
    with SessionLocal() as db:
        row = db.get(SignageScreen, sid)
        row.room_id = room_id
        db.commit()
    url = f"/signage/view/{sid}"
    assert "GEHEIMER PERSONALTERMIN" not in client().get(url).text
    # No accidental calendar publication merely because the screen exists.
    assert "Heute sind keine bestätigten Buchungen eingetragen" in client().get(url).text
    csrf = csrf_of(c.get("/signage").text)
    r = c.post(f"/signage/room/{room_id}/calendar",
               data={"csrf": csrf, "calendar_id": str(calendar_id)})
    assert r.status_code == 303
    page = client().get(url)
    assert page.status_code == 200
    assert "Belegt" in page.text
    assert "GEHEIMER PERSONALTERMIN" not in page.text
    # Internal admin preview with explicit title option and existing calendar ACL.
    assert "GEHEIMER PERSONALTERMIN" in c.get(f"/signage/{sid}/preview").text


def test_calendar_date_conversion_uses_local_timezone_for_day_and_aware_iso():
    from datetime import datetime
    day = signage._calendar_date("2026-11-11")
    assert day.hour == 0 and day.tzinfo == LOCAL_TZ
    dt = signage._calendar_date("2026-11-11T13:00:00+00:00")
    assert dt.hour == 14

def test_studio_revision_restore_leaves_publication_and_links_unchanged():
    c = _admin()
    sid = _screen(c, name="Original", kind="room", visibility="link")
    with SessionLocal() as db:
        created = db.scalar(select(SignageRevision).where(
            SignageRevision.screen_id == sid, SignageRevision.version == 1))
        assert created
        revision_id = created.id
    editor = c.get(f"/signage/{sid}/edit")
    assert "Designverlauf" in editor.text
    csrf = csrf_of(editor.text)
    changed = c.post(f"/signage/{sid}/save", data={
        "csrf": csrf, "version": "1", "name": "Neues Design",
        "kind": "info", "visibility": "public", "enabled": "1",
        "background": "#000000", "foreground": "#ffffff", "accent": "#42d4ad",
        "layout_json": '["clock","message"]',
    })
    assert changed.status_code == 303
    with SessionLocal() as db:
        row = db.get(SignageScreen, sid)
        assert row.version == 2 and row.visibility == "public"
        assert db.scalar(select(SignageRevision).where(SignageRevision.screen_id == sid,
                                                       SignageRevision.version == 2))
    stale = c.post(f"/signage/{sid}/save", data={"csrf": csrf, "version": "1",
             "name": "Old tab", "kind": "agenda", "visibility": "link"})
    assert stale.status_code == 409
    restored = c.post(f"/signage/{sid}/revision/{revision_id}/restore",
                      data={"csrf": csrf, "version": "2"})
    assert restored.status_code == 303
    with SessionLocal() as db:
        row = db.get(SignageScreen, sid)
        assert row.name == "Original" and row.kind == "room"
        assert row.version == 3
        assert row.visibility == "public"  # Never restore publication state.
        assert db.scalar(select(SignageRevision).where(SignageRevision.screen_id == sid,
                                                       SignageRevision.version == 3))


def test_live_preview_changes_are_not_persisted():
    c = _admin()
    sid = _screen(c, name="Original Preview", kind="agenda")
    editor = c.get(f"/signage/{sid}/edit")
    assert "sg-live-status" in editor.text
    csrf = csrf_of(editor.text)
    preview = c.post(f"/signage/{sid}/preview-live", data={
        "csrf": csrf, "name": "Entwurf nur in Vorschau",
        "kind": "info", "subtitle": "Nicht gespeichert",
        "visibility": "public", "resource_id": "", "room_id": "", "org_id": "",
        "background": "#162b3e", "foreground": "#f8fafc", "accent": "#42d4ad",
        "layout_json": '["clock","message"]'
    })
    assert preview.status_code == 200, preview.text[:400]
    assert "Entwurf nur in Vorschau" in preview.text
    assert "Nicht gespeichert" in preview.text
    assert preview.headers["cache-control"].startswith("no-store")
    with SessionLocal() as db:
        row = db.get(SignageScreen, sid)
        assert row.name == "Original Preview" and row.kind == "agenda"
        assert row.visibility == "private"
        assert row.version == 1
