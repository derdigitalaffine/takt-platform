"""Read-only projections of canonical business objects, with their live access rules."""

from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select, or_
from .db import (
    get_settings,
    to_local,
    Meeting,
    Invitee,
    Seminar,
    SeminarEnrollment,
    BookingPage,
    Booking,
    Absence,
)

SOURCES = {
    "meetings": ("Besprechungen", "module_video"),
    "seminars": ("Seminare und Teilnahmen", "module_seminars"),
    "resources": ("Ressourcenbelegung", "module_resources"),
    "bookings": ("Terminbuchungen", "module_bookings"),
    "tasks": ("Aufgabentermine", "module_tasks"),
    "leave": ("Mein Urlaub", "module_calendars"),
    "absences": ("Meine Abwesenheiten", "module_calendars"),
    "closures": ("Schließzeiten meines Bereichs", "module_calendars"),
}


def enabled(db, kind):
    cfg = get_settings(db)
    return kind in SOURCES and (
        kind == "meetings" or cfg.get(SOURCES[kind][1], "1") == "1"
    )


def project(db, user, kind, start, end):
    if not user or not user.active or not enabled(db, kind):
        return []
    a = start.astimezone(timezone.utc).replace(tzinfo=None)
    b = end.astimezone(timezone.utc).replace(tzinfo=None)
    out = []

    def add(key, title, s, e, url, all_day=False, description="", status=""):
        if not s or not e:
            return
        if isinstance(s, datetime):
            s = to_local(s) if s.tzinfo is None else s
            e = to_local(e) if e.tzinfo is None else e
            if e <= start or s >= end:
                return
        else:
            if e <= start.date() or s >= end.date():
                return
        out.append(
            dict(
                id=kind + ":" + str(key),
                title=title,
                start=s.isoformat(),
                end=e.isoformat(),
                allDay=all_day,
                extendedProps=dict(
                    source=kind, url=url, description=description, status=status
                ),
            )
        )

    if kind == "meetings" and user.can("video"):
        for row in db.scalars(
            select(Meeting).where(
                or_(
                    Meeting.owner_id == user.id,
                    Meeting.id.in_(
                        select(Invitee.meeting_id).where(Invitee.email == user.email)
                    ),
                ),
                Meeting.ends_at > a,
                Meeting.starts_at < b,
                Meeting.cancelled_at.is_(None),
            )
        ):
            add(
                row.id,
                row.title,
                row.starts_at,
                row.ends_at,
                (
                    "/meetings/" + str(row.id)
                    if row.owner_id == user.id
                    else "/join/" + row.room
                ),
            )
    elif kind == "seminars":
        from . import seminars

        owned = set(
            db.scalars(
                select(SeminarEnrollment.seminar_id).where(
                    SeminarEnrollment.user_id == user.id,
                    SeminarEnrollment.status.in_(["confirmed", "attended"]),
                )
            )
        )
        for row in db.scalars(select(Seminar)):
            planning = seminars.may_plan(db, user, row)
            if row.id not in owned and not planning:
                continue
            enrolled = list(
                db.scalars(
                    select(SeminarEnrollment).where(
                        SeminarEnrollment.seminar_id == row.id,
                        SeminarEnrollment.user_id == user.id,
                        SeminarEnrollment.status.in_(["confirmed", "attended"]),
                    )
                )
            )
            allowed = {
                t.id
                for rec in enrolled
                for t in seminars.enrollment_sessions(db, row, rec)
            }
            if row.status == "cancelled":
                continue
            for term in seminars.sessions(db, row):
                if not planning and term.id not in allowed:
                    continue
                add(
                    term.id,
                    row.title + (" · " + term.title if term.title else ""),
                    term.starts_at,
                    term.ends_at,
                    "/seminare/" + str(row.id),
                )
    elif kind == "resources":
        from . import resources

        for resource, level in resources.visible(db, user):
            for event in resources.fc_events(
                resources.calendar_events(
                    db,
                    [resource],
                    a,
                    b,
                    "title" if level >= 3 else "busy",
                    staff_links=level >= 3,
                )
            ):
                event["id"] = kind + ":" + str(resource.id) + ":" + event["id"]
                event.setdefault("extendedProps", {}).update(
                    source=kind, url=event.pop("url", "/resources/" + str(resource.id))
                )
                out.append(event)
    elif kind == "bookings":
        from . import shares, bookings

        for page in db.scalars(select(BookingPage)):
            if shares.access_level(db, "booking", page, user) < shares.VIEW:
                continue
            for row in bookings.active_bookings(page):
                add(
                    row.id,
                    page.title + ": " + row.name,
                    row.starts_at,
                    row.ends_at,
                    "/bookings/" + str(page.id),
                )
    elif kind == "tasks":
        from . import tasks
        from .task_models import Task

        for row in db.scalars(
            tasks.visible_query(user).where(
                Task.due_at.is_not(None), Task.archived_at.is_(None)
            )
        ):
            if row.due_has_time:
                add(
                    row.id,
                    row.title,
                    row.starts_at or row.due_at,
                    row.due_at + timedelta(minutes=1),
                    "/aufgaben/" + str(row.id),
                )
            else:
                day = to_local(row.due_at).date()
                add(
                    row.id,
                    row.title,
                    day,
                    day + timedelta(days=1),
                    "/aufgaben/" + str(row.id),
                    True,
                )
    elif kind == "leave":
        import json
        from .leave_models import LeaveRequest

        for row in db.scalars(
            select(LeaveRequest).where(LeaveRequest.person_id == user.id)
        ):
            if not row.effective_json:
                continue
            interval = json.loads(row.effective_json)
            halves = ""
            if interval["start_half"] != "am" or interval["end_half"] != "pm":
                halves = (
                    " ("
                    + {"am": "Vormittag", "pm": "Nachmittag"}[interval["start_half"]]
                    + " – "
                    + {"am": "Vormittag", "pm": "Nachmittag"}[interval["end_half"]]
                    + ")"
                )
            add(
                row.id,
                "Verbindlicher Urlaub" + halves,
                date.fromisoformat(interval["starts_on"]),
                date.fromisoformat(interval["ends_on"]) + timedelta(days=1),
                "/urlaub",
                True,
                status="binding",
            )
    elif kind == "absences":
        from . import absence

        for row in db.scalars(
            select(Absence).where(
                Absence.user_id == user.id, Absence.status == "confirmed"
            )
        ):
            add(
                row.id,
                "Abwesend: " + absence.span(row),
                date.fromisoformat(row.starts_on),
                date.fromisoformat(row.ends_on) + timedelta(days=1),
                "/abwesenheiten",
                True,
            )
    elif kind == "closures":
        from .leave_extensions import Closure
        from .routes_calendars import closure_visible, closure_link

        for row in db.scalars(select(Closure)):
            if closure_visible(db, user, row):
                add(
                    row.id,
                    "Schließzeit: " + row.title,
                    date.fromisoformat(row.starts_on),
                    date.fromisoformat(row.ends_on) + timedelta(days=1),
                    closure_link(db, user, row),
                    True,
                )
    if len(out) > 10000:
        from fastapi import HTTPException

        raise HTTPException(507, "Zu viele Fachtermine im angefragten Zeitraum.")
    return out


