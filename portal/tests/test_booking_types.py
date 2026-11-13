"""Terminbuchung im erweiterten Umfang: Terminarten mit Dauer/Puffer/Vorlauf, mehrere Mitarbeitende mit
Sprechzeiten, Ausnahmen, Feiertage, Abwesenheiten, Verteilung, Bestätigung durch Mitarbeitende, Bürgersicht."""

import re
from urllib.parse import quote
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app import btypes
from app.db import (
    Absence, Booking, BookingHours, BookingPage, BookingType, Notification, SessionLocal, User, to_local, utcnow,
)
from app.security import hash_password

from conftest import client, csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")


def staff(email: str, name: str) -> int:
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        if u is None:
            u = User(email=email, name=name, password_hash=hash_password("staff-passwort-1"), permissions="bookings")
            db.add(u)
        u.active = True
        db.commit()
        return u.id


@pytest.fixture(autouse=True)
def setup():
    settings(module_bookings="1", smtp_host="smtp.example.org", mail_from="portal@example.org")
    with SessionLocal() as db:
        db.execute(delete(BookingPage).where(BookingPage.title == "Bürgerbüro Termine"))
        db.execute(delete(Absence))
        db.execute(delete(Notification))
        db.commit()
    yield
    settings(smtp_host="", mail_from="")


def make_page(approval=False, choose=False) -> tuple[int, int, int, int, int]:
    """Seite mit zwei Terminarten; Anna und Ben bieten Mo–So 08–12 Uhr an."""
    anna, ben = staff("anna.bt@example.org", "Anna Beratung"), staff("ben.bt@example.org", "Ben Beratung")
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == ADMIN[0]))
        page = BookingPage(title="Bürgerbüro Termine", owner_id=admin.id, public_token="bt-buergerbuero-token-123",
                           extended=True, step_minutes=30, days_ahead=14, holidays_closed=False, max_per_person=5)
        db.add(page)
        db.flush()
        a = BookingType(page_id=page.id, name="Bauberatung", duration_minutes=60, buffer_minutes=30, min_notice_hours=0,
                        approval=approval, choose_provider=choose, docs_hint="Lageplan mitbringen", phone_mode="required")
        b = BookingType(page_id=page.id, name="Gewerbeanmeldung", duration_minutes=15, min_notice_hours=0, position=1)
        db.add_all([a, b])
        db.flush()
        a.providers = [db.get(User, anna), db.get(User, ben)]
        b.providers = [db.get(User, anna)]
        for uid in (anna, ben):
            for wd in range(7):
                db.add(BookingHours(page_id=page.id, user_id=uid, weekday=wd, start="08:00", end="12:00"))
        db.commit()
        return page.id, a.id, b.id, anna, ben


def tomorrow() -> date:
    return to_local(utcnow()).date() + timedelta(days=1)


def day_slots(slots, d):
    return [s for s in slots if to_local(s["start"]).date() == d]


def test_slots_closures_absence_and_buffer():
    page_id, a_id, b_id, anna, ben = make_page()
    with SessionLocal() as db:
        page, a = db.get(BookingPage, page_id), db.get(BookingType, a_id)
        d = tomorrow()
        slots = day_slots(btypes.slots(db, page, a), d)
        assert [to_local(s["start"]).strftime("%H:%M") for s in slots] == ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00"]
        assert all(sorted(s["providers"]) == sorted([anna, ben]) for s in slots)
        # Ausnahme für Anna an dem Tag, Abwesenheit von Ben → keine Termine
        from app.db import BookingClosure
        db.add(BookingClosure(page_id=page.id, user_id=anna, date_from=d.isoformat(), date_to=d.isoformat()))
        db.add(Absence(user_id=ben, starts_on=d.isoformat(), ends_on=d.isoformat(), status="confirmed"))
        db.commit()
        db.refresh(page)
        assert day_slots(btypes.slots(db, page, a), d) == []
        db.execute(delete(Absence))
        db.commit()
        # Ben bucht 09:00–10:00 + 30 Min. Puffer → 08:00 (endet 9:00 + Puffer) und 08:30…10:00 nicht mehr bei Ben
        ben_slots = day_slots(btypes.slots(db, page, a, ben), d)
        start = next(s for s in ben_slots if to_local(s["start"]).strftime("%H:%M") == "09:00")["start"]
        db.add(Booking(page_id=page.id, type_id=a.id, provider_id=ben, starts_at=start, ends_at=start + timedelta(hours=1),
                       name="X", email="x@example.org", token="bt-token-x-1"))
        db.commit()
        free = [to_local(s["start"]).strftime("%H:%M") for s in day_slots(btypes.slots(db, page, a, ben), d)]
        assert free == ["10:30", "11:00"]


