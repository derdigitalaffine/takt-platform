"""Shared CalDAV read responses and bounded WebDAV synchronization snapshots.

RFC 4791 calendar-query/multiget and RFC 6578 sync-collection; no scheduling service.
"""

import copy
import hashlib
import json
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote
from xml.etree import ElementTree as ET
from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from icalendar import Calendar as ICalendar
from .calendar_models import CalendarSyncState

D = "DAV:"
C = "urn:ietf:params:xml:ns:caldav"
CS = "http://calendarserver.org/ns/"
DAV = "1, calendar-access, sync-collection"


def sub(parent, ns, name, text=None):
    el = ET.SubElement(parent, "{" + ns + "}" + name)
    if text is not None:
        el.text = str(text)
    return el


def node(ns, tag, **attrs):
    return ET.Element("{" + ns + "}" + tag, attrs)


def href(value):
    el = node(D, "href")
    el.text = value
    return el


def error(name, status=403):
    root = node(D, "error")
    sub(root, D, name)
    return Response(
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
        status,
        media_type="application/xml",
        headers={"Cache-Control": "no-store"},
    )


def multistatus(entries, requested=None, missing=(), sync_token=None):
    root = node(D, "multistatus")
    wanted = requested.find("{DAV:}prop") if requested is not None else None
    wanted_tags = [p.tag for p in wanted] if wanted is not None else None
    for url, properties in entries:
        response = sub(root, D, "response")
        sub(response, D, "href", url)
        values = {"{" + ns + "}" + name: value for ns, name, value in properties}
        selected = list(values) if wanted_tags is None else wanted_tags
        for known, status in [(True, "200 OK"), (False, "404 Not Found")]:
            tags = [t for t in selected if (t in values) == known]
            if not tags:
                continue
            stat = sub(response, D, "propstat")
            prop = sub(stat, D, "prop")
            for tag in tags:
                element = ET.SubElement(prop, tag)
                value = values.get(tag)
                if known:
                    if isinstance(value, ET.Element):
                        element.append(copy.deepcopy(value))
                    elif isinstance(value, list):
                        element.extend(copy.deepcopy(value))
                    elif value is not None:
                        element.text = str(value)
            sub(stat, D, "status", "HTTP/1.1 " + status)
    for url in missing:
        response = sub(root, D, "response")
        sub(response, D, "href", url)
        sub(response, D, "status", "HTTP/1.1 404 Not Found")
    if sync_token:
        sub(root, D, "sync-token", sync_token)
    return Response(
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
        207,
        media_type="application/xml",
        headers={"DAV": DAV, "Cache-Control": "no-store"},
    )


def reports():
    result = []
    for ns, name in [
        (C, "calendar-query"),
        (C, "calendar-multiget"),
        (D, "sync-collection"),
    ]:
        supported = node(D, "supported-report")
        sub(sub(supported, D, "report"), ns, name)
        result.append(supported)
    return result


def collection_props(calendar, principal, can_write, objects):
    privilege = node(D, "privilege")
    sub(privilege, D, "read")
    privileges = [privilege]
    if can_write:
        write = node(D, "privilege")
        sub(write, D, "write")
        privileges.append(write)
    return [
        (D, "displayname", calendar.title),
        (D, "resourcetype", [node(D, "collection"), node(C, "calendar")]),
        (D, "owner", href(principal)),
        (D, "current-user-principal", href(principal)),
        (D, "current-user-privilege-set", privileges),
        (D, "supported-report-set", reports()),
        (C, "supported-calendar-component-set", node(C, "comp", name="VEVENT")),
        (
            C,
            "supported-calendar-data",
            node(
                C,
                "calendar-data",
                **{"content-type": "text/calendar", "version": "2.0"}
            ),
        ),
        (C, "max-resource-size", "262144"),
        (C, "calendar-description", calendar.title),
        (
            CS,
            "getctag",
            hashlib.sha256(
                json.dumps(
                    {k: v[1] for k, v in objects.items()}, sort_keys=True
                ).encode()
            ).hexdigest(),
        ),
    ]


def resource_props(content, tag):
    return [
        (D, "getetag", tag),
        (D, "getcontenttype", "text/calendar; charset=utf-8"),
        (D, "getcontentlength", len(content.encode())),
        (D, "resourcetype", None),
        (C, "calendar-data", content),
    ]


