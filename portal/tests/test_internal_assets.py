"""Regressionen für interne Inventarreservierung, Ausgabe und Wartung."""
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.db import SessionLocal, User, to_local, utcnow
from app.internal_asset_models import (
    InternalAsset, InternalAssetEvent, InternalAssetMaintenance,
    InternalAssetReservation, InternalStorageLocation,
)
from app.routes_internal_assets import _access, _available, _peak
from app.main import module_for_path
from conftest import csrf_of, client, login, settings


def _dt(days=7, hours=0):
    return to_local(utcnow() + timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M")


def test_capacity_uses_peak_not_sum_and_issued_blocks_future(db):
    asset = InternalAsset(name="Prüf-Beamer", quantity=2, created_by_id=1)
    db.add(asset)
    db.flush()
    base = utcnow() + timedelta(days=10)
    one = InternalAssetReservation(asset_id=asset.id, user_id=1, starts_at=base,
                                   ends_at=base + timedelta(hours=1), quantity=2)
    two = InternalAssetReservation(asset_id=asset.id, user_id=1,
                                   starts_at=base + timedelta(hours=1),
                                   ends_at=base + timedelta(hours=2), quantity=2)
    db.add_all([one, two])
    db.flush()
    assert _peak(db, asset.id, base, base + timedelta(hours=2)) == 2
    assert _available(db, asset, base, base + timedelta(hours=2)) == 0
    assert _available(db, asset, base + timedelta(hours=3), base + timedelta(hours=4)) == 2
    one.status = "issued"
    db.flush()
    assert _peak(db, asset.id, base + timedelta(days=3), base + timedelta(days=4)) == 2
    one.status = "returned"
    db.flush()
    assert _peak(db, asset.id, base + timedelta(days=3), base + timedelta(days=4)) == 0
    db.rollback()


def test_maintenance_reduces_future_capacity(db):
    asset = InternalAsset(name="Wartung-Pavillon", quantity=4, created_by_id=1)
    db.add(asset)
    db.flush()
    base = utcnow() + timedelta(days=10)
    db.add(InternalAssetMaintenance(asset_id=asset.id, starts_at=base,
                                    ends_at=base + timedelta(hours=2),
                                    quantity=3, created_by_id=1, reason="Reparatur"))
    db.flush()
    assert _available(db, asset, base, base + timedelta(hours=1)) == 1
    assert _available(db, asset, base + timedelta(hours=2), base + timedelta(hours=3)) == 4
    db.rollback()


def test_book_right_is_not_manage_right():
    settings(module_internal_assets="1")
    staff = User(email="pool-staff@example.org", name="Pool-Test",
                 permissions="internal_assets_book", active=True, is_admin=False)
    assert _access(staff) is False
    try:
        _access(staff, manage=True)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("Buchende dürfen keine Bestände ändern")


def test_inventory_booking_issue_return_http():
    settings(module_internal_assets="1")
    c = login("admin@example.org", "admin-passwort-123")
    page = c.get("/interne-ressourcen")
    assert page.status_code == 200, page.text[:500]
    assert "Interne Ressourcen" in page.text
    csrf = csrf_of(page.text)
    res = c.post("/interne-ressourcen/lagerorte",
                 data={"csrf": csrf, "name": "Lager Test Pool", "building": "Rathaus"})
    assert res.status_code == 303, res.text[:300]
    with SessionLocal() as db:
        location_id = db.scalar(select(InternalStorageLocation.id).where(
            InternalStorageLocation.name == "Lager Test Pool").order_by(
            InternalStorageLocation.id.desc()))
    res = c.post("/interne-ressourcen/gegenstaende", data={
        "csrf": csrf, "name": "End-to-End-Leinwand", "category": "Präsentation",
        "quantity": 1, "location_id": location_id, "inventory_code": "POOL-E2E-01",
    })
    assert res.status_code == 303, res.text[:300]
    with SessionLocal() as db:
        asset_id = db.scalar(select(InternalAsset.id).where(
            InternalAsset.name == "End-to-End-Leinwand").order_by(InternalAsset.id.desc()))
    start, end = _dt(12), _dt(12, 2)
    data = {"csrf": csrf, "start": start, "end": end, "quantity": 1, "purpose": "Sitzung"}
    assert c.post(f"/interne-ressourcen/{asset_id}/reservieren", data=data).status_code == 303
    availability = c.get("/interne-ressourcen/verfuegbarkeit",
                         params={"asset_id": asset_id, "start": start, "end": end})
    assert availability.status_code == 200 and availability.json()["available"] == 0
    assert c.post(f"/interne-ressourcen/{asset_id}/reservieren", data=data).status_code == 303
    with SessionLocal() as db:
        bookings = list(db.scalars(select(InternalAssetReservation).where(
            InternalAssetReservation.asset_id == asset_id)))
        assert len(bookings) == 1
        booking_id = bookings[0].id
    issue = c.post(f"/interne-ressourcen/buchungen/{booking_id}/issue", data={"csrf": csrf})
    assert issue.status_code == 303
    after = c.get("/interne-ressourcen/verfuegbarkeit",
                  params={"asset_id": asset_id, "start": _dt(20), "end": _dt(20, 1)})
    assert after.json()["available"] == 0
    returned = c.post(f"/interne-ressourcen/buchungen/{booking_id}/return",
                      data={"csrf": csrf, "note": "Vollständig und unbeschädigt"})
    assert returned.status_code == 303
    after_return = c.get("/interne-ressourcen/verfuegbarkeit",
                         params={"asset_id": asset_id, "start": start, "end": end})
    assert after_return.json()["available"] == 1
    with SessionLocal() as db:
        assert db.get(InternalAssetReservation, booking_id).status == "returned"
        assert db.scalar(select(InternalAssetEvent.id).where(
            InternalAssetEvent.reservation_id == booking_id,
            InternalAssetEvent.action == "returned")) is not None


def test_maintenance_http_blocks_and_can_be_lifted():
    settings(module_internal_assets="1")
    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/interne-ressourcen").text)
    c.post("/interne-ressourcen/gegenstaende", data={
        "csrf": csrf, "name": "Wartungs-Test-Beamer", "quantity": 1,
    })
    with SessionLocal() as db:
        aid = db.scalar(select(InternalAsset.id).where(
            InternalAsset.name == "Wartungs-Test-Beamer").order_by(InternalAsset.id.desc()))
    start, end = _dt(22), _dt(22, 1)
    r = c.post(f"/interne-ressourcen/{aid}/wartung", data={
        "csrf": csrf, "start": start, "end": end, "quantity": 1, "reason": "Sicherheitsprüfung"})
    assert r.status_code == 303
    r = c.get("/interne-ressourcen/verfuegbarkeit",
              params={"asset_id": aid, "start": start, "end": end})
    assert r.json()["available"] == 0
    with SessionLocal() as db:
        mid = db.scalar(select(InternalAssetMaintenance.id).where(
            InternalAssetMaintenance.asset_id == aid))
    assert c.post(f"/interne-ressourcen/wartungen/{mid}/loeschen",
                  data={"csrf": csrf}).status_code == 303
    r = c.get("/interne-ressourcen/verfuegbarkeit",
              params={"asset_id": aid, "start": start, "end": end})
    assert r.json()["available"] == 1


def test_week_plan_keeps_personal_details_private():
    settings(module_internal_assets="1")
    c = login("admin@example.org", "admin-passwort-123")
    response = c.get("/interne-ressourcen/plan")
    assert response.status_code == 200, response.text[:400]
    assert "Materialplan" in response.text
    assert "Vorige Woche" in response.text


def test_ical_contains_no_public_token():
    settings(module_internal_assets="1")
    c = login("admin@example.org", "admin-passwort-123")
    with SessionLocal() as db:
        bid = db.scalar(select(InternalAssetReservation.id).where(
            InternalAssetReservation.status == "returned").order_by(
            InternalAssetReservation.id.desc()))
    if bid:
        response = c.get(f"/interne-ressourcen/buchungen/{bid}/termin.ics")
        assert response.status_code == 200
        assert b"BEGIN:VCALENDAR" in response.content
        assert b"BEGIN:VEVENT" in response.content
        assert "private" in response.headers["cache-control"]


def test_booker_is_not_inventory_manager_over_http():
    from app.security import hash_password
    settings(module_internal_assets="1")
    email, password = "pool-only@example.org", "Testbucher-123456"
    with SessionLocal() as db:
        person = db.scalar(select(User).where(User.email == email))
        if not person:
            person = User(email=email, name="Gerätepool-Testperson",
                          password_hash=hash_password(password), permissions="internal_assets_book",
                          active=True, password_set=True)
            db.add(person)
        else:
            person.password_hash = hash_password(password)
            person.permissions, person.active, person.must_change_password = "internal_assets_book", True, False
        db.commit()
    c = login(email, password)
    page = c.get("/interne-ressourcen")
    assert page.status_code == 200 and "Interne Ressourcen" in page.text
    assert c.get("/interne-ressourcen/plan").status_code == 200
    csrf = csrf_of(page.text)
    creation = c.post("/interne-ressourcen/gegenstaende",
                      data={"csrf": csrf, "name": "Unzulässiges Inventar"})
    assert creation.status_code == 403
    with SessionLocal() as db:
        booking = db.scalar(select(InternalAssetReservation).order_by(
            InternalAssetReservation.id.desc()))
        if booking:
            response = c.get(f"/interne-ressourcen/buchungen/{booking.id}/termin.ics")
            assert response.status_code == 404


@pytest.fixture(autouse=True)
def ensure_internal_assets_module():
    # Eigenständige Aktivierung auch dann, wenn andere Tests den Schalter verändern.
    settings(module_internal_assets="1")
    yield
    settings(module_internal_assets="1")


def test_module_is_separate_from_public_rental():
    assert module_for_path("/interne-ressourcen") == "internal_assets"
    assert module_for_path("/interne-ressourcen/plan") == "internal_assets"
    assert module_for_path("/resources/intern") == "internal_assets"
    assert module_for_path("/resources/intern/plan") == "internal_assets"
    assert module_for_path("/resources") == "resources"
    assert module_for_path("/r") == "resources"
    c = login("admin@example.org", "admin-passwort-123")
    settings(module_resources="0", module_internal_assets="1")
    try:
        dashboard = c.get("/interne-ressourcen")
        assert dashboard.status_code == 200, dashboard.text[:300]
        assert 'href="/interne-ressourcen"' in dashboard.text
        assert c.get("/resources").status_code == 404
        old = c.get("/resources/intern?verlauf=1")
        assert old.status_code == 308
        assert old.headers["location"] == "/interne-ressourcen?verlauf=1"
        assert c.get("/resources/intern/plan").status_code == 308
    finally:
        settings(module_resources="1", module_internal_assets="1")


def test_module_deactivation_preserves_public_rental():
    c = login("admin@example.org", "admin-passwort-123")
    settings(module_resources="1", module_internal_assets="0")
    try:
        assert c.get("/interne-ressourcen").status_code == 404
        assert c.get("/interne-ressourcen/plan").status_code == 404
        assert c.get("/resources/intern").status_code == 404
        assert c.get("/resources").status_code == 200
    finally:
        settings(module_resources="1", module_internal_assets="1")


def test_pool_permissions_are_not_implicitly_granted_by_public_rental():
    from app.security import hash_password
    email, password = "rental-only-test@example.org", "rental-only-4567"
    with SessionLocal() as db:
        person = db.scalar(select(User).where(User.email == email))
        if person is None:
            person = User(email=email, name="Nur Vermietung", password_hash=hash_password(password),
                          permissions="resources", active=True, password_set=True)
            db.add(person)
        else:
            person.permissions, person.active = "resources", True
            person.password_hash = hash_password(password)
        person.must_change_password = False
        db.commit()
    c = login(email, password)
    page = c.get("/resources")
    assert page.status_code == 200
    html = page.text
    assert 'href="/interne-ressourcen"' not in html
    assert c.get("/interne-ressourcen").status_code == 403
    assert c.get("/resources/intern").status_code == 403


def test_separate_menu_is_visible_to_booking_only_user():
    from app.security import hash_password
    email, password = "pool-standalone-test@example.org", "pool-standalone-4567"
    with SessionLocal() as db:
        person = db.scalar(select(User).where(User.email == email))
        if person is None:
            person = User(email=email, name="Nur interne Ressourcen", password_hash=hash_password(password),
                          permissions="internal_assets_book", active=True, password_set=True)
            db.add(person)
        else:
            person.permissions, person.active = "internal_assets_book", True
            person.password_hash = hash_password(password)
        person.must_change_password = False
        db.commit()
    c = login(email, password)
    settings(module_resources="0", module_internal_assets="1")
    try:
        page = c.get("/interne-ressourcen")
        assert page.status_code == 200, page.text[:300]
        assert 'data-nav-id="internal_assets"' in page.text
        assert 'href="/resources"' not in page.text
        assert 'href="/interne-ressourcen/plan"' in page.text
    finally:
        settings(module_resources="1", module_internal_assets="1")


def test_legacy_calendar_link_redirect_keeps_bookings_private():
    c = login("admin@example.org", "admin-passwort-123")
    with SessionLocal() as db:
        book = db.scalar(select(InternalAssetReservation).order_by(InternalAssetReservation.id.desc()))
        if book:
            response = c.get(f"/resources/intern/buchungen/{book.id}/termin.ics")
            assert response.status_code == 308
            assert response.headers["location"] == f"/interne-ressourcen/buchungen/{book.id}/termin.ics"
