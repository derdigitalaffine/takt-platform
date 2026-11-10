"""Single free-calendar event workflows. Source events and series remain native."""
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, func
from . import calendars
from .calendar_models import Calendar, CalendarEvent
from .db import LOCAL_TZ

TOOLS = {'create_event', 'update_event', 'delete_event'}


def current(db, user, tool, rid):
    from .agent import require
    require(user, 'calendars')
    row = db.get(CalendarEvent, rid) if tool != 'create_event' else None
    cal = db.get(Calendar, row.calendar_id if row else rid) if tool == 'create_event' or row else None
    if not cal or (tool != 'create_event' and not row):
        raise HTTPException(404, 'Kalendertermin nicht gefunden.')
    if not calendars.access(db, user, cal, True) or (row and not calendars.event_access(db, user, cal, row)):
        raise HTTPException(403)
    if row and calendars.event_data(row)['extendedProps'].get('series'):
        raise HTTPException(422, 'Serientermine bitte im Kalenderclient bearbeiten. Der Agent ändert oder löscht keine gesamte Serie.')
    if tool == 'create_event' and db.scalar(select(func.count()).select_from(CalendarEvent).where(CalendarEvent.calendar_id == cal.id)) >= 10000:
        raise HTTPException(409, 'Dieser Kalender enthält bereits 10000 Termine.')
    return cal, row


def snapshot(cal, row):
    return [cal.version, row.org_id, row.include_children] if row else [cal.version]


def target(db, user, action):
    cal, row = current(db, user, action['tool'], action['id'])
    if action['version'] != (row.version if row else cal.version) or snapshot(cal, row) != action['calendar_snapshot']:
        raise HTTPException(409, 'Termin oder Kalenderfreigabe geändert. Bitte neu planen.')
    return cal, row