def test_public_flow_distribution_and_mails():
    page_id, a_id, b_id, anna, ben = make_page()
    c = client()
    html = c.get("/b/bt-buergerbuero-token-123").text
    assert "Worum geht es?" in html and "Bauberatung" in html and "Gewerbeanmeldung" in html
    html = c.get(f"/b/bt-buergerbuero-token-123?art={a_id}").text
    assert 'name="art"' in html and "Weiter zu Ihren Angaben" in html
    slot = re.search(r'name="slot" id="s-1-[^"]+" value="([^"]+)"', html).group(1)
    details = c.get(f"/b/bt-buergerbuero-token-123?art={a_id}&step=details&slot={quote(slot, safe='')}").text
    assert "Lageplan mitbringen" in details and "Ihre Angaben" in details
    data = {"csrf": csrf_of(details), "art": str(a_id), "slot": slot, "name": "Bürger Eins", "email": "eins@example.org"}
    r = c.post("/b/bt-buergerbuero-token-123", data=data, follow_redirects=True)
    assert "Telefonnummer" in r.text                               # Telefon ist bei dieser Art Pflicht
    r = c.post("/b/bt-buergerbuero-token-123", data={**data, "phone": "0631 1"}, follow_redirects=False)
    assert r.status_code == 303 and "/b/m/" in r.headers["location"]
    r2 = c.post("/b/bt-buergerbuero-token-123", data={**data, "csrf": csrf_of(html), "phone": "0631 2", "name": "Bürger Zwei",
                                                       "email": "zwei@example.org"}, follow_redirects=False)
    assert r2.status_code == 303
    with SessionLocal() as db:
        rows = db.scalars(select(Booking).where(Booking.page_id == page_id).order_by(Booking.id)).all()
        assert [b.status for b in rows] == ["booked", "booked"]
        assert {rows[0].provider_id, rows[1].provider_id} == {anna, ben}          # gleicher Beginn → zwei Personen
        mails = db.scalars(select(Notification)).all()
        guest = next(m for m in mails if m.to_addr == "eins@example.org")
        assert "Bauberatung" in guest.subject and "Lageplan" in guest.body and guest.attachments_json
        assert any(m.to_addr in ("anna.bt@example.org", "ben.bt@example.org") and m.kind == "booking_owner" for m in mails)
    # dritter Gast zur selben Zeit: niemand mehr frei
    r3 = c.post("/b/bt-buergerbuero-token-123", data={**data, "phone": "1", "name": "Drei", "email": "drei@example.org"},
                follow_redirects=True)
    assert "nicht mehr frei" in r3.text


def test_approval_flow_and_management_page():
    page_id, a_id, b_id, anna, ben = make_page(approval=True, choose=True)
    c = client()
    html = c.get(f"/b/bt-buergerbuero-token-123?art={a_id}&person={ben}").text
    assert "Ansprechperson" in html and "Weiter zu Ihren Angaben" in html
    slot = re.search(r'name="slot" id="s-1-[^"]+" value="([^"]+)"', html).group(1)
    details = c.get(f"/b/bt-buergerbuero-token-123?art={a_id}&person={ben}&step=details&slot={quote(slot, safe='')}").text
    assert "Termin anfragen" in details and f'name="person" value="{ben}"' in details
    r = c.post("/b/bt-buergerbuero-token-123", data={"csrf": csrf_of(html), "art": str(a_id), "person": str(ben),
                                                     "slot": slot, "name": "Anfrage", "email": "anfrage@example.org",
                                                     "phone": "1"})
    manage = c.get(r.headers["location"]).text
    assert "wartet auf Bestätigung" in manage
    with SessionLocal() as db:
        b = db.scalar(select(Booking).where(Booking.email == "anfrage@example.org"))
        assert b.status == "requested" and b.provider_id == ben
        assert db.scalar(select(Notification).where(Notification.kind == "booking_requested")).attachments_json is None
    admin = login(*ADMIN)
    page = admin.get(f"/bookings/{page_id}")
    assert "angefragt" in page.text and 'value="confirm"' in page.text and "Terminarten" in page.text
    admin.post(f"/bookings/{page_id}/entries/{b.id}", data={"csrf": csrf_of(page.text), "action": "confirm"})
    with SessionLocal() as db:
        assert db.get(Booking, b.id).status == "booked"
        assert db.scalar(select(Notification).where(Notification.kind == "booking_confirm",
                                                    Notification.to_addr == "anfrage@example.org")) is not None
    # Verwaltung: Terminart anlegen, Sprechzeit eintragen
    mg = admin.get(f"/bookings/{page_id}/arten")
    assert mg.status_code == 200 and "Sprechzeiten (wöchentlich)" in mg.text
    admin.post(f"/bookings/{page_id}/arten", data={"csrf": csrf_of(mg.text), "name": "Fundsachen", "duration_minutes": "15",
                                                   "providers": [str(anna)], "phone_mode": "none", "active": "1"})
    admin.post(f"/bookings/{page_id}/sprechzeiten", data={"csrf": csrf_of(mg.text), "user_id": str(anna), "start": "14:00",
                                                          "end": "16:00", "weekday": ["0", "2"]})
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        assert any(t.name == "Fundsachen" for t in page.types)
        assert sum(1 for h in page.hours if h.start == "14:00") == 2



