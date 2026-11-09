"""Calendar ACLs are reused by HTML, JSON and calendar-file serialization."""

from datetime import date, datetime, timedelta, timezone
import uuid
from sqlalchemy import select, or_, func
from fastapi import HTTPException
from .db import User, GroupMember, utcnow
from .calendar_models import Calendar, CalendarEvent, CalendarGrant, CalendarAudit
from .org_models import OrgMembership
from . import organization as org, ics


async def json_payload(request):
    import json

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 262144:
            raise HTTPException(413, "Anfrage zu groß.")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Gültige Eingaben erforderlich.")
    if not isinstance(data, dict):
        raise HTTPException(422, "Gültige Eingaben erforderlich.")
    return data


def access(db, user, calendar, write=False):
    if calendar.source == "birthdays":
        from . import birthdays
        # A birthday projection is always private and per-account; normal
        # calendar publication/ACL grants must never elevate its visibility.
        return bool(
            not write and user and user.active and calendar.owner_id == user.id
            and calendar.visibility == "private"
            and (birthdays.external_allowed(db, user, "caldav")
                 or birthdays.external_allowed(db, user, "ics"))
        )
    if write and calendar.source != "free":
        return False
    if user and user.active and (user.is_admin or user.id == calendar.owner_id):
        return True
    if not write and calendar.visibility == "public":
        return True
    if not user or not user.active:
        return False
    if not write and calendar.visibility == "internal":
        return True
    if calendar.visibility == "organization" and calendar.org_id:
        if not org.active_path(db, calendar.org_id):
            return False
        if write and org.allows(db, user, calendar.org_id, "plan"):
            return True
        if not write:
            for oid in db.scalars(
                select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)
            ):
                if (
                    oid == calendar.org_id
                    or calendar.include_children
                    and calendar.org_id in org.active_path(db, oid)
                ):
                    return True
    groups = select(GroupMember.group_id).where(GroupMember.user_id == user.id)
    grants = select(CalendarGrant).where(
        CalendarGrant.calendar_id == calendar.id,
        or_(CalendarGrant.user_id == user.id, CalendarGrant.group_id.in_(groups)),
    )
    if write:
        grants = grants.where(CalendarGrant.can_write.is_(True))
    return db.scalar(grants) is not None


def event_access(db, actor, calendar, event):
    if not access(db, actor, calendar):
        return False
    if not event.org_id:
        return True
    if not actor or not actor.active:
        return False
    if (
        actor.is_admin
        or actor.id == calendar.owner_id
        or org.allows(db, actor, event.org_id, "plan")
    ):
        return True
    if not org.active_path(db, event.org_id):
        return False
    return any(
        oid == event.org_id
        or event.include_children
        and event.org_id in org.active_path(db, oid)
        for oid in db.scalars(
            select(OrgMembership.org_id).where(OrgMembership.user_id == actor.id)
        )
    )


def event_data(row):
    data = dict(
        id=row.id,
        title=row.title,
        start=row.starts_at,
        end=row.ends_at,
        allDay=row.all_day,
        extendedProps=dict(
            description=row.description, location=row.location, version=row.version
        ),
    )
    data["extendedProps"].update(
        orgId=getattr(row, "org_id", None),
        includeChildren=getattr(row, "include_children", True),
    )
    if row.ical_data:
        from .calendar_recurrence import validate

        _, master, events = validate(row.ical_data)
        if master.get("RRULE") or master.get("RDATE") or len(events) > 1:
            rule = master.get("RRULE", {})
            data["extendedProps"].update(
                series=True,
                seriesId=row.id,
                masterStart=row.starts_at,
                masterEnd=row.ends_at,
                masterTitle=row.title,
                repeat=str(rule.get("FREQ", ["NONE"])[0]),
                repeatCount=str(rule.get("COUNT", [""])[0]),
                hasOverrides=len(events) > 1,
            )
    return data


def audit(db, actor, calendar, action, event=None, device_id=None):
    db.add(
        CalendarAudit(
            calendar_id=calendar.id,
            actor_id=actor.id,
            device_id=device_id,
            action=action,
            event_uid=event.uid if event else "",
            event_title=event.title if event else "",
            version=event.version if event else calendar.version,
        )
    )


