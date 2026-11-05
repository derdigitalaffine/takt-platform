"""Bounded expansion of recurring free-calendar events, preserving client exceptions."""

from datetime import datetime, date, timedelta, timezone
from icalendar import Calendar as ICalendar
from dateutil.rrule import rrulestr
from fastapi import HTTPException
from . import calendars


def aware(value):
    if not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if value.tzinfo is None:
        raise ValueError("Zeitzone fehlt")
    return value


def validate(raw):
    """A resource is one UID, with a master and optional same-UID exceptions."""
    try:
        parsed = ICalendar.from_ical(raw)
        events = parsed.walk("VEVENT")
        if not 1 <= len(events) <= 1000 or parsed.walk("VTODO"):
            raise ValueError()
        masters = [e for e in events if not e.get("RECURRENCE-ID")]
        if len(masters) != 1:
            raise ValueError()
        master = masters[0]
        uid = str(master["UID"])
        if not uid or len(uid) > 100 or any(ord(c) < 32 for c in uid):
            raise ValueError()
        for event in events:
            if str(event["UID"]) != uid:
                raise ValueError()
            start = event.decoded("DTSTART")
            end = event.decoded("DTEND")
            if type(start) != type(end) or aware(end) <= aware(start):
                raise ValueError()
            if not 1970 <= start.year <= 2200 or end.year > 2201:
                raise ValueError()
            for rule in [event.get("RRULE")] if event.get("RRULE") else []:
                if len(rule.get("FREQ", [])) != 1 or str(rule["FREQ"][0]) not in (
                    "DAILY",
                    "WEEKLY",
                    "MONTHLY",
                    "YEARLY",
                ):
                    raise ValueError()
                if any(key in rule for key in ("BYSECOND", "BYMINUTE", "BYHOUR")):
                    raise ValueError()
                if rule.get("COUNT") and (
                    len(rule["COUNT"]) != 1 or not 1 <= int(rule["COUNT"][0]) <= 10000
                ):
                    raise ValueError()
                if rule.get("INTERVAL") and not 1 <= int(rule["INTERVAL"][0]) <= 365:
                    raise ValueError()
                rrulestr(
                    rule.to_ical().decode(),
                    dtstart=(
                        datetime.combine(start, datetime.min.time())
                        if not isinstance(start, datetime)
                        else aware(start)
                    ),
                )
        return parsed, master, events
    except Exception as exc:
        raise HTTPException(
            422,
            "Gültigen Einzeltermin oder eine tägliche, wöchentliche, monatliche oder jährliche Serie mit höchstens 1000 Ausnahmen angeben.",
        ) from exc


def occurrences(row, start, end):
    row_start = (
        date.fromisoformat(row.starts_at)
        if row.all_day
        else datetime.fromisoformat(row.starts_at)
    )
    row_end = (
        date.fromisoformat(row.ends_at)
        if row.all_day
        else datetime.fromisoformat(row.ends_at)
    )
    overlaps = aware(row_start) < aware(end) and aware(row_end) > aware(start)
    if not row.ical_data:
        return [calendars.event_data(row)] if overlaps else []
    parsed, master, events = validate(row.ical_data)
    if not master.get("RRULE") and not master.get("RDATE") and len(events) == 1:
        return [calendars.event_data(row)] if overlaps else []
    begins = master.decoded("DTSTART")
    finishes = master.decoded("DTEND")
    all_day = not isinstance(begins, datetime)
    duration = aware(finishes) - aware(begins)
    first = aware(begins)
    window_start = aware(start).astimezone(first.tzinfo)
    window_end = aware(end).astimezone(first.tzinfo)
    if window_end <= window_start or window_end - window_start > timedelta(days=400):
        raise HTTPException(422, "Sichtbaren Kalenderzeitraum begrenzen.")
    overrides = {
        aware(e.decoded("RECURRENCE-ID")): e for e in events if e.get("RECURRENCE-ID")
    }
    exclusions = set()
    exdates = master.get("EXDATE", [])
    if not isinstance(exdates, list):
        exdates = [exdates]
    for ex in exdates:
        exclusions.update(aware(item.dt) for item in ex.dts)
    if master.get("RRULE"):
        import warnings

        base = first.replace(tzinfo=None) if all_day else first
        lower = (
            (window_start - duration).replace(tzinfo=None)
            if all_day
            else window_start - duration
        )
        upper = window_end.replace(tzinfo=None) if all_day else window_end
        rule = rrulestr(master["RRULE"].to_ical().decode(), dtstart=base)
        until_values = master["RRULE"].get("UNTIL", [])
        cap = upper
        if until_values:
            original = aware(until_values[0]).astimezone(first.tzinfo)
            if all_day:
                original = original.replace(tzinfo=None)
            cap = min(cap, original)
        # Bound even impossible BYxxx combinations; never scan to dateutil's year limit.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            bounded = rule.replace(until=cap)
        starts = [
            value.replace(tzinfo=timezone.utc) if all_day else aware(value)
            for value in bounded.between(lower, upper, inc=True)
        ]
    else:
        starts = [first]
    rdates = master.get("RDATE", [])
    if not isinstance(rdates, list):
        rdates = [rdates]
    for rd in rdates:
        starts.extend(aware(item.dt) for item in rd.dts)
    # An overridden instance can be moved into the visible window from elsewhere.
    starts.extend(overrides)
    result = []
    base = calendars.event_data(row)
    for occurrence in sorted(set(starts)):
        if occurrence in exclusions:
            continue
        override = overrides.get(occurrence)
        event = override if override is not None else master
        if str(event.get("STATUS", "")) == "CANCELLED":
            continue
        a = aware(override.decoded("DTSTART")) if override is not None else occurrence
        b = aware(override.decoded("DTEND")) if override is not None else a + duration
        if b <= window_start or a >= window_end:
            continue
        data = dict(base, extendedProps=dict(base["extendedProps"]))
        data.update(
            id=str(row.id) + ":" + occurrence.isoformat(),
            start=a.date().isoformat() if all_day else a.isoformat(),
            end=b.date().isoformat() if all_day else b.isoformat(),
            title=str(event.get("SUMMARY", row.title)),
        )
        data["extendedProps"].update(
            seriesId=row.id,
            series=True,
            description=str(event.get("DESCRIPTION", "")),
            location=str(event.get("LOCATION", "")),
        )
        result.append(data)
        if len(result) > 1000:
            raise HTTPException(507, "Zu viele Serientermine im angefragten Zeitraum.")
    return result