def snapshot(db, device, cid, objects):
    state = json.dumps(
        {name: value[1] for name, value in objects.items()}, sort_keys=True
    )
    rows = list(
        db.scalars(
            select(CalendarSyncState)
            .where(
                CalendarSyncState.device_id == device.id,
                CalendarSyncState.calendar_id == cid,
            )
            .order_by(CalendarSyncState.id.desc())
        )
    )
    if rows and rows[0].state_json == state:
        return rows[0].token
    token = "urn:takt:sync:" + secrets.token_hex(24)
    db.add(
        CalendarSyncState(
            device_id=device.id, calendar_id=cid, token=token, state_json=state
        )
    )
    for row in rows[19:]:
        db.delete(row)
    db.commit()
    return token


def query_filter(tree):
    """Reject unsupported filters instead of silently returning the wrong event set."""
    filt = tree.find("{" + C + "}filter")
    if filt is None:
        return None
    components = filt.findall("{" + C + "}comp-filter")
    if len(components) != 1 or components[0].get("name") != "VCALENDAR":
        raise HTTPException(403, "Unsupported calendar filter")
    outer = components[0]
    inner = outer.findall("{" + C + "}comp-filter")
    if not inner:
        return None
    if len(inner) != 1 or inner[0].get("name") != "VEVENT":
        raise HTTPException(403, "Unsupported calendar component")
    for element in inner[0]:
        if element.tag != "{" + C + "}time-range":
            raise HTTPException(403, "Unsupported calendar filter")
    bounds = inner[0].find("{" + C + "}time-range")
    if bounds is None:
        return None
    try:
        begin = datetime.strptime(
            bounds.get("start", "19700101T000000Z"), "%Y%m%dT%H%M%SZ"
        ).replace(tzinfo=timezone.utc)
        finish = datetime.strptime(
            bounds.get("end", "22001231T000000Z"), "%Y%m%dT%H%M%SZ"
        ).replace(tzinfo=timezone.utc)
        if finish <= begin:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "Invalid time range")
    return begin, finish


def intersects(content, bounds):
    if bounds is None:
        return True
    from types import SimpleNamespace
    from datetime import timedelta
    from .calendar_recurrence import occurrences, aware

    parsed = ICalendar.from_ical(content)
    events = parsed.walk("VEVENT")
    master = next(e for e in events if not e.get("RECURRENCE-ID"))
    a, b = bounds
    if not master.get("RRULE") and not master.get("RDATE") and len(events) == 1:
        return (
            aware(master.decoded("DTSTART")) < b and aware(master.decoded("DTEND")) > a
        )
    row = SimpleNamespace(
        id=0,
        ical_data=content,
        uid=str(master["UID"]),
        title=str(master.get("SUMMARY", "")),
        description="",
        location="",
        starts_at=master.decoded("DTSTART").isoformat(),
        ends_at=master.decoded("DTEND").isoformat(),
        all_day=not isinstance(master.decoded("DTSTART"), datetime),
        version=1,
    )
    # Expansion stays bounded even when the client requests several years.
    cursor = a
    while cursor < b:
        end = min(cursor + timedelta(days=366), b)
        for item in occurrences(row, cursor, end):
            start = datetime.fromisoformat(item["start"])
            stop = datetime.fromisoformat(item["end"])
            if aware(start) < b and aware(stop) > a:
                return True
        cursor = end
    return False


def report(db, device, cal, base, objects, tree):
    if tree is None:
        raise HTTPException(400)
    if tree.tag == "{" + D + "}sync-collection":
        if tree.findtext("{DAV:}sync-level") != "1":
            raise HTTPException(403)
        token = tree.findtext("{DAV:}sync-token") or ""
        old = {}
        if token:
            row = db.scalar(
                select(CalendarSyncState).where(
                    CalendarSyncState.device_id == device.id,
                    CalendarSyncState.calendar_id == cal.id,
                    CalendarSyncState.token == token,
                )
            )
            if not row:
                return error("valid-sync-token")
            old = json.loads(row.state_json)
        changed = [
            (base + name, resource_props(*value))
            for name, value in objects.items()
            if old.get(name) != value[1]
        ]
        missing = [base + name for name in old if name not in objects]
        token = snapshot(db, device, cal.id, objects)
        return multistatus(changed, tree, missing, token)
    if tree.tag == "{" + C + "}calendar-multiget":
        requested = {
            unquote(urlsplit(e.text or "").path) for e in tree.findall("{DAV:}href")
        }
        entries = [
            (base + name, resource_props(*value))
            for name, value in objects.items()
            if base + name in requested
        ]
        missing = requested - {url for url, _ in entries}
        return multistatus(entries, tree, sorted(missing))
    if tree.tag == "{" + C + "}calendar-query":
        bounds = query_filter(tree)
        return multistatus(
            [
                (base + name, resource_props(*value))
                for name, value in objects.items()
                if intersects(value[0], bounds)
            ],
            tree,
        )
    raise HTTPException(403, "Unsupported report")
