import pytest
from sqlalchemy import select
from fastapi import HTTPException
from app import calendars
from app.calendar_models import Calendar, CalendarEvent
from app.db import SessionLocal
from conftest import login, csrf_of
from test_native_tasks import task_people


def test_calendar_acl_json_write_and_ics(db, task_people):
    owner, other = task_people[:2]
    row = Calendar(owner_id=owner.id, title="Jahrestermine", visibility="private")
    db.add(row)
    db.commit()
    cid = row.id
    try:
        c = login(owner.email, "task-passwort-123")
        token = csrf_of(c.get("/kalender").text)
        payload = dict(
            title="Jahresabschluss", start="2026-12-28", end="2026-12-30", all_day=True
        )
        assert c.post(f"/kalender/{cid}/termine", json=payload).status_code == 400
        response = c.post(
            f"/kalender/{cid}/termine", json=payload, headers={"X-CSRF-Token": token}
        )
        assert response.status_code == 200, response.text
        event = response.json()
        assert event["end"] == "2026-12-31"
        external = login(other.email, "task-passwort-123")
        assert external.get(f"/kalender/{cid}/data").status_code == 403
        assert external.get(f"/kalender/{cid}/abo.ics").status_code == 403
        ics = c.get(f"/kalender/{cid}/abo.ics")
        assert ics.status_code == 200 and "DTEND;VALUE=DATE:20261231" in ics.text
        response = c.post(
            f"/kalender/{cid}/termine",
            json={**payload, "id": event["id"], "version": 0},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 409
    finally:
        db.query(CalendarEvent).filter_by(calendar_id=cid).delete()
        db.delete(row)
        db.commit()


@pytest.fixture(autouse=True)
def calendar_enabled():
    from conftest import settings

    settings(module_calendars="1")
    yield
    settings(module_calendars="0")


def test_closure_created_in_calendar_is_same_object_in_leave(db, task_people, units):
    from app.leave_extensions import Closure
    from test_leave import assigned
    from test_organization import grant

    _, unit, team, other = units
    manager, member, outsider = task_people[:3]
    assigned(db, member, team)
    assigned(db, outsider, other)
    grant(db, unit, manager, "leave_settings")
    c = login(manager.email, "task-passwort-123")
    token = csrf_of(c.get("/kalender").text)
    try:
        response = c.post(
            "/kalender/schliesszeiten",
            json=dict(
                org_id=unit.id,
                title="Zwischen den Jahren",
                start="2026-12-28",
                end="2026-12-30",
                minimum=1,
                enrollment="self",
            ),
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200, response.text
        rid = response.json()["id"]
        assert db.get(Closure, rid).org_id == unit.id
        member_client = login(member.email, "task-passwort-123")
        events = member_client.get("/kalender/organisationstermine").json()["events"]
        assert len(events) == 1 and events[0]["id"] == "closure:" + str(rid)
        assert events[0]["end"] == "2026-12-31"
        assert (
            "Zwischen den Jahren"
            in member_client.get("/urlaub?unit=" + str(team.id)).text
        )
        other_client = login(outsider.email, "task-passwort-123")
        assert other_client.get("/kalender/organisationstermine").json()["events"] == []
        denied = other_client.post(
            "/kalender/schliesszeiten",
            json=dict(
                org_id=unit.id, title="Unzulässig", start="2026-12-28", end="2026-12-30"
            ),
            headers={"X-CSRF-Token": csrf_of(other_client.get("/kalender").text)},
        )
        assert denied.status_code == 403
    finally:
        db.query(Closure).filter_by(org_id=unit.id).delete()
        db.commit()


from test_organization import units


def test_shared_calendar_and_feed_follow_live_rights(db, task_people):
    import re
    from app.calendar_models import CalendarFeed, CalendarGrant

    owner, reader = task_people[:2]
    cal = Calendar(owner_id=owner.id, title="Freigaben", visibility="private")
    db.add(cal)
    db.commit()
    c = login(owner.email, "task-passwort-123")
    other = login(reader.email, "task-passwort-123")
    try:
        token = csrf_of(c.get(f"/kalender/{cal.id}/teilen").text)
        response = c.post(
            f"/kalender/{cal.id}/teilen",
            data={
                "csrf": token,
                "version": cal.version,
                "target": "user:" + str(reader.id),
            },
        )
        assert response.status_code == 303
        assert other.get(f"/kalender/{cal.id}/data").status_code == 200
        created = other.post(
            "/kalender/abos",
            data={
                "csrf": csrf_of(other.get("/kalender/abos").text),
                "calendar_id": cal.id,
                "name": "Thunderbird",
            },
        )
        assert created.status_code == 200
        url = re.search(
            r"https://portal.example.org(/kalender/abos/[A-Za-z0-9_-]+.ics)",
            created.text,
        ).group(1)
        from conftest import client

        assert client().get(url).status_code == 200
        grant = db.scalar(
            select(CalendarGrant).where(CalendarGrant.calendar_id == cal.id)
        )
        db.delete(grant)
        db.commit()
        assert other.get(f"/kalender/{cal.id}/data").status_code == 403
        assert client().get(url).status_code == 404
        assert client().get(f"/kalender/oeffentlich/{cal.id}").status_code == 404
    finally:
        db.query(CalendarFeed).filter_by(calendar_id=cal.id).delete()
        db.query(CalendarGrant).filter_by(calendar_id=cal.id).delete()
        db.delete(cal)
        db.commit()


def test_event_audience_never_leaks_through_public_json_ics_or_dav(
    db, task_people, units
):
    from app.calendar_models import CalendarGrant
    from test_leave import assigned
    from test_organization import grant
    from conftest import client

    _, unit, team, elsewhere = units
    owner, member, outsider = task_people[:3]
    assigned(db, member, team)
    assigned(db, outsider, elsewhere)
    grant(db, unit, owner, "planner")
    cal = Calendar(owner_id=owner.id, title="Jahreskalender", visibility="public")
    db.add(cal)
    db.commit()
    try:
        row = calendars.save_event(
            db,
            owner,
            cal,
            dict(
                title="Nur Bereich A",
                start="2026-12-01",
                end="2026-12-01",
                all_day=True,
                org_id=unit.id,
                include_children="1",
            ),
        )
        db.commit()
        c = client()
        assert (
            c.get(
                f"/kalender/oeffentlich/{cal.id}/data?start=2026-12-01&end=2027-01-01"
            ).json()
            == []
        )
        assert "Nur Bereich A" not in calendars.export(db, None, cal)
        assert "Nur Bereich A" not in calendars.export(db, outsider, cal)
        assert "Nur Bereich A" in calendars.export(db, member, cal)
    finally:
        db.delete(cal)
        db.commit()


def test_web_edit_retains_client_alarm_and_custom_properties(db, task_people):
    owner = task_people[0]
    cal = Calendar(owner_id=owner.id, title="Client roundtrip")
    db.add(cal)
    db.commit()
    raw = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Roundtrip//EN\r\nBEGIN:VEVENT\r\nUID:roundtrip@example.org\r\nDTSTART;VALUE=DATE:20261201\r\nDTEND;VALUE=DATE:20261202\r\nSUMMARY:Original\r\nX-CLIENT-NOTE:keep-me\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nDESCRIPTION:Remember\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    try:
        row = calendars.save_event(
            db,
            owner,
            cal,
            dict(title="Original", start="2026-12-01", end="2026-12-01", all_day=True),
            raw_ical=raw,
        )
        db.commit()
        calendars.save_event(
            db,
            owner,
            cal,
            dict(
                title="Web edit",
                start="2026-12-03",
                end="2026-12-03",
                all_day=True,
                version=row.version,
            ),
            row,
        )
        db.commit()
        content = calendars.export(db, owner, cal)
        assert (
            "X-CLIENT-NOTE:keep-me" in content
            and "BEGIN:VALARM" in content
            and "SUMMARY:Web edit" in content
            and "DTSTART;VALUE=DATE:20261203" in content
        )
    finally:
        db.delete(cal)
        db.commit()