def test_custom_fields_validation_mail_and_export():
    page_id, a_id, b_id, anna, ben = make_page()
    admin = login(*ADMIN)
    mg = admin.get(f"/bookings/{page_id}/arten")
    admin.post(f"/bookings/{page_id}/arten", data={
        "csrf": csrf_of(mg.text), "type_id": str(b_id), "name": "Gewerbeanmeldung", "duration_minutes": "15",
        "providers": [str(anna)], "phone_mode": "none", "active": "1",
        "f_label": ["Art des Gewerbes", "Rechtsform", "", "Beginn"], "f_kind": ["text", "select", "text", "date"],
        "f_options": ["", "Einzelunternehmen; GmbH", "", ""], "f_help": ["", "", "", ""], "f_required": ["0", "1"]})
    with SessionLocal() as db:
        fields = btypes.fields(db.get(BookingType, b_id))
    assert [f["label"] for f in fields] == ["Art des Gewerbes", "Rechtsform", "Beginn"]
    assert fields[1]["options"] == ["Einzelunternehmen", "GmbH"] and fields[0]["required"] and not fields[2]["required"]
    c = client()
    html = c.get(f"/b/bt-buergerbuero-token-123?art={b_id}").text
    assert 'name="q_f2"' not in html
    slot = re.search(r'name="slot" id="s-1-[^"]+" value="([^"]+)"', html).group(1)
    details = c.get(f"/b/bt-buergerbuero-token-123?art={b_id}&step=details&slot={quote(slot, safe='')}").text
    assert 'name="q_f2"' in details and "<option>GmbH</option>" in details
    base = {"csrf": csrf_of(details), "art": str(b_id), "slot": slot, "name": "Gewerbe", "email": "gew@example.org"}
    bad = c.post("/b/bt-buergerbuero-token-123", data={**base, "q_f1": "Bäckerei", "q_f2": "AG"}, follow_redirects=True)
    assert "aus der Liste" in bad.text
    ok = c.post("/b/bt-buergerbuero-token-123", data={**base, "q_f1": "Bäckerei", "q_f2": "GmbH", "q_f3": "2026-11-01"})
    assert ok.status_code == 303 and "/b/m/" in ok.headers["location"]
    with SessionLocal() as db:
        b = db.scalar(select(Booking).where(Booking.email == "gew@example.org"))
        assert btypes.answers_text(b) == "Art des Gewerbes: Bäckerei\nRechtsform: GmbH\nBeginn: 01.11.2026"
        mail = db.scalar(select(Notification).where(Notification.kind == "booking_owner",
                                                    Notification.to_addr == "anna.bt@example.org"))
        assert "Rechtsform: GmbH" in mail.body
    detail = admin.get(f"/bookings/{page_id}").text
    assert "Rechtsform:" in detail
    csv = admin.get(f"/bookings/{page_id}/export.csv?status=all").text
    assert "Gewerbeanmeldung" in csv and "Rechtsform: GmbH" in csv


def test_extended_horizon_cannot_be_bypassed_by_direct_booking():
    page_id, a_id, b_id, anna, ben = make_page()
    from datetime import datetime, time
    from app import bookings as bk
    with SessionLocal() as db:
        page, bt = db.get(BookingPage, page_id), db.get(BookingType, b_id)
        page.days_ahead = 2
        db.commit()
        far_day = tomorrow() + timedelta(days=7)
        far_start = bk.to_utc(datetime.combine(far_day, time(9, 0)))
        slot, error = btypes.check(db, page, bt, far_start)
        assert slot is None and "außerhalb" in error
        near_start = bk.to_utc(datetime.combine(tomorrow(), time(9, 0)))
        slot, error = btypes.check(db, page, bt, near_start)
        assert not error and slot is not None


