"""CalDAV collections for free calendar events, authenticated by scoped device keys.

Business calendars remain read-only projections. Free-calendar series preserve
client-supplied recurrence and exceptions through the central event service.
"""

import base64, binascii, re
from datetime import date, datetime, timezone
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from fastapi import Request, Depends, HTTPException
from fastapi.responses import Response, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from icalendar import Calendar as ICalendar
from .main import app, get_db
from .db import utcnow
from .calendar_models import CalendarEvent, CalendarDeviceScope
from . import calendar_devices as devices, calendars, leave, dav_protocol as protocol

D = "DAV:"
C = "urn:ietf:params:xml:ns:caldav"
CS = "http://calendarserver.org/ns/"
ET.register_namespace("d", D)
ET.register_namespace("c", C)
ET.register_namespace("cs", CS)


def sub(parent, namespace, name, text=None):
    el = ET.SubElement(parent, "{" + namespace + "}" + name)
    if text is not None:
        el.text = str(text)
    return el


def etag(event):
    return '"takt-' + str(event.id) + "-" + str(event.version) + '"'


def auth(request, db):
    if request.url.scheme != "https":
        raise HTTPException(400, "Kalendergeräte benötigen eine HTTPS-Verbindung.")
    header = request.headers.get("authorization", "")
    try:
        if not header.startswith("Basic ") or len(header) > 2048:
            raise ValueError()
        user, password = (
            base64.b64decode(header[6:], validate=True).decode().split(":", 1)
        )
    except (ValueError, UnicodeError, binascii.Error):
        raise HTTPException(
            401,
            headers={
                "WWW-Authenticate": 'Basic realm="Takt Calendar", charset="UTF-8"'
            },
        )
    result = devices.authenticate(db, user, password)
    if not result:
        raise HTTPException(
            401, headers={"WWW-Authenticate": 'Basic realm="Takt Calendar"'}
        )
    device, user = result
    device.last_used = utcnow()
    db.commit()
    return device, user


