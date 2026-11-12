"""Cross-module appointment closing days: creator unit, ancestry, opt-out, and disabled-module fallbacks."""
import json
import secrets
from datetime import timedelta

from app import booking_integration, btypes
from app.db import (
    BookingHours, BookingPage, BookingType, Organization,
    get_settings, to_local, utcnow,
)
from app.leave_extensions import Closure
from app.org_models import OrgMembership
from conftest import settings
from test_native_tasks import task_people


def test_creator_org_closures_block_speaking_hours_but_can_be_disabled(db, task_people):
    owner, new_owner = task_people[:2]
    original = get_settings(db).get("module_calendars", "1")
    settings(module_calendars="1")
    tag = secrets.token_hex(5)
    root = Organization(name="Verwaltung " + tag, kind="department", active=True)
    child = Organization(name="Bürgerbüro " + tag, kind="department", parent=root, active=True)
    unrelated = Organization(name="Unbeteiligt " + tag, kind="department", active=True)
    db.add_all([root, child, unrelated])
    db.flush()
    membership = OrgMembership(user_id=owner.id, org_id=child.id, is_primary=True, counts_staff=True)
    db.add(membership)
    day = to_local(utcnow()).date() + timedelta(days=10)
    unrelated_day = day + timedelta(days=1)
    page = BookingPage(
        owner_id=owner.id, title="Beratung", public_token=secrets.token_hex(12),
        extended=True, days_ahead=20, holidays_closed=False,
        integration_json=json.dumps({"creator_org_id": child.id, "org_closures": True}),
    )
    db.add(page)
    db.flush()
    bt = BookingType(page_id=page.id, name="Beratung 30 Minuten",
                     duration_minutes=30, min_notice_hours=0)
    bt.providers.append(owner)
    page.types.append(bt)
    page.hours.append(BookingHours(
        page_id=page.id, user_id=owner.id, weekday=day.weekday(),
        start="09:00", end="12:00",
    ))
    closed = Closure(
        org_id=root.id, title="Verwaltungsweiter Schließtag",
        starts_on=day.isoformat(), ends_on=day.isoformat(),
    )
    sibling = Closure(
        org_id=unrelated.id, title="Andere Verwaltung schließt",
        starts_on=unrelated_day.isoformat(), ends_on=unrelated_day.isoformat(),
    )
    db.add_all([closed, sibling])
    db.commit()
    def day_slots():
        return [entry for entry in btypes.slots(db, page, bt, until=day)
                if to_local(entry["start"]).date() == day]
    try:
        assert booking_integration.creator_org_id(db, page) == child.id
        assert booking_integration.creator_closure_days(db, page, day, day) == {day}
        assert booking_integration.creator_closure_days(db, page, unrelated_day, unrelated_day) == set()
        assert day_slots() == []

        # Retargeting the page owner never switches the original creator unit.
        page.owner_id = new_owner.id
        db.flush()
        assert booking_integration.creator_org_id(db, page) == child.id
        assert day_slots() == []

        page.integration_json = json.dumps({"creator_org_id": child.id, "org_closures": False})
        db.flush()
        assert booking_integration.creator_closure_days(db, page, day, day) == set()
        assert day_slots()

        page.integration_json = json.dumps({"creator_org_id": child.id, "org_closures": True})
        db.flush()
        settings(module_calendars="0")
        assert booking_integration.creator_closure_days(db, page, day, day) == set()
        assert booking_integration.internal_busy(
            db, owner.id, utcnow(), utcnow() + timedelta(hours=1)
        ) == []
        assert day_slots()
    finally:
        db.delete(page)
        db.flush()
        db.delete(membership)
        db.delete(closed)
        db.delete(sibling)
        db.flush()
        db.delete(child)
        db.delete(unrelated)
        db.flush()
        db.delete(root)
        db.commit()
        settings(module_calendars=original)


def test_old_booking_page_resolves_primary_unit_and_no_unit_is_safe(db, task_people):
    owner, other = task_people[:2]
    tag = secrets.token_hex(5)
    unit = Organization(name="Abteilung " + tag, active=True)
    db.add(unit)
    db.flush()
    membership = OrgMembership(user_id=owner.id, org_id=unit.id, is_primary=True, counts_staff=True)
    db.add(membership)
    db.flush()
    old_page = BookingPage(
        owner_id=owner.id, title="Altbestand", public_token=secrets.token_hex(14),
        integration_json="{}",
    )
    independent = BookingPage(
        owner_id=other.id, title="Ohne Organisation", public_token=secrets.token_hex(14),
        integration_json="{}",
    )
    try:
        assert booking_integration.creator_org_id(db, old_page) == unit.id
        assert booking_integration.creator_org_id(db, independent) is None
        assert booking_integration.creator_closure_days(
            db, independent, to_local(utcnow()).date(),
            to_local(utcnow()).date() + timedelta(days=7)
        ) == set()
    finally:
        db.delete(membership)
        db.flush()
        db.delete(unit)
        db.commit()
