"""Organization-aware booking assignment without expanding booking-data permissions."""
import json
import secrets
from datetime import datetime, time, timedelta

from app import bookings, btypes
from app.db import Booking, BookingHours, BookingPage, BookingType, Organization, to_local, utcnow
from app.org_models import OrgMembership
from test_native_tasks import task_people


def test_assignment_resolves_organization_tree_and_respects_staff_capacity(db, task_people):
    first, second, outsider = task_people[:3]
    root = Organization(name="Fachbereich", kind="department", active=True)
    child = Organization(name="Bürgerbüro", kind="department", parent=root, active=True)
    db.add_all([root, child])
    db.flush()
    entries = [
        OrgMembership(org_id=root.id, user_id=first.id, counts_staff=True, capacity_percent=100),
        OrgMembership(org_id=child.id, user_id=second.id, counts_staff=True, capacity_percent=50),
        OrgMembership(org_id=root.id, user_id=outsider.id, counts_staff=False, capacity_percent=100),
    ]
    db.add_all(entries)
    page = BookingPage(owner_id=first.id, title="Org-Sprechstunde",
                       public_token=secrets.token_hex(20), extended=True,
                       holidays_closed=False, days_ahead=30)
    db.add(page)
    db.flush()
    bt = BookingType(page_id=page.id, name="Anmeldung", duration_minutes=30,
                     min_notice_hours=0, routing_json=json.dumps({
                         "mode": "organization", "org_id": root.id, "include_children": True,
                     }))
    db.add(bt)
    db.flush()
    try:
        resolved = btypes.providers_for(db, bt)
        assert {u.id for u in resolved} == {first.id, second.id}
        assert btypes.provider_capacity(db, bt) == {first.id: 100, second.id: 50}
        assert bt in btypes.active_types(page, db)
        assert {p.id for p in btypes.all_providers(page, db)} == {first.id, second.id}

        day = to_local(utcnow()).date() + timedelta(days=9)
        for uid in (first.id, second.id):
            db.add(BookingHours(page_id=page.id, user_id=uid,
                                weekday=day.weekday(), start="09:00", end="10:30"))
        db.flush()
        slot = next(s for s in btypes.slots(db, page, bt, until=day)
                    if to_local(s["start"]).date() == day)
        assert set(slot["providers"]) == {first.id, second.id}

        bt.routing_json = json.dumps({"mode": "organization", "org_id": root.id,
                                      "include_children": False})
        db.flush()
        assert [u.id for u in btypes.providers_for(db, bt)] == [first.id]

        bt.routing_json = json.dumps({"mode": "mixed", "org_id": child.id,
                                      "include_children": False})
        bt.providers = [first]
        db.flush()
        assert {u.id for u in btypes.providers_for(db, bt)} == {first.id, second.id}

        bt.routing_json = json.dumps({"mode": "manual"})
        db.flush()
        assert [u.id for u in btypes.providers_for(db, bt)] == [first.id]
        assert btypes.provider_capacity(db, bt) == {}
    finally:
        db.rollback()
        for entry in entries:
            db.delete(entry)
        db.delete(bt)
        db.delete(page)
        db.flush()
        db.delete(child)
        db.delete(root)
        db.commit()


def test_weighted_fair_routing_prefers_normalized_capacity(db, task_people):
    full, half = task_people[:2]
    page = BookingPage(owner_id=full.id, title="Auslastung",
                       public_token=secrets.token_hex(20))
    db.add(page)
    db.flush()
    start = bookings.to_utc(datetime.combine(to_local(utcnow()).date() + timedelta(days=9), time(9)))
    # 30 minutes at full-time versus 20 minutes at half-time:
    # 30/100% < 20/50%, so full-time employee has more remaining capacity.
    items = [
        Booking(page_id=page.id, provider_id=full.id, status="booked",
                starts_at=start, ends_at=start + timedelta(minutes=30),
                name="A", email="a@example.org", token=secrets.token_hex(20)),
        Booking(page_id=page.id, provider_id=half.id, status="booked",
                starts_at=start, ends_at=start + timedelta(minutes=20),
                name="B", email="b@example.org", token=secrets.token_hex(20)),
    ]
    db.add_all(items)
    db.flush()
    try:
        selected = btypes.pick_provider(db, [half.id, full.id], start + timedelta(hours=1),
                                       capacity={full.id: 100, half.id: 50})
        assert selected == full.id
        assert btypes.pick_provider(db, [half.id, full.id], start + timedelta(hours=1)) == half.id
    finally:
        db.rollback()
        db.delete(page)
        db.commit()
