"""Central, fail-closed integration rules for appointment booking and calendar sources.

There is no shadow appointment calendar: booking rows stay canonical. Personal free
calendars and directly-owned meetings are used only as busy-time sources when a
booking page explicitly enables conflict checking.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from .db import LOCAL_TZ, to_local

log = logging.getLogger(__name__)
PRIVACY = ("inherit", "restricted", "busy")
SCOPES = ("personal", "meetings")


def options(page) -> dict:
    try:
        raw = json.loads(page.integration_json or "{}")
    except (ValueError, TypeError):
        raw = {}
    return raw if isinstance(raw, dict) else {}


def configured(page, flag: str, default=False) -> bool:
    value = options(page).get(flag, default)
    return value is True


def calendar_visibility(booking, *, channel="web", can_edit=False, responsible=False) -> str:
    """Whether an event may expose the guest's name in a given calendar channel.

    An event may be visible as occupied without granting booking-record access.
    External feeds are always busy-only, even for the owning employee, by default.
    """
    if channel in ("ics", "caldav"):
        return "busy"
    if booking.type and booking.type.privacy_mode in ("restricted", "busy"):
        return "busy" if booking.type.privacy_mode == "busy" or not responsible else "detail"
    return "detail" if can_edit or responsible else "busy"


def _utc(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time(), tzinfo=LOCAL_TZ)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=LOCAL_TZ)
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    raise ValueError("Ungültige Kalenderzeit")


def internal_busy(db, user_id: int, start: datetime, end: datetime, *, scopes=None, exclude_meeting_id=None):
    """Relevant occupied intervals (UTC, naive), without copying personal event data.

    Only free calendars *owned by this user* count, never arbitrary organization
    calendars shared for information. Transparent/cancelled events do not block.
    Recurrence expansion is bounded to 180-day chunks as required by the calendar core.
    """
    from .calendar_models import Calendar, CalendarEvent
    from .calendar_recurrence import occurrences
    from .db import Meeting

    selected = set(scopes or SCOPES).intersection(SCOPES)
    busy = []
    if start >= end or not selected:
        return busy

    if "meetings" in selected:
        meetings = db.scalars(
            select(Meeting).where(Meeting.owner_id == user_id,
                                  Meeting.starts_at.is_not(None),
                                  Meeting.starts_at < end,
                                  Meeting.cancelled_at.is_(None))
        ).all()
        for row in meetings:
            if row.id == exclude_meeting_id:
                continue
            finish = row.starts_at + timedelta(minutes=row.duration_minutes or 0)
            if finish > start:
                busy.append((row.starts_at, finish))

    if "personal" not in selected:
        return busy
    calendar_ids = list(db.scalars(select(Calendar.id).where(
        Calendar.owner_id == user_id, Calendar.source == "free",
        Calendar.visibility == "private"
    )))
    if not calendar_ids:
        return busy
    events = list(db.scalars(select(CalendarEvent).where(CalendarEvent.calendar_id.in_(calendar_ids))))
    cursor = start.replace(tzinfo=timezone.utc)
    stop = end.replace(tzinfo=timezone.utc)
    while cursor < stop:
        cut = min(cursor + timedelta(days=180), stop)
        for event in events:
            try:
                # Suppress transparent and cancelled VEVENTs, including user-created
                # import sources; a free informational event is not a busy slot.
                if event.ical_data:
                    from icalendar import Calendar as ICalendar
                    parsed = ICalendar.from_ical(event.ical_data)
                    master = next(iter(parsed.walk("VEVENT")), None)
                    if master and (str(master.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT"
                                   or str(master.get("STATUS", "")).upper() == "CANCELLED"):
                        continue
                for occurrence in occurrences(event, cursor, cut):
                    a, b = _utc(datetime.fromisoformat(occurrence["start"]) if not occurrence["allDay"] else
                                date.fromisoformat(occurrence["start"][:10])), \
                           _utc(datetime.fromisoformat(occurrence["end"]) if not occurrence["allDay"] else
                                date.fromisoformat(occurrence["end"][:10]))
                    if a < end and b > start:
                        busy.append((a, b))
            except (ValueError, TypeError, KeyError, StopIteration) as exc:
                # A broken entry must never lead to an unsafe bookable slot.
                log.warning("Kalendereintrag %s für Verfügbarkeit unlesbar: %s", event.id, exc)
                busy.append((start, end))
        cursor = cut
    return busy


def conflicts(db, page, user_id: int | None, start: datetime, end: datetime, *, keep=None) -> bool:
    if not user_id or not configured(page, "calendar_conflicts"):
        return False
    sources = options(page).get("conflict_sources", list(SCOPES))
    if not isinstance(sources, list):
        sources = list(SCOPES)
    # Bookings are canonical, so the meeting created for the booking being
    # rescheduled must not conflict with its own new interval.
    return any(a < end and start < b for a, b in internal_busy(
        db, user_id, start, end, scopes=sources,
        exclude_meeting_id=keep.meeting_id if keep else None))
