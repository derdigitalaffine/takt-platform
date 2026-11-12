"""Privacy-aware event suggestions for the central Digital Signage campaign editor.

This is a read-only discovery aid. It never copies internal event titles to
public signage, creates campaigns or grants new calendar permissions.
"""
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from . import calendar_recurrence, signage_passive, signage
from .calendar_models import Calendar, CalendarEvent
from .signage_models import SignageCampaign

# Match strong, explicit civic-event phrases only. An ordinary private
# appointment, staff meeting or association board election is not suggested.
PATTERNS = (
    ("postal", re.compile(r"\bbriefwahl(?:stelle|büro|buero|unterlagen|annahme)?\b", re.I)),
    ("poll", re.compile(r"\b(?:wahlraum|wahllokal|wahltag|stimmabgabe)\b", re.I)),
    ("council", re.compile(
        r"\b(?:gemeinderatssitzung|stadtratssitzung|verbandsgemeinderatssitzung|"
        r"ratssitzung|ausschusssitzung|ortsgemeinderatssitzung)\b", re.I)),
    ("event", re.compile(
        r"\b(?:bürgerversammlung|buergerversammlung|einwohnerversammlung|"
        r"bürgerinformationsveranstaltung|buergerinformationsveranstaltung|"
        r"öffentliche\s+veranstaltung|oeffentliche\s+veranstaltung)\b", re.I)),
)


def classify_title(title: str):
    text = str(title or "")[:200]
    for preset, pattern in PATTERNS:
        if pattern.search(text):
            return preset
    return None


def suggest(db, actor, now=None, *, limit=12, horizon_days=45):
    """Upcoming, not-yet-linked candidates from source-ACL-readable calendars.

    Recurrence exceptions and cancellations are respected. The result is
    bounded to keep dashboard loads predictable in large organizations.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    finish = moment + timedelta(days=max(1, min(horizon_days, 120)))
    linked = set(db.scalars(select(SignageCampaign.event_id).where(
        SignageCampaign.event_id.is_not(None))))
    calendars = list(db.scalars(select(Calendar).where(
        Calendar.source == "free").order_by(Calendar.id).limit(300)))
    available = {row.id: row for row in calendars}
    if not available:
        return []
    rows = db.scalars(select(CalendarEvent).where(
        CalendarEvent.calendar_id.in_(available)).order_by(
        CalendarEvent.updated_at.desc(), CalendarEvent.id.desc()).limit(800)).all()
    suggestions = []
    for row in rows:
        if row.id in linked:
            continue
        preset = classify_title(row.title)
        if not preset or not signage_passive.source_access(
                db, actor, row, SimpleNamespace(org_id=None)):
            continue
        try:
            if row.ical_data:
                _, master, components = calendar_recurrence.validate(row.ical_data)
                if len(components) == 1 and str(master.get("STATUS", "")).upper() == "CANCELLED":
                    continue
            instances = calendar_recurrence.occurrences(row, moment, finish)
            upcoming = []
            for instance in instances[:60]:
                start = signage._calendar_date(instance["start"])
                end = signage._calendar_date(instance["end"])
                if end > moment and start < finish:
                    upcoming.append((start, end))
            if not upcoming:
                continue
            start, end = min(upcoming)
        except (ValueError, TypeError, OverflowError, HTTPException):
            continue
        suggestions.append({
            "event_id": row.id,
            "calendar_id": row.calendar_id,
            "source_title": row.title,
            "calendar_title": available[row.calendar_id].title,
            "preset": preset,
            "public_title": signage_passive.PRESETS[preset][0],
            "start": start,
            "end": end,
        })
    return sorted(suggestions, key=lambda item: (item["start"], item["event_id"]))[:max(1, min(limit, 30))]
