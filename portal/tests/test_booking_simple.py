"""Regressionen für einfache Terminbuchung: Fenster -> buchbare Slots -> Buchung -> Sperre."""

import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app import bookings as bk
from app.db import Booking, BookingPage, SessionLocal, User, to_local, utcnow
from conftest import client, csrf_of, login, settings


TITLE = "Einfache Slot Regression"
ADMIN = ("admin@example.org", "admin-passwort-123")


@pytest.fixture(autouse=True)
def setup_booking():
    settings(module_bookings="1", smtp_host="smtp.example.org", mail_from="portal@example.org")
    with SessionLocal() as db:
        db.execute(delete(BookingPage).where(BookingPage.title == TITLE))
        db.commit()
    yield
    settings(smtp_host="", mail_from="")


def make_page(slot_minutes=30, pause_minutes=0, capacity=1) -> tuple[int, str]:
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == ADMIN[0]))
        page = BookingPage(title=TITLE, owner_id=owner.id, public_token="reg-simple-slot-page",
                           slot_minutes=slot_minutes, pause_minutes=pause_minutes,
                           min_notice_hours=0, capacity=capacity, max_per_person=5)
        db.add(page)
        db.commit()
        return page.id, page.public_token


def future_day():
    return to_local(utcnow()).date() + timedelta(days=2)


def test_simple_window_generates_publicly_bookable_slots_and_updates_preview():
    page_id, token = make_page(slot_minutes=30, pause_minutes=15)
    admin = login(*ADMIN)
    day = future_day()
    detail = admin.get(f"/bookings/{page_id}")
    assert detail.status_code == 200
    assert "Zurzeit keine buchbaren Termine" in detail.text
    response = admin.post(f"/bookings/{page_id}/windows", data={
        "csrf": csrf_of(detail.text), "date": day.isoformat(), "from": "09:00", "to": "11:00"
    })
    assert response.status_code == 303
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        slots = bk.bookable(page)
        assert [to_local(s["start"]).strftime("%H:%M") for s in slots] == ["09:00", "09:45", "10:30"]
        assert all(s["free"] == 1 for s in slots)
        chosen = slots[0]["start"].isoformat() + "+00:00"
        assert len(page.windows) == 1
    detail = admin.get(f"/bookings/{page_id}")
    assert "Nächste buchbare Termine" in detail.text and "bk-time-chip" in detail.text
    assert "09:00" in detail.text and "freie Plätze" in detail.text
    public = client()
    html = public.get(f"/b/{token}").text
    assert len(re.findall(r'name="slot" id="s-', html)) == 3
    payload = {"csrf": csrf_of(html), "slot": chosen, "name": "Gast Eins", "email": "gast1@example.org"}
    first = public.post(f"/b/{token}", data=payload)
    assert first.status_code == 303 and "/b/m/" in first.headers["location"]
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        assert len([b for b in page.bookings if b.status == "booked"]) == 1
        assert [to_local(s["start"]).strftime("%H:%M") for s in bk.bookable(page)] == ["09:45", "10:30"]
    public = client()
    html = public.get(f"/b/{token}").text
    assert len(re.findall(r'name="slot" id="s-', html)) == 2
    second = public.post(f"/b/{token}", data={
        "csrf": csrf_of(html), "slot": chosen, "name": "Gast Zwei", "email": "gast2@example.org"
    })
    assert second.status_code == 303 and "/b/m/" not in second.headers["location"]
    with SessionLocal() as db:
        assert db.scalar(select(Booking).where(Booking.email == "gast2@example.org")) is None


def test_simple_slots_block_overlapping_old_bookings_when_duration_changes():
    page_id, _ = make_page(slot_minutes=30)
    day = future_day()
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        start = bk.to_utc(datetime.combine(day, datetime.min.time()).replace(hour=9))
        assert bk.add_window(db, page, start, start + timedelta(hours=2)) == ""
        db.add(Booking(page_id=page_id, starts_at=start + timedelta(minutes=30),
                       ends_at=start + timedelta(hours=1), name="Bestehender Termin",
                       email="old@example.org", token="simple-overlap-old"))
        page.slot_minutes = 60
        db.commit()
        result = bk.slots(page)
        assert [(to_local(s["start"]).strftime("%H:%M"), s["free"]) for s in result] == [
            ("09:00", 0), ("10:00", 1)
        ]
        assert [to_local(s["start"]).strftime("%H:%M") for s in bk.bookable(page)] == ["10:00"]


