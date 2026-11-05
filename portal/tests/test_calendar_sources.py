"""Canonical projections retain their source's object and term-level ACLs."""

from datetime import datetime, timezone, timedelta
import json
from app import calendar_sources
from app.db import SeminarSession, Poll, PollOption, get_settings
from conftest import settings
from test_seminars import people, make
from test_native_tasks import task_people


def test_seminar_lecturer_only_receives_assigned_terms(db, people):
    row, first = make(db, people)
    first.lecturers_json = json.dumps([people[2].id])
    second = SeminarSession(
        seminar_id=row.id,
        starts_at=first.starts_at + timedelta(days=1),
        ends_at=first.ends_at + timedelta(days=1),
        lecturers_json=json.dumps([people[3].id]),
    )
    db.add(second)
    db.commit()
    a = datetime(2027, 3, 1, tzinfo=timezone.utc)
    b = datetime(2027, 4, 1, tzinfo=timezone.utc)
    assert [
        e["id"] for e in calendar_sources.project(db, people[2], "seminars", a, b)
    ] == ["seminars:" + str(first.id)]
    assert [
        e["id"] for e in calendar_sources.project(db, people[3], "seminars", a, b)
    ] == ["seminars:" + str(second.id)]
    assert not calendar_sources.project(db, people[1], "seminars", a, b)


def test_final_poll_projects_live_option_without_exposing_private_poll(db, task_people):
    owner, other = task_people[:2]
    old = get_settings(db).get("module_polls", "1")
    settings(module_polls="1")
    poll = Poll(owner_id=owner.id, title="Festgelegte Besprechung")
    db.add(poll)
    db.flush()
    option = PollOption(
        poll_id=poll.id,
        starts_at=datetime(2026, 12, 1, 9),
        ends_at=datetime(2026, 12, 1, 10),
    )
    db.add(option)
    db.flush()
    poll.final_option_id = option.id
    db.commit()
    a = datetime(2026, 12, 1, tzinfo=timezone.utc)
    b = datetime(2027, 1, 1, tzinfo=timezone.utc)
    try:
        events = calendar_sources.project(db, owner, "polls", a, b)
        assert len(events) == 1 and events[0]["title"] == poll.title
        assert not calendar_sources.project(db, other, "polls", a, b)
        option.starts_at = datetime(2026, 12, 2, 9)
        option.ends_at = datetime(2026, 12, 2, 10)
        db.commit()
        assert calendar_sources.project(db, owner, "polls", a, b)[0][
            "start"
        ].startswith("2026-12-02")
    finally:
        db.delete(poll)
        db.commit()
        settings(module_polls=old)


def test_meeting_invite_does_not_require_global_creation_right_and_keeps_token_private(
    db, task_people
):
    from app.db import Meeting, Invitee
    from conftest import login
    import secrets

    owner, member, outsider = task_people[:3]
    owner.permissions = "video"
    row = Meeting(
        owner_id=owner.id,
        title="Planungsbesprechung",
        room="calendar-" + secrets.token_hex(8),
        starts_at=datetime(2026, 12, 1, 9),
        duration_minutes=60,
    )
    db.add(row)
    db.flush()
    invite = Invitee(
        meeting_id=row.id, email=member.email, join_token=secrets.token_hex(16)
    )
    db.add(invite)
    db.commit()
    a = datetime(2026, 12, 1, tzinfo=timezone.utc)
    b = datetime(2027, 1, 1, tzinfo=timezone.utc)
    try:
        events = calendar_sources.project(db, member, "meetings", a, b)
        assert len(events) == 1 and events[0]["title"] == row.title
        assert invite.join_token not in json.dumps(events)
        assert not calendar_sources.project(db, outsider, "meetings", a, b)
        c = login(member.email, "task-passwort-123")
        response = c.get(events[0]["extendedProps"]["url"], follow_redirects=False)
        assert (
            response.status_code == 303
            and response.headers["location"] == "/join/" + invite.join_token
        )
        db.delete(invite)
        db.commit()
        assert not calendar_sources.project(db, member, "meetings", a, b)
        assert (
            c.get(
                f"/kalender/besprechungen/{row.id}/oeffnen", follow_redirects=False
            ).status_code
            == 403
        )
    finally:
        db.delete(row)
        db.commit()


from test_calendars import calendar_enabled


def test_resource_booking_task_and_absence_projections_keep_acl_and_private_notes(
    db, task_people
):
    import secrets
    from app.db import Resource, ResourceBooking, BookingPage, Booking, Absence
    from app.task_models import Task

    owner, outsider = task_people[:2]
    key = secrets.token_hex(8)
    old = get_settings(db)
    settings(module_resources="1", module_bookings="1")
    resource = Resource(
        owner_id=owner.id, name="Kalenderraum", slug="calendar-" + key, public=False
    )
    page = BookingPage(owner_id=owner.id, title="Sprechstunde", public_token=key)
    db.add_all([resource, page])
    db.flush()
    start = datetime(2026, 12, 1, 9)
    end = start + timedelta(hours=1)
    rb = ResourceBooking(
        resource_id=resource.id,
        ref="CAL-" + key,
        token=key,
        starts_at=start,
        ends_at=end,
        status="confirmed",
        mode="hour",
        title="Reserviert",
        email="secret@example.org",
    )
    booking = Booking(
        page_id=page.id,
        starts_at=start,
        ends_at=end,
        name="Gast",
        email="secret@example.org",
        note="DO_NOT_EXPORT",
        token=key,
    )
    task = Task(
        creator_id=owner.id,
        assignee_id=owner.id,
        title="Frist",
        due_at=end,
        due_has_time=True,
        description="DO_NOT_EXPORT",
    )
    absence = Absence(
        user_id=owner.id,
        created_by=owner.id,
        starts_on="2026-12-01",
        ends_on="2026-12-01",
        status="confirmed",
        note="DO_NOT_EXPORT",
    )
    db.add_all([rb, booking, task, absence])
    db.commit()
    a = datetime(2026, 12, 1, tzinfo=timezone.utc)
    b = datetime(2027, 1, 1, tzinfo=timezone.utc)
    try:
        for kind in ("resources", "bookings", "tasks", "absences"):
            events = calendar_sources.project(db, owner, kind, a, b)
            assert events, kind
            content = calendar_sources.to_ics(events, kind)
            assert (
                "DO_NOT_EXPORT" not in content and "secret@example.org" not in content
            )
            assert not calendar_sources.project(db, outsider, kind, a, b), kind
        rb.status = "cancelled"
        booking.status = "cancelled"
        db.commit()
        assert not calendar_sources.project(db, owner, "resources", a, b)
        assert not calendar_sources.project(db, owner, "bookings", a, b)
    finally:
        for item in (resource, page, task, absence):
            db.delete(item)
        db.commit()
        settings(
            module_resources=old.get("module_resources", "1"),
            module_bookings=old.get("module_bookings", "1"),
        )
