"""Regression: booking notifications, privacy projections and cross-calendar availability."""
import json
import secrets
from datetime import datetime, date, time, timedelta, timezone

from sqlalchemy import select

from app import booking_integration, bookings, calendar_sources, notify
from app.calendar_models import Calendar, CalendarEvent
from app.db import Booking, BookingPage, BookingType, BookingWindow, get_settings, to_local, utcnow
from conftest import login, settings
from test_native_tasks import task_people


def _range():
    a = datetime(2026, 11, 1, tzinfo=timezone.utc)
    b = datetime(2027, 6, 1, tzinfo=timezone.utc)
    return a, b


def test_assigned_booking_visible_only_to_staff_and_external_feeds_anonymous(db, task_people):
    owner, provider, stranger = task_people[:3]
    previous = get_settings(db)
    settings(module_bookings="1", module_calendars="1")
    token = secrets.token_hex(12)
    page = BookingPage(owner_id=owner.id, title="Bürgerbüro", public_token=token)
    db.add(page)
    db.flush()
    bt = BookingType(page_id=page.id, name="Bauberatung", privacy_mode="inherit")
    db.add(bt)
    db.flush()
    booking = Booking(page_id=page.id, type_id=bt.id, provider_id=provider.id,
                      starts_at=datetime(2027, 1, 5, 9),
                      ends_at=datetime(2027, 1, 5, 10),
                      name="Erika Vertraulich", email="private@example.org",
                      token=secrets.token_hex(18), status="requested")
    db.add(booking)
    db.commit()
    start, end = _range()
    try:
        mine = calendar_sources.project(db, provider, "bookings", start, end)
        assert len(mine) == 1 and "Erika Vertraulich" in mine[0]["title"]
        assert mine[0]["extendedProps"]["status"] == "requested"
        assert mine[0]["extendedProps"]["url"] == f"/kalender/buchungen/{booking.id}"
        assert calendar_sources.project(db, stranger, "bookings", start, end) == []

        c = login(provider.email, "task-passwort-123")
        detail = c.get(f"/kalender/buchungen/{booking.id}")
        assert detail.status_code == 200 and "Erika Vertraulich" in detail.text
        not_allowed = login(stranger.email, "task-passwort-123")
        assert not_allowed.get(f"/kalender/buchungen/{booking.id}").status_code == 404

        external = calendar_sources.project(db, provider, "bookings", start, end, channel="caldav")
        assert external[0]["title"] == "Bürgertermin (belegt)"
        feed = calendar_sources.to_ics(external, "Buchungen")
        assert "private@example.org" not in feed
        assert "Erika Vertraulich" not in feed
        assert "TENTATIVE" in feed
        assert "/b/m/" not in feed

        bt.privacy_mode = "busy"
        db.commit()
        mine = calendar_sources.project(db, provider, "bookings", start, end)
        assert mine[0]["title"].endswith("Bürgertermin (belegt)")
        assert "Erika Vertraulich" not in mine[0]["title"]

        booking.status = "cancelled"
        db.commit()
        assert not calendar_sources.project(db, provider, "bookings", start, end)
    finally:
        db.delete(booking)
        db.delete(bt)
        db.delete(page)
        db.commit()
        settings(module_bookings=previous.get("module_bookings", "1"),
                 module_calendars=previous.get("module_calendars", "0"))


def test_opt_in_private_calendar_prevents_simple_double_booking(db, task_people):
    owner = task_people[0]
    token = secrets.token_hex(12)
    local_day = to_local(utcnow()).date() + timedelta(days=8)
    begin = bookings.to_utc(datetime.combine(local_day, time(9)))
    end = begin + timedelta(hours=2)
    page = BookingPage(owner_id=owner.id, title="Konfliktprüfung", public_token=token,
                       min_notice_hours=0, slot_minutes=30,
                       integration_json=json.dumps({"calendar_conflicts": True,
                                                    "conflict_sources": ["personal"]}))
    db.add(page)
    db.flush()
    db.add(BookingWindow(page_id=page.id, starts_at=begin, ends_at=end))
    personal = Calendar(owner_id=owner.id, title="Mein Kalender", source="free", visibility="private")
    db.add(personal)
    db.flush()
    busy_start = begin + timedelta(minutes=30)
    busy_end = busy_start + timedelta(minutes=30)
    event = CalendarEvent(
        calendar_id=personal.id, uid=secrets.token_hex(12),
        title="Vertrauliche persönliche Besprechung",
        starts_at=busy_start.replace(tzinfo=timezone.utc).isoformat(),
        ends_at=busy_end.replace(tzinfo=timezone.utc).isoformat(),
    )
    db.add(event)
    db.commit()
    try:
        starts = [s["start"] for s in bookings.bookable(page, db=db)]
        assert starts == [begin, begin + timedelta(hours=1), begin + timedelta(minutes=90)]
        slot, error = bookings.check(page, busy_start, "a@example.org", db=db)
        assert slot is None and "nicht mehr frei" in error

        event.ical_data = ""  # no recurrence, normal opaque event
        page.integration_json = json.dumps({"calendar_conflicts": False})
        db.commit()
        assert len(bookings.bookable(page, db=db)) == 4
    finally:
        db.delete(event)
        db.delete(personal)
        db.delete(page)
        db.commit()


def test_booking_html_mail_styled_and_user_data_escaped():
    cfg = {"mail_from": "portal@example.org", "smtp_host": "smtp.example.org",
           "ui_mail_frame": "1"}
    msg = notify._build(
        cfg, "gast@example.org", "Termin bestätigt",
        "Guten Tag Erika,\n\nIhr Termin ist bestätigt.\n\n"
        "TERMINÜBERSICHT\nAnliegen: Bauberatung\nDatum: 17.11.2026\nUhrzeit: 10:00–10:45 Uhr\n"
        "Ort: <img src=x onerror=alert(1)>\n\n"
        "Termin ansehen:\nhttps://portal.example.org/b/m/private\n\nViele Grüße",
        kind="booking_confirm")
    html = next(p for p in msg.walk() if p.get_content_type() == "text/html").get_content()
    text = next(p for p in msg.walk() if p.get_content_type() == "text/plain").get_content()
    assert "Termin bestätigt" in html and "Bauberatung" in html
    assert '<table role="presentation"' in html
    assert 'href="https://portal.example.org/b/m/private"' in html
    assert "<img src=x onerror=" not in html
    assert "&lt;img src=x" in html
    assert "TERMINÜBERSICHT" in text