def test_simple_capacity_requested_bookings_and_rescheduling_exclusion():
    page_id, _ = make_page(slot_minutes=30, capacity=2)
    day = future_day()
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        start = bk.to_utc(datetime.combine(day, datetime.min.time()).replace(hour=9))
        bk.add_window(db, page, start, start + timedelta(hours=1))
        a = Booking(page_id=page_id, starts_at=start, ends_at=start + timedelta(minutes=30),
                    name="Anfrage", email="a@example.org", token="simple-cap-request",
                    status="requested")
        b = Booking(page_id=page_id, starts_at=start, ends_at=start + timedelta(minutes=30),
                    name="Gebucht", email="b@example.org", token="simple-cap-book")
        db.add_all([a, b])
        db.commit()
        assert [s["free"] for s in bk.slots(page)] == [0, 2]
        assert [to_local(s["start"]).strftime("%H:%M") for s in bk.bookable(page)] == ["09:30"]
        keep = bk.bookable(page, keep=a)
        assert keep[0]["start"] == start and keep[0]["free"] == 1


def test_weekly_window_repeats_in_local_time_across_dst():
    page_id, _ = make_page()
    admin = login(*ADMIN)
    html = admin.get(f"/bookings/{page_id}").text
    # 2027-03-28 ist die Umstellung auf die Sommerzeit in Europe/Berlin.
    response = admin.post(f"/bookings/{page_id}/windows", data={
        "csrf": csrf_of(html), "date": "2027-03-21", "from": "09:00", "to": "10:00", "repeat_weeks": "1"
    })
    assert response.status_code == 303
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        assert len(page.windows) == 2
        assert [to_local(w.starts_at).strftime("%Y-%m-%d %H:%M") for w in page.windows] == [
            "2027-03-21 09:00", "2027-03-28 09:00"
        ]


def test_ajax_window_add_and_delete_refresh_slots_without_navigation():
    page_id, _ = make_page(slot_minutes=30)
    admin = login(*ADMIN)
    day = future_day()
    html = admin.get(f"/bookings/{page_id}").text
    csrf = csrf_of(html)
    headers = {"X-Requested-With": "fetch"}
    added = admin.post(f"/bookings/{page_id}/windows", headers=headers, data={
        "csrf": csrf, "date": day.isoformat(), "from": "09:00", "to": "10:00"
    })
    assert added.status_code == 200
    assert added.headers["content-type"].startswith("application/json")
    response = added.json()
    assert response["ok"]
    assert response["availability"]["window_count"] == 1
    assert response["availability"]["slot_count"] == 2
    assert response["availability"]["free_count"] == 2
    assert response["availability"]["days"][0]["slots"] == [
        {"time": "09:00", "free": 1}, {"time": "09:30", "free": 1}
    ]
    window = next(e for e in response["events"] if e["extendedProps"]["kind"] == "window")

    removed = admin.post(f"/bookings/{page_id}/windows/{window['extendedProps']['wid']}/delete",
                         headers=headers, data={"csrf": csrf})
    assert removed.status_code == 200
    assert removed.json()["availability"] == {
        "free_count": 0, "slot_count": 0, "window_count": 0, "days": []
    }
    assert removed.json()["events"] == []


def test_ajax_repeated_windows_and_clear_refresh_preview():
    page_id, _ = make_page(slot_minutes=30)
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get(f"/bookings/{page_id}").text)
    headers = {"X-Requested-With": "fetch"}
    added = admin.post(f"/bookings/{page_id}/windows", headers=headers, data={
        "csrf": csrf, "date": future_day().isoformat(), "from": "09:00",
        "to": "10:00", "repeat_weeks": "1"
    })
    assert added.status_code == 200
    info = added.json()["availability"]
    assert info["window_count"] == 2
    assert info["slot_count"] == 4
    assert info["free_count"] == 4
    assert len(info["days"]) == 2
    cleared = admin.post(f"/bookings/{page_id}/windows/clear", headers=headers, data={"csrf": csrf})
    assert cleared.status_code == 200
    assert cleared.json()["availability"]["window_count"] == 0
    assert cleared.json()["availability"]["days"] == []


def test_booking_calendar_has_no_automatic_hash_jump_or_reload():
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "app"
    script = (base / "static" / "booking-calendar.js").read_text()
    template = (base / "templates" / "booking.html").read_text()
    assert "window.location.hash =" not in script
    assert "window.location.reload()" not in script
    assert "updateAvailability(data.availability)" in script
    assert 'id="bk-availability-content"' in template
    assert "data-bk-window-form" in template
    assert "</div>\n{% endblock %}\n{% block scripts %}" in template
