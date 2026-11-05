import base64, plistlib
from sqlalchemy import select
from app import calendar_devices
from app.calendar_models import (
    Calendar,
    CalendarEvent,
    CalendarDevice,
    CalendarDeviceScope,
)
from conftest import client, login, csrf_of
from test_native_tasks import task_people

ICAL = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\nBEGIN:VEVENT\r\nUID:device-event@example.org\r\nDTSTART;VALUE=DATE:20261201\r\nDTEND;VALUE=DATE:20261203\r\nSUMMARY:Kalendertest\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"


def test_device_scope_etags_and_revocation(db, task_people):
    user = task_people[0]
    cal = Calendar(owner_id=user.id, title="DAV Test", visibility="private")
    other = Calendar(owner_id=user.id, title="Not selected", visibility="private")
    db.add_all([cal, other])
    db.commit()
    device, secret = calendar_devices.create(db, user, "Mein Gerät", [(cal.id, True)])
    db.commit()
    c = client()
    auth = {
        "Authorization": "Basic "
        + base64.b64encode((device.username + ":" + secret).encode()).decode()
    }
    url = f"/caldav/calendars/{cal.id}/event.ics"
    try:
        assert c.get(f"/caldav/calendars/{other.id}/", headers=auth).status_code == 403
        assert (
            c.request(
                "PROPFIND",
                "/caldav/principals/" + device.username + "/",
                headers={**auth, "Depth": "0"},
            ).status_code
            == 207
        )
        result = c.put(url, content=ICAL, headers={**auth, "If-None-Match": "*"})
        assert result.status_code == 201, result.text
        tag = result.headers["etag"]
        assert c.get(url, headers=auth).status_code == 200
        assert (
            c.put(url, content=ICAL, headers={**auth, "If-Match": '"old"'}).status_code
            == 412
        )
        changed = c.put(
            url,
            content=ICAL.replace(b"Kalendertest", b"Geaendert"),
            headers={**auth, "If-Match": tag},
        )
        assert changed.status_code == 204
        assert changed.headers["etag"] != tag
        device.revoked = True
        db.commit()
        assert c.get(url, headers=auth).status_code == 401
    finally:
        db.query(CalendarEvent).filter(
            CalendarEvent.calendar_id.in_([cal.id, other.id])
        ).delete()
        db.delete(device)
        db.delete(cal)
        db.delete(other)
        db.commit()


