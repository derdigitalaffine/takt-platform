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
