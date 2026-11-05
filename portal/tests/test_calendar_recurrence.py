from datetime import datetime, timezone
from app import calendar_recurrence as recurrence, calendars
from app.calendar_models import Calendar, CalendarEvent
from test_native_tasks import task_people


def test_all_day_series_exclusions_and_date_until(db, task_people):
    owner = task_people[0]
    cal = Calendar(owner_id=owner.id, title="Serie", visibility="private")
    db.add(cal)
    db.commit()
    raw = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:series-test@takt\r\nDTSTART;VALUE=DATE:20261201\r\nDTEND;VALUE=DATE:20261202\r\nRRULE:FREQ=DAILY;UNTIL=20261205\r\nEXDATE;VALUE=DATE:20261203\r\nSUMMARY:Serie\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    try:
        row = calendars.save_event(
            db,
            owner,
            cal,
            dict(title="Serie", start="2026-12-01", end="2026-12-01", all_day=True),
            raw_ical=raw,
        )
        db.commit()
        items = recurrence.occurrences(
            row,
            datetime(2026, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 12, 10, tzinfo=timezone.utc),
        )
        assert [e["start"] for e in items] == [
            "2026-12-01",
            "2026-12-02",
            "2026-12-04",
            "2026-12-05",
        ]
        assert "EXDATE;VALUE=DATE:20261203" in calendars.export(db, owner, cal)
    finally:
        db.query(CalendarEvent).filter_by(calendar_id=cal.id).delete()
        db.delete(cal)
        db.commit()


def test_daily_wall_time_survives_berlin_dst(db, task_people):
    owner = task_people[0]
    cal = Calendar(owner_id=owner.id, title="DST", visibility="private")
    db.add(cal)
    db.commit()
    try:
        row = calendars.save_event(
            db,
            owner,
            cal,
            dict(
                title="Serie",
                start="2026-03-28T08:00:00+01:00",
                end="2026-03-28T09:00:00+01:00",
                repeat="daily",
                repeat_count=3,
                time_zone="Europe/Berlin",
            ),
        )
        db.commit()
        events = recurrence.occurrences(
            row,
            datetime(2026, 3, 27, tzinfo=timezone.utc),
            datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        assert len(events) == 3
        assert events[0]["start"].endswith("08:00:00+01:00")
        assert events[1]["start"].endswith("08:00:00+02:00")
    finally:
        db.query(CalendarEvent).filter_by(calendar_id=cal.id).delete()
        db.delete(cal)
        db.commit()