def save_event(db, actor, calendar, data, row=None, *, raw_ical=None, device_id=None):
    new = row is None
    if (
        row is None
        and db.scalar(
            select(func.count())
            .select_from(CalendarEvent)
            .where(CalendarEvent.calendar_id == calendar.id)
        )
        >= 10000
    ):
        raise HTTPException(409, "Dieser Kalender enthält bereits 10000 Termine.")
    if (
        row
        and row.ical_data
        and event_data(row)["extendedProps"].get("series")
        and raw_ical is None
        and data.get("replace_series") != "1"
    ):
        raise HTTPException(
            422,
            "Eine Serienänderung muss ausdrücklich für die gesamte Serie bestätigt werden.",
        )
    if not access(db, actor, calendar, True):
        raise HTTPException(403)
    if row and str(row.version) != str(data.get("version")):
        raise HTTPException(409, "Der Termin wurde inzwischen geändert.")
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 200:
        raise HTTPException(422, "Titel mit höchstens 200 Zeichen angeben.")
    all_day = data.get("all_day") in (True, "1")
    try:
        if all_day:
            start = date.fromisoformat(data["start"])
            end = date.fromisoformat(data["end"]) + timedelta(days=1)
        else:
            start = datetime.fromisoformat(data["start"])
            end = datetime.fromisoformat(data["end"])
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError("Zeitzone fehlt")
        if end <= start or not 1970 <= start.year <= 2200 or end.year > 2201:
            raise ValueError()
    except (KeyError, ValueError, TypeError, OverflowError):
        raise HTTPException(
            422, "Gültigen Beginn und ein späteres Ende mit Zeitzone angeben."
        )
    row = row or CalendarEvent(calendar_id=calendar.id, uid=str(uuid.uuid4()) + "@takt")
    if row.calendar_id != calendar.id:
        raise HTTPException(404)
    if raw_ical is None:
        raw_org = data.get("org_id")
        try:
            target = int(raw_org) if raw_org else None
        except (ValueError, TypeError):
            raise HTTPException(422, "Zielgruppe prüfen.")
        if target and not org.allows(db, actor, target, "plan"):
            raise HTTPException(403)
        row.org_id = target
        row.include_children = data.get("include_children") in (True, "1")
    row.updated_at = utcnow()
    calendar.version += 1
    row.title = title
    row.starts_at = start.isoformat()
    row.ends_at = end.isoformat()
    row.all_day = all_day
    row.description = str(data.get("description", ""))[:10000]
    row.location = str(data.get("location", ""))[:500]
    from .calendar_recurrence import build_web_series, validate

    if raw_ical is not None:
        parsed, master, _ = validate(raw_ical)
        row.uid = str(master["UID"])
        row.ical_data = parsed.to_ical().decode()
    else:
        replacement = build_web_series(row, data)
        if (
            not replacement
            and row.ical_data
            and not event_data(row)["extendedProps"].get("series")
        ):
            parsed, master, _ = validate(row.ical_data)
            # A web edit of a client-created single event retains alarms and extra properties.
            for key, value in {
                "SUMMARY": row.title,
                "DESCRIPTION": row.description,
                "LOCATION": row.location,
                "DTSTART": start,
                "DTEND": end,
                "DTSTAMP": row.updated_at.replace(tzinfo=timezone.utc),
                "SEQUENCE": (row.version or 0) + 1,
            }.items():
                master.pop(key, None)
                master.add(key, value)
            replacement = parsed.to_ical().decode()
        row.ical_data = replacement
    row.version = (row.version or 0) + 1
    db.add(row)
    db.flush()
    audit(db, actor, calendar, "create" if new else "update", row, device_id)
    return row


def export(db, actor, calendar, events=None, channel="ics"):
    if not access(db, actor, calendar):
        raise HTTPException(403)
    if calendar.source != "free":
        from .calendar_sources import project, to_ics

        a = datetime(1970, 1, 1, tzinfo=timezone.utc)
        b = datetime(2200, 12, 31, tzinfo=timezone.utc)
        return to_ics(project(db, actor, calendar.source, a, b, channel=channel), calendar.title)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TAKT//Calendar//DE",
        "CALSCALE:GREGORIAN",
    ]
    for row in (
        events
        if events is not None
        else db.scalars(
            select(CalendarEvent).where(CalendarEvent.calendar_id == calendar.id)
        )
    ):
        if not event_access(db, actor, calendar, row):
            continue
        if row.ical_data:
            from icalendar import Calendar as ICalendar

            parsed = ICalendar.from_ical(row.ical_data)
            for component in parsed.subcomponents:
                if component.name in ("VTIMEZONE", "VEVENT"):
                    lines.extend(component.to_ical().decode().splitlines())
            continue
        lines += [
            "BEGIN:VEVENT",
            "UID:" + ics._esc(row.uid),
            "SEQUENCE:" + str(row.version),
            "DTSTAMP:" + ics._dt(row.updated_at),
            "SUMMARY:" + ics._esc(row.title),
            "DESCRIPTION:" + ics._esc(row.description),
            "LOCATION:" + ics._esc(row.location),
        ]
        if row.all_day:
            lines += [
                "DTSTART;VALUE=DATE:" + row.starts_at.replace("-", ""),
                "DTEND;VALUE=DATE:" + row.ends_at.replace("-", ""),
            ]
        else:
            from datetime import timezone

            lines += [
                "DTSTART:"
                + datetime.fromisoformat(row.starts_at)
                .astimezone(timezone.utc)
                .strftime("%Y%m%dT%H%M%SZ"),
                "DTEND:"
                + datetime.fromisoformat(row.ends_at)
                .astimezone(timezone.utc)
                .strftime("%Y%m%dT%H%M%SZ"),
            ]
        lines += ["END:VEVENT"]
    lines += ["END:VCALENDAR"]
    return "\r\n".join(ics._fold(line) for line in lines) + "\r\n"