def to_ics(events, name):
    from . import ics
    from .config import settings

    items = []
    for item in events:
        props = item.get("extendedProps", {})
        event = {
            "uid": "takt-" + item["id"] + "@calendar",
            "dtstamp": datetime(2000, 1, 1, tzinfo=timezone.utc),
            "summary": item["title"],
            "description": props.get("description", ""),
            "transp": (
                "TRANSPARENT"
                if props.get("source") in ("closures", "tasks")
                else "OPAQUE"
            ),
        }
        for key, prop in [("start", "dtstart"), ("end", "dtend")]:
            event[prop] = (
                date.fromisoformat(item[key][:10])
                if item.get("allDay")
                else datetime.fromisoformat(item[key])
            )
        url = props.get("url", "")
        if url.startswith("/"):
            event["url"] = settings.portal_base_url + url
        items.append(event)
    return ics.feed(items, name, prodid="-//TAKT//Calendar Sources//DE").decode()


def dav_objects(db, user, calendar):
    """Stable, read-only calendar resources projected directly from the business data."""
    import base64, hashlib

    events = project(
        db,
        user,
        calendar.source,
        datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(2200, 12, 31, tzinfo=timezone.utc),
    )
    result = {}
    for event in events:
        name = (
            base64.urlsafe_b64encode(event["id"].encode()).decode().rstrip("=") + ".ics"
        )
        content = to_ics([event], calendar.title)
        result[name] = (
            content,
            '"' + hashlib.sha256(content.encode()).hexdigest() + '"',
        )
    return result