async def xml_body(request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 262144:
            raise HTTPException(413)
    return bytes(body)


def parse_xml(body):
    if not body:
        return None
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise HTTPException(400)
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        raise HTTPException(400, "Ungültige XML-Anfrage.")


def href(value):
    node = ET.Element("{DAV:}href")
    node.text = value
    return node


def collection(calendar=False):
    node = ET.Element("{DAV:}collection")
    # resourcetype has collection + calendar siblings, built separately below.
    return node


@app.api_route("/.well-known/caldav", methods=["GET", "PROPFIND"])
def discovery():
    return RedirectResponse("/caldav/", status_code=307)


@app.api_route("/caldav/", methods=["OPTIONS", "PROPFIND"])
@app.api_route(
    "/caldav/{path:path}",
    methods=["OPTIONS", "PROPFIND", "REPORT", "GET", "HEAD", "PUT", "DELETE"],
)
async def dav(request: Request, path: str = "", db: Session = Depends(get_db)):
    device, user = auth(request, db)
    method = request.method
    principal = "/caldav/principals/" + device.username + "/"
    home = "/caldav/home/" + device.username + "/"
    if method == "OPTIONS":
        return Response(
            status_code=204,
            headers={
                "DAV": protocol.DAV,
                "Allow": "OPTIONS, PROPFIND, REPORT, GET, HEAD, PUT, DELETE",
            },
        )
    if method == "PROPFIND" and path in (
        "",
        "principals/" + device.username + "/",
        "home/" + device.username + "/",
    ):
        if request.headers.get("depth", "0") not in ("0", "1"):
            raise HTTPException(403)
        request_tree = parse_xml(await xml_body(request))
        entries = []
        current = "/caldav/" + path
        props = [
            (D, "displayname", "Takt Calendar"),
            (D, "current-user-principal", href(principal)),
            (D, "resourcetype", collection()),
        ]
        if path.startswith("principals/"):
            props.append((C, "calendar-home-set", href(home)))
            props[2] = (D, "resourcetype", protocol.node(D, "principal"))
            props.append((D, "principal-URL", href(principal)))
        entries.append((current, props))
        if path.startswith("home/") and request.headers.get("depth", "0") == "1":
            for scope in db.scalars(
                select(CalendarDeviceScope).where(
                    CalendarDeviceScope.device_id == device.id
                )
            ):
                cal = devices.allowed(db, device, user, scope.calendar_id)
                if cal:
                    kind = ET.Element("{DAV:}collection")
                    entries.append(
                        (
                            "/caldav/calendars/" + str(cal.id) + "/",
                            [
                                (D, "displayname", cal.title),
                                (D, "resourcetype", kind),
                                (C, "calendar-description", cal.title),
                            ],
                        )
                    )
        result = protocol.multistatus(entries, request_tree)
        # Add calendar resource types alongside DAV collection types.
        tree = ET.fromstring(result.body)
        for response in tree:
            url = response.find("{DAV:}href").text
            if "/calendars/" in url:
                kind = response.find(".//{DAV:}resourcetype")
                if kind is not None:
                    ET.SubElement(kind, "{" + C + "}calendar")
        return Response(
            ET.tostring(tree, encoding="utf-8", xml_declaration=True),
            207,
            media_type="application/xml",
            headers={"DAV": protocol.DAV, "Cache-Control": "no-store"},
        )
    match = re.fullmatch(r"calendars/(\d+)/(?:([^/]+))?", path)
    if not match:
        raise HTTPException(404)
    cid = int(match[1])
    name = match[2]
    cal = devices.allowed(db, device, user, cid, method in ("PUT", "DELETE"))
    if not cal:
        raise HTTPException(403)
    if name and (
        len(name) > 200
        or not name.endswith(".ics")
        or not re.fullmatch(r"[A-Za-z0-9_.@-]+", name)
    ):
        raise HTTPException(400)
    if method in ("PUT", "DELETE"):
        if not name:
            raise HTTPException(405)
        body = await xml_body(request) if method == "PUT" else b""
        leave.lock(db)
        # Rights and device revocation are rechecked after the serialization lock.
        db.refresh(device)
        if (
            device.revoked
            or device.expires_at
            and device.expires_at <= utcnow()
            or not devices.allowed(db, device, user, cid, True)
        ):
            raise HTTPException(403)
        event = db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.calendar_id == cid, CalendarEvent.dav_name == name
            )
        )
        if event and not calendars.event_access(db, user, cal, event):
            raise HTTPException(403)
        if event:
            if request.headers.get("if-match") != etag(event):
                raise HTTPException(412)
        elif method == "DELETE":
            raise HTTPException(404)
        elif request.headers.get("if-none-match") != "*":
            raise HTTPException(428, "If-None-Match: * erforderlich.")
        if method == "DELETE":
            calendars.audit(db, user, cal, "delete", event, device.id)
            db.delete(event)
            cal.version += 1
            db.commit()
            return Response(status_code=204)
        if b"<!DOCTYPE" in body.upper() or len(body) > 262144:
            raise HTTPException(400)
        try:
            from .calendar_recurrence import validate

            parsed, ve, events = validate(body)
            start = ve.decoded("DTSTART")
            end = ve.decoded("DTEND")
            uid = str(ve["UID"])
            if not uid or len(uid) > 100:
                raise ValueError()
            all_day = isinstance(start, date) and not isinstance(start, datetime)
            if all_day:
                from datetime import timedelta

                end = end - timedelta(days=1)
            data = dict(
                title=str(ve.get("SUMMARY", "")),
                description=str(ve.get("DESCRIPTION", "")),
                location=str(ve.get("LOCATION", "")),
                start=start.isoformat(),
                end=end.isoformat(),
                all_day=all_day,
                version=event.version if event else None,
            )
        except Exception:
            raise HTTPException(
                422,
                "Gültigen Termin oder unterstützte Serie mit Beginn und Ende angeben.",
            )
        if event and event.uid != uid:
            raise HTTPException(409, "UID darf nicht geändert werden.")
        duplicate = db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.calendar_id == cid, CalendarEvent.uid == uid
            )
        )
        if duplicate and (not event or duplicate.id != event.id):
            raise HTTPException(409, "UID bereits vorhanden.")
        new = event is None
        event = calendars.save_event(
            db, user, cal, data, event, raw_ical=body, device_id=device.id
        )
        event.uid = uid
        event.dav_name = name
        device.last_used = utcnow()
        db.commit()
        return Response(status_code=201 if new else 204, headers={"ETag": etag(event)})
    from .calendar_sources import dav_objects

    if cal.source == "free":
        events = list(
            db.scalars(
                select(CalendarEvent)
                .where(CalendarEvent.calendar_id == cid)
                .limit(10001)
            )
        )
        if len(events) > 10000:
            raise HTTPException(507, "Kalender zu groß für diesen Abruf.")
        objects = {
            event.dav_name: (calendars.export(db, user, cal, [event]), etag(event))
            for event in events
            if calendars.event_access(db, user, cal, event)
        }
    else:
        objects = dav_objects(db, user, cal)
    base = "/caldav/calendars/" + str(cid) + "/"
    if name and name not in objects:
        raise HTTPException(404)
    if method in ("GET", "HEAD"):
        content, tag = (
            objects[name] if name else (calendars.export(db, user, cal), None)
        )
        if tag and request.headers.get("if-none-match") == tag:
            return Response(
                status_code=304, headers={"ETag": tag, "Cache-Control": "no-store"}
            )
        return Response(
            content if method == "GET" else "",
            media_type="text/calendar",
            headers={
                "Cache-Control": "no-store",
                "Content-Length": str(len(content.encode())),
                **({"ETag": tag} if tag else {}),
            },
        )
    tree = parse_xml(await xml_body(request))
    if method == "REPORT":
        if name:
            raise HTTPException(405)
        return protocol.report(db, device, cal, base, objects, tree)
    if method != "PROPFIND":
        raise HTTPException(405)
    depth = request.headers.get("depth", "0")
    if depth not in ("0", "1"):
        raise HTTPException(403)
    if name:
        return protocol.multistatus(
            [(base + name, protocol.resource_props(*objects[name]))], tree
        )
    props = protocol.collection_props(
        cal, principal, bool(devices.allowed(db, device, user, cid, True)), objects
    )
    if tree is not None and tree.find(".//{DAV:}sync-token") is not None:
        props.append((D, "sync-token", protocol.snapshot(db, device, cid, objects)))
    entries = [(base, props)]
    if depth == "1":
        entries += [
            (base + key, protocol.resource_props(*value))
            for key, value in objects.items()
        ]
    return protocol.multistatus(entries, tree)