def test_profile_download_has_device_secret_and_private_headers(db, task_people):
    user = task_people[0]
    cal = Calendar(owner_id=user.id, title="Profile Test", visibility="private")
    db.add(cal)
    db.commit()
    c = login(user.email, "task-passwort-123")
    token = csrf_of(c.get("/kalender/geraete").text)
    try:
        response = c.post(
            "/kalender/geraete",
            data={
                "csrf": token,
                "name": "iPhone",
                "platform": "ios",
                "calendars": str(cal.id),
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        account = plistlib.loads(response.content)["PayloadContent"][0]
        device = db.scalar(
            select(CalendarDevice).where(
                CalendarDevice.username == account["CalDAVUsername"]
            )
        )
        assert calendar_devices.authenticate(
            db, account["CalDAVUsername"], account["CalDAVPassword"]
        )
        assert device.secret_hash != account["CalDAVPassword"]
        assert not db.get(CalendarDeviceScope, (device.id, cal.id)).can_write
    finally:
        for d in db.scalars(
            select(CalendarDevice).where(CalendarDevice.user_id == user.id)
        ):
            db.delete(d)
        db.delete(cal)
        db.commit()


from test_calendars import calendar_enabled


def test_reports_properties_incremental_changes_and_deletions(db, task_people):
    from xml.etree import ElementTree as ET

    user = task_people[0]
    cal = Calendar(owner_id=user.id, title="Sync", visibility="private")
    db.add(cal)
    db.commit()
    device, secret = calendar_devices.create(db, user, "Sync test", [(cal.id, True)])
    db.commit()
    c = client()
    auth = {
        "Authorization": "Basic "
        + base64.b64encode((device.username + ":" + secret).encode()).decode()
    }
    base = f"/caldav/calendars/{cal.id}/"
    url = base + "sync.ics"

    def sync(token=""):
        return c.request(
            "REPORT",
            base,
            headers=auth,
            content=f'<d:sync-collection xmlns:d="DAV:"><d:sync-token>{token}</d:sync-token><d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>',
        )

    try:
        created = c.put(url, content=ICAL, headers={**auth, "If-None-Match": "*"})
        assert created.status_code == 201
        props = c.request(
            "PROPFIND",
            base,
            headers={**auth, "Depth": "0"},
            content='<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:unknown/><d:sync-token/></d:prop></d:propfind>',
        )
        assert (
            props.status_code == 207
            and "404 Not Found" in props.text
            and "calendar" in props.text
        )
        first = sync()
        assert first.status_code == 207, first.text
        tree = ET.fromstring(first.content)
        token = tree.findtext("{DAV:}sync-token")
        assert token and len(tree.findall("{DAV:}response")) == 1
        unchanged = sync(token)
        assert len(ET.fromstring(unchanged.content).findall("{DAV:}response")) == 0
        query = '<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:"><d:prop><d:getetag/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="20270101T000000Z" end="20270201T000000Z"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>'
        result = c.request("REPORT", base, headers=auth, content=query)
        assert result.status_code == 207 and not ET.fromstring(result.content).findall(
            "{DAV:}response"
        )
        multiget = c.request(
            "REPORT",
            base,
            headers=auth,
            content=f'<c:calendar-multiget xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:"><d:prop><d:getetag/></d:prop><d:href>{url}</d:href><d:href>{base}missing.ics</d:href></c:calendar-multiget>',
        )
        assert multiget.status_code == 207 and "404 Not Found" in multiget.text
        assert (
            c.delete(
                url, headers={**auth, "If-Match": created.headers["etag"]}
            ).status_code
            == 204
        )
        deleted = sync(token)
        assert deleted.status_code == 207 and "404 Not Found" in deleted.text
        assert sync("urn:invalid").status_code == 403
    finally:
        db.delete(device)
        db.delete(cal)
        db.commit()


def test_readonly_source_sync_rechecks_membership_and_reports_removal(
    db, task_people, units
):
    import pytest
    from fastapi import HTTPException
    from xml.etree import ElementTree as ET
    from app.leave_extensions import Closure
    from app.org_models import OrgMembership
    from test_leave import assigned

    user = task_people[0]
    _, unit, _, _ = units
    assigned(db, user, unit)
    closed = Closure(
        org_id=unit.id, title="Jahresruhe", starts_on="2026-12-28", ends_on="2026-12-30"
    )
    cal = Calendar(
        owner_id=user.id,
        title="Meine Schließzeiten",
        source="closures",
        visibility="private",
    )
    db.add_all([closed, cal])
    db.commit()
    with pytest.raises(HTTPException):
        calendar_devices.create(db, user, "Invalid write", [(cal.id, True)])
    db.rollback()
    device, secret = calendar_devices.create(
        db, user, "Source reader", [(cal.id, False)]
    )
    db.commit()
    auth = {
        "Authorization": "Basic "
        + base64.b64encode((device.username + ":" + secret).encode()).decode()
    }
    c = client()
    base = f"/caldav/calendars/{cal.id}/"

    def sync(token=""):
        return c.request(
            "REPORT",
            base,
            headers=auth,
            content=f'<d:sync-collection xmlns:d="DAV:"><d:sync-token>{token}</d:sync-token><d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>',
        )

    try:
        result = sync()
        assert result.status_code == 207, result.text
        tree = ET.fromstring(result.content)
        token = tree.findtext("{DAV:}sync-token")
        url = tree.findtext("{DAV:}response/{DAV:}href")
        assert url
        assert "Jahresruhe" in c.get(url, headers=auth).text
        assert (
            c.put(url, content=ICAL, headers={**auth, "If-Match": "*"}).status_code
            == 403
        )
        db.query(OrgMembership).filter_by(user_id=user.id).delete()
        db.commit()
        removed = sync(token)
        assert removed.status_code == 207 and "404 Not Found" in removed.text
        assert c.get(url, headers=auth).status_code == 404
    finally:
        db.delete(device)
        db.delete(cal)
        db.delete(closed)
        db.commit()


from test_organization import units
