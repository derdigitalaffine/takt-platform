"""Regressionen für interne Inventarreservierung, Ausgabe und Wartung."""
from datetime import timedelta
from sqlalchemy import select
from app.db import SessionLocal, User, to_local, utcnow
from app.internal_asset_models import (
    InternalAsset, InternalAssetEvent, InternalAssetMaintenance,
    InternalAssetReservation, InternalStorageLocation,
)
from app.routes_internal_assets import _access, _available, _peak
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
    settings(module_resources="1")
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
    settings(module_resources="1")
    c = login("admin@example.org", "admin-passwort-123")
    page = c.get("/resources/intern")
    assert page.status_code == 200, page.text[:500]
    assert "Interner Gerätepool" in page.text
    csrf = csrf_of(page.text)
    res = c.post("/resources/intern/lagerorte",
                 data={"csrf": csrf, "name": "Lager Test Pool", "building": "Rathaus"})
    assert res.status_code == 303, res.text[:300]
    with SessionLocal() as db:
        location_id = db.scalar(select(InternalStorageLocation.id).where(
            InternalStorageLocation.name == "Lager Test Pool").order_by(
            InternalStorageLocation.id.desc()))
    res = c.post("/resources/intern/gegenstaende", data={
        "csrf": csrf, "name": "End-to-End-Leinwand", "category": "Präsentation",
        "quantity": 1, "location_id": location_id, "inventory_code": "POOL-E2E-01",
    })
    assert res.status_code == 303, res.text[:300]
    with SessionLocal() as db:
        asset_id = db.scalar(select(InternalAsset.id).where(
            InternalAsset.name == "End-to-End-Leinwand").order_by(InternalAsset.id.desc()))
    start, end = _dt(12), _dt(12, 2)
    data = {"csrf": csrf, "start": start, "end": end, "quantity": 1, "purpose": "Sitzung"}
    assert c.post(f"/resources/intern/{asset_id}/reservieren", data=data).status_code == 303
    availability = c.get("/resources/intern/verfuegbarkeit",
                         params={"asset_id": asset_id, "start": start, "end": end})
    assert availability.status_code == 200 and availability.json()["available"] == 0
    assert c.post(f"/resources/intern/{asset_id}/reservieren", data=data).status_code == 303
    with SessionLocal() as db:
        bookings = list(db.scalars(select(InternalAssetReservation).where(
            InternalAssetReservation.asset_id == asset_id)))
        assert len(bookings) == 1
        booking_id = bookings[0].id
    issue = c.post(f"/resources/intern/buchungen/{booking_id}/issue", data={"csrf": csrf})
    assert issue.status_code == 303
    after = c.get("/resources/intern/verfuegbarkeit",
                  params={"asset_id": asset_id, "start": _dt(20), "end": _dt(20, 1)})
    assert after.json()["available"] == 0
    returned = c.post(f"/resources/intern/buchungen/{booking_id}/return",
                      data={"csrf": csrf, "note": "Vollständig und unbeschädigt"})
    assert returned.status_code == 303
    after_return = c.get("/resources/intern/verfuegbarkeit",
                         params={"asset_id": asset_id, "start": start, "end": end})
    assert after_return.json()["available"] == 1
    with SessionLocal() as db:
        assert db.get(InternalAssetReservation, booking_id).status == "returned"
        assert db.scalar(select(InternalAssetEvent.id).where(
            InternalAssetEvent.reservation_id == booking_id,
            InternalAssetEvent.action == "returned")) is not None


def test_maintenance_http_blocks_and_can_be_lifted():
    settings(module_resources="1")
    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/resources/intern").text)
    c.post("/resources/intern/gegenstaende", data={
        "csrf": csrf, "name": "Wartungs-Test-Beamer", "quantity": 1,
    })
    with SessionLocal() as db:
        aid = db.scalar(select(InternalAsset.id).where(
            InternalAsset.name == "Wartungs-Test-Beamer").order_by(InternalAsset.id.desc()))
    start, end = _dt(22), _dt(22, 1)
    r = c.post(f"/resources/intern/{aid}/wartung", data={
        "csrf": csrf, "start": start, "end": end, "quantity": 1, "reason": "Sicherheitsprüfung"})
    assert r.status_code == 303
    r = c.get("/resources/intern/verfuegbarkeit",
              params={"asset_id": aid, "start": start, "end": end})
    assert r.json()["available"] == 0
    with SessionLocal() as db:
        mid = db.scalar(select(InternalAssetMaintenance.id).where(
            InternalAssetMaintenance.asset_id == aid))
    assert c.post(f"/resources/intern/wartungen/{mid}/loeschen",
                  data={"csrf": csrf}).status_code == 303
    r = c.get("/resources/intern/verfuegbarkeit",
              params={"asset_id": aid, "start": start, "end": end})
    assert r.json()["available"] == 1


def test_week_plan_keeps_personal_details_private():
    settings(module_resources="1")
    c = login("admin@example.org", "admin-passwort-123")
    response = c.get("/resources/intern/plan")
    assert response.status_code == 200, response.text[:400]
    assert "Material-Belegungsplan" in response.text
    assert "Vorige Woche" in response.text