def normalize(db, user, raw, findings):
    tool = raw['tool']; rid = raw.get('id')
    kind = 'calendar' if tool == 'create_event' else 'event'
    if type(rid) is not int or not any(r.get('type') == kind and r['id'] == rid for r in findings):
        raise ValueError('Kalender bzw. Termin muss zuvor berechtigt gefunden werden.')
    cal, row = current(db, user, tool, rid)
    action = dict(tool=tool, id=rid, calendar_id=cal.id, version=row.version if row else cal.version,
                  calendar_snapshot=snapshot(cal, row))
    if tool == 'delete_event':
        return action
    for field, limit in [('title',200),('description',10000),('location',500)]:
        value = raw.get(field, getattr(row, field) if row else '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('Terminangaben prüfen.')
        action[field] = value.strip()
    if not action['title']:
        raise ValueError('Termintitel fehlt.')
    all_day = raw.get('all_day', row.all_day if row else False)
    if type(all_day) is not bool:
        raise ValueError('Ganztägig muss true oder false sein.')
    action['all_day'] = all_day
    for field, column in [('start','starts_at'),('end','ends_at')]:
        default = getattr(row, column) if row else ''
        if row and row.all_day and field == 'end':
            default = (date.fromisoformat(default) - timedelta(days=1)).isoformat()
        value = raw.get(field, default)
        try:
            if not isinstance(value, str) or not 1 <= len(value) <= 40:
                raise ValueError()
            parsed = date.fromisoformat(value) if all_day and len(value) == 10 else datetime.fromisoformat(value)
            if all_day and (type(parsed) is not date or len(value) != 10):
                raise ValueError()
            if not all_day and (type(parsed) is not datetime or parsed.tzinfo is None):
                raise ValueError()
            if not 1970 <= parsed.year <= 2200:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Ganztägige Termine benötigen Datumswerte; Uhrzeiten benötigen eine explizite ISO-Zeitzone.')
        action[field] = parsed.isoformat()
    start = date.fromisoformat(action['start']) if all_day else datetime.fromisoformat(action['start'])
    end = date.fromisoformat(action['end']) if all_day else datetime.fromisoformat(action['end'])
    if end < start or (end == start and not all_day):
        raise ValueError('Das Terminende muss nach dem Beginn liegen (ganztägig einschließlich Enddatum).')
    return action


def preview(db, action):
    cal = db.get(Calendar, action['calendar_id'])
    if action['tool'] == 'delete_event':
        row = db.get(CalendarEvent, action['id'])
        return f'Einzeltermin #{row.id} „{row.title}“ in Kalender „{cal.title}“ endgültig löschen: {row.starts_at} bis {row.ends_at}. Das Kalender-Audit bleibt erhalten.'
    previous = ''
    if action['tool'] == 'update_event':
        row = db.get(CalendarEvent, action['id'])
        previous = f'Bisher: {row.title}, {row.starts_at} bis {row.ends_at}.\n'
    return (f"Einzeltermin {'ändern' if previous else 'erstellen'} in Kalender „{cal.title}“: {action['title']}\n" + previous +
            f"Neu: {action['start']} bis {action['end']} {'(ganztägig, Enddatum einschließlich)' if action['all_day'] else ''}\n"
            f"Ort: {action['location'] or '–'}\nBeschreibung: {action['description'] or '–'}")


def execute(db, user, action):
    from .leave import lock
    lock(db)
    cal, row = target(db, user, action)
    label = preview(db, action)
    if action['tool'] == 'delete_event':
        rid = row.id
        calendars.delete_event(db, user, cal, row, action['version'], single_only=True)
    else:
        payload = dict(action)
        # Unsupported audience fields are preserved exactly on existing events.
        payload.update(org_id=row.org_id if row else None, include_children=row.include_children if row else True)
        row = calendars.save_event(db, user, cal, payload, row)
        rid = row.id
    return dict(label=label, target_id=rid, url='/kalender?ansicht=termine')


def search(db, user, spec):
    from .agent import require, _like
    require(user, 'calendars')
    bounds = []
    for key in ('start','end'):
        value = spec.get(key, '')
        try:
            if value and (not isinstance(value, str) or len(value) != 10):
                raise ValueError()
            parsed = date.fromisoformat(value) if value else None
            if parsed and not 1970 <= parsed.year <= 2200:
                raise ValueError()
            bounds.append(parsed)
        except (ValueError, TypeError):
            raise ValueError('Suchzeitraum als YYYY-MM-DD angeben.')
    a, b = bounds
    if a and b and (b < a or (b-a).days > 366):
        raise ValueError('Suchzeitraum mit höchstens 367 Tagen angeben.')
    phrase = str(spec.get('query') or '').strip()[:100]
    query = select(CalendarEvent).join(Calendar).where(Calendar.source == 'free')
    if phrase.lstrip('#').isdigit():
        query = query.where(CalendarEvent.id == int(phrase.lstrip('#')))
    else:
        query = query.where(CalendarEvent.title.ilike(_like(phrase), escape='\\'))
    out = []
    for row in db.scalars(query.order_by(CalendarEvent.starts_at, CalendarEvent.id)):
        cal = db.get(Calendar, row.calendar_id)
        if not calendars.event_access(db, user, cal, row):
            continue
        start = datetime.combine(date.fromisoformat(row.starts_at), datetime.min.time(), LOCAL_TZ) if row.all_day else datetime.fromisoformat(row.starts_at)
        end = datetime.combine(date.fromisoformat(row.ends_at), datetime.min.time(), LOCAL_TZ) if row.all_day else datetime.fromisoformat(row.ends_at)
        if a and end <= datetime.combine(a, datetime.min.time(), LOCAL_TZ):
            continue
        if b and start >= datetime.combine(b + timedelta(days=1), datetime.min.time(), LOCAL_TZ):
            continue
        series = bool(calendars.event_data(row)['extendedProps'].get('series'))
        out.append(dict(type='event',id=row.id,title=row.title,calendar_id=cal.id,calendar_title=cal.title,
                        start=row.starts_at,end=row.ends_at,all_day=row.all_day,end_exclusive=row.all_day,
                        editable=calendars.access(db,user,cal,True) and not series,series=series,
                        url='/kalender?ansicht=termine'))
        if len(out) == 20:
            break
    return out


def local_timestamp(day, clock, zone_name, original=None):
    """Reject nonexistent/ambiguous edited wall times; preserve an unchanged explicit offset."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        zone = ZoneInfo(zone_name)
        naive = datetime.fromisoformat(day + 'T' + clock)
        if naive.tzinfo is not None:
            raise ValueError()
        old = datetime.fromisoformat(original) if original else None
        if old and old.tzinfo and len(clock) == 5 and old.astimezone(zone).replace(second=0, microsecond=0, tzinfo=None) == naive:
            return old.isoformat()
        first, second = [naive.replace(tzinfo=zone,fold=i) for i in (0,1)]
        valid = [v for v in (first,second) if v.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive]
        if not valid:
            raise ValueError()
        if first.utcoffset() != second.utcoffset() and len(valid) == 2:
            old = datetime.fromisoformat(original) if original else None
            if old and old.astimezone(zone).replace(tzinfo=None) == naive:
                return old.isoformat()
            raise ValueError()
        return valid[0].isoformat()
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise HTTPException(422, 'Uhrzeit oder Zeitzone ist ungültig bzw. bei der Zeitumstellung nicht eindeutig. Bitte einen eindeutigen Zeitpunkt wählen oder neu mit UTC-Offset planen.')