def test_extended_shared_provider_conflicts_across_types_and_requests():
    page_id, a_id, b_id, anna, ben = make_page(approval=True)
    with SessionLocal() as db:
        page = db.get(BookingPage, page_id)
        a, b = db.get(BookingType, a_id), db.get(BookingType, b_id)
        d = tomorrow()
        start = next(s["start"] for s in day_slots(btypes.slots(db, page, a, anna), d)
                     if to_local(s["start"]).strftime("%H:%M") == "09:00")
        db.add(Booking(page_id=page_id, type_id=a_id, provider_id=anna, starts_at=start,
                       ends_at=start + timedelta(hours=1), name="Anfrage",
                       email="wait@example.org", token="bt-cross-type-request",
                       status="requested"))
        db.commit()
        # Auch eine noch nicht bestätigte 60-Minuten-Anfrage blockiert Anna
        # für 15-Minuten-Termine einer anderen Terminart plus 30 Minuten Puffer.
        times = [to_local(s["start"]).strftime("%H:%M")
                 for s in day_slots(btypes.slots(db, page, b, anna), d)]
        assert "08:30" in times and "09:00" not in times
        assert "10:15" not in times and "10:30" in times
        # Der andere Anbieter bleibt für die erste Terminart verfügbar.
        available = next(s for s in day_slots(btypes.slots(db, page, a), d)
                         if s["start"] == start)
        assert available["providers"] == [ben]


def test_extended_pages_report_availability_in_management_list():
    page_id, a_id, b_id, anna, ben = make_page()
    admin = login(*ADMIN)
    html = admin.get("/bookings").text
    match = re.search(r'Bürgerbüro Termine.*?Optionen', html, re.S)
    assert match is not None
    with SessionLocal() as db:
        from app import bookings as bk
        page = db.get(BookingPage, page_id)
        assert sum(s["free"] for s in bk.free_slots(db, page)) > 0
    assert "buchbar" in html


def test_public_wizard_shows_one_day_and_paginates_available_days():
    page_id, a_id, _, _, _ = make_page()
    c = client()
    base = "/b/bt-buergerbuero-token-123"
    choose = c.get(base).text
    assert "Worum geht es?" in choose and 'data-booking-type=' in choose
    assert 'name="slot"' not in choose

    # Exercise a complete future service day, not today's remaining slots:
    # at office hours a time-dependent 3-slot remainder is entirely valid.
    times = c.get(f"{base}?art={a_id}&day={tomorrow().isoformat()}").text
    assert "Wann passt es Ihnen?" in times
    assert 'name="name"' not in times
    assert len(re.findall(r'class="bk-day-option[ "]', times)) == 7
    assert "Weitere Tage" in times
    # Die Anzahl buchbarer Zeiten kann je nach Wochentag, Ausnahmen und
    # bereits belegten Zeiten schwanken; die Tagespagination muss unabhängig
    # vom Ausführungstag funktionieren.
    assert 1 <= times.count('name="slot"') <= 7
    value = re.search(r'name="slot" id="s-1-[^"]+" value="([^"]+)"', times).group(1)
    details = c.get(f"{base}?art={a_id}&step=details&slot={quote(value, safe='')}").text
    assert "Ihre Angaben" in details and 'name="name"' in details
    assert 'name="slot" value="' + value + '"' in details
    assert 'name="email"' in details and "Zurück zum Termin" in details

    later = c.get(f"{base}?art={a_id}&step=times&offset=7").text
    assert len(re.findall(r'class="bk-day-option[ "]', later)) <= 7
    assert "Vorherige Tage" in later
    assert 'name="slot"' in later
    bad = c.get(f"{base}?art={a_id}&step=details&slot=invalid").text
    assert "nicht mehr verfügbar" in bad
    assert 'name="name"' not in bad


def test_public_wizard_preserves_provider_selection_through_steps():
    _, a_id, _, _, ben = make_page(choose=True, approval=True)
    c = client()
    base = "/b/bt-buergerbuero-token-123"
    times = c.get(f"{base}?art={a_id}&person={ben}").text
    assert f'name="person" value="{ben}"' in times
    value = re.search(r'name="slot" id="s-1-[^"]+" value="([^"]+)"', times).group(1)
    details = c.get(f"{base}?art={a_id}&person={ben}&step=details&slot={quote(value, safe='')}").text
    assert f'name="person" value="{ben}"' in details
    assert "Termin anfragen" in details
    assert "Lageplan mitbringen" in details
    # Beim Zurückgehen wird die gewählte Terminart beibehalten.
    assert f"art={a_id}" in details