def build_web_series(row, data):
    from icalendar import Event, Timezone
    from zoneinfo import ZoneInfo

    frequency = str(data.get("repeat", "")).upper()
    if frequency in ("", "NONE"):
        return ""
    if frequency not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        raise HTTPException(422, "Wiederholung prüfen.")
    try:
        count = int(data.get("repeat_count", 10))
        if not 1 <= count <= 1000:
            raise ValueError()
        start = (
            date.fromisoformat(row.starts_at)
            if row.all_day
            else datetime.fromisoformat(row.starts_at)
        )
        end = (
            date.fromisoformat(row.ends_at)
            if row.all_day
            else datetime.fromisoformat(row.ends_at)
        )
        tz = ZoneInfo(str(data.get("time_zone", "Europe/Berlin")))
        if not row.all_day:
            start = start.astimezone(tz)
            end = end.astimezone(tz)
        skips = [
            date.fromisoformat(value.strip())
            for value in str(data.get("skip_dates", "")).replace("\n", ",").split(",")
            if value.strip()
        ]
        if len(skips) > 1000:
            raise ValueError()
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(
            422, "Serienanzahl, Zeitzone und Ausnahmetage prüfen."
        ) from e
    cal = ICalendar()
    cal.add("version", "2.0")
    cal.add("prodid", "-//TAKT//Calendar//DE")
    if not row.all_day:
        cal.add_component(
            Timezone.from_tzinfo(
                tz,
                first_date=date(max(1970, start.year - 1), 1, 1),
                last_date=date(2200, 12, 31),
            )
        )
    event = Event()
    event.add("uid", row.uid)
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("dtstamp", row.updated_at.replace(tzinfo=timezone.utc))
    event.add("summary", row.title)
    event.add("description", row.description)
    event.add("location", row.location)
    event.add("rrule", {"freq": frequency, "count": count})
    for day in skips:
        event.add(
            "exdate",
            (
                day
                if row.all_day
                else datetime.combine(day, start.timetz()).replace(tzinfo=tz)
            ),
        )
    cal.add_component(event)
    raw = cal.to_ical().decode()
    validate(raw)
    return raw


def window(start=None, end=None):
    try:
        a = (
            datetime.fromisoformat(start.replace("Z", "+00:00"))
            if start
            else datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc)
        )
        b = (
            datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end
            else datetime(a.year + 1, 1, 1, tzinfo=timezone.utc)
        )
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
        if b.tzinfo is None:
            b = b.replace(tzinfo=timezone.utc)
        if not 0 < (b - a).total_seconds() <= 400 * 86400:
            raise ValueError()
        return a, b
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Kalenderzeitraum prüfen.")
