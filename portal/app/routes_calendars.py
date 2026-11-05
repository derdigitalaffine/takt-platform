"""Shared calendar entry point and rights-protected event CRUD."""

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app, current_user, get_db, check_csrf, render, redirect, flash
from .db import User, Organization
from .calendar_models import Calendar, CalendarEvent
from . import calendars, calendar_sources, organization as org


def get_calendar(db, actor, cid, write=False):
    row = db.get(Calendar, cid)
    if not row:
        raise HTTPException(404)
    if not calendars.access(db, actor, row, write):
        raise HTTPException(403)
    return row


@app.get("/kalender")
def calendar_page(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = [
        c
        for c in db.scalars(select(Calendar).order_by(Calendar.title))
        if calendars.access(db, user, c)
    ]
    units = [
        n
        for n in db.scalars(select(Organization).order_by(Organization.name))
        if org.allows(db, user, n.id, "plan")
    ]
    return render(
        request,
        "calendars.html",
        user,
        calendars=rows,
        has_closure_source=any(c.source == "closures" for c in rows),
        sources={
            key: val[0]
            for key, val in calendar_sources.SOURCES.items()
            if calendar_sources.enabled(db, key)
        },
        writable_calendars={c.id for c in rows if calendars.access(db, user, c, True)},
        units=units,
        closure_units=[
            n
            for n in db.scalars(select(Organization).order_by(Organization.name))
            if org.allows(db, user, n.id, "leave_settings")
        ],
    )


@app.post("/kalender", dependencies=[Depends(check_csrf)])
async def calendar_create(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not user.can("calendars"):
        raise HTTPException(403)
    data = await request.form()
    title = str(data.get("title", "")).strip()
    visibility = str(data.get("visibility", "private"))
    if (
        not title
        or len(title) > 200
        or visibility not in ("private", "organization", "internal", "public")
    ):
        raise HTTPException(422)
    if visibility in ("public", "internal") and not user.can("calendar_publish"):
        raise HTTPException(403)
    oid = int(data["org_id"]) if str(data.get("org_id", "")).isdigit() else None
    if visibility == "organization" and (
        not oid or not org.allows(db, user, oid, "plan")
    ):
        raise HTTPException(403)
    row = Calendar(
        owner_id=user.id,
        title=title,
        visibility=visibility,
        org_id=oid if visibility == "organization" else None,
        include_children=data.get("include_children") == "1",
    )
    db.add(row)
    db.commit()
    return redirect("/kalender")


@app.get("/kalender/{cid:int}/data")
def calendar_data(
    cid: int,
    start: str | None = None,
    end: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from .calendar_recurrence import window, occurrences

    row = get_calendar(db, user, cid)
    a, b = window(start, end)
    if row.source != "free":
        from .calendar_sources import project

        return dict(events=project(db, user, row.source, a, b), canWrite=False)
    events = []
    for event in db.scalars(
        select(CalendarEvent).where(CalendarEvent.calendar_id == cid)
    ):
        if not calendars.event_access(db, user, row, event):
            continue
        events.extend(occurrences(event, a, b))
        if len(events) > 10000:
            raise HTTPException(507, "Zu viele Termine im Kalenderzeitraum.")
    can_write = calendars.access(db, user, row, True)
    for event in events:
        event["extendedProps"]["canWrite"] = can_write
    return dict(events=events, canWrite=can_write)


@app.get("/kalender/{cid:int}/abo.ics")
def calendar_ics(
    cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return Response(
        calendars.export(db, user, get_calendar(db, user, cid)),
        media_type="text/calendar",
        headers={"Cache-Control": "private, no-store"},
    )


@app.post("/kalender/{cid:int}/termine", dependencies=[Depends(check_csrf)])
async def calendar_event(
    request: Request,
    cid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = await calendars.json_payload(request)
    from .leave import lock

    lock(db)
    cal = get_calendar(db, user, cid, True)
    row = None
    if data.get("id"):
        if not isinstance(data["id"], (str, int)) or not str(data["id"]).isdigit():
            raise HTTPException(422)
        row = db.get(CalendarEvent, data["id"])
        if (
            not row
            or row.calendar_id != cid
            or not calendars.event_access(db, user, cal, row)
        ):
            raise HTTPException(404)
    if data.get("action") == "delete":
        if not row or str(row.version) != str(data.get("version")):
            raise HTTPException(409, "Der Termin wurde inzwischen geändert.")
        calendars.audit(db, user, cal, "delete", row)
        db.delete(row)
        cal.version += 1
        db.commit()
        return {"deleted": True}
    row = calendars.save_event(db, user, cal, data, row)
    db.commit()
    return calendars.event_data(row)


def closure_visible(db, user, closed):
    from .org_models import OrgMembership

    if user.is_admin:
        return True
    path = org.active_path(db, closed.org_id)
    if not path:
        return False
    for unit in db.scalars(
        select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)
    ):
        if closed.org_id in org.active_path(db, unit):
            return True
    for grant in org.grants(db, user):
        if (
            closed.org_id in org.active_path(db, grant.org_id)
            or grant.include_children
            and grant.org_id in path
        ):
            return True
    return False


def closure_link(db, user, closed):
    from .routes_leave import readable
    from .org_models import OrgMembership

    if readable(db, user, closed.org_id):
        unit = closed.org_id
    else:
        unit = next(
            (
                oid
                for oid in db.scalars(
                    select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)
                )
                if closed.org_id in org.active_path(db, oid)
            ),
            None,
        )
    return (
        "/urlaub"
        + ("?unit=" + str(unit) if unit else "")
        + "#closure-"
        + str(closed.id)
    )


@app.get("/kalender/organisationstermine")
def organization_events(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from datetime import date, timedelta
    from .leave_extensions import Closure

    return dict(
        events=[
            dict(
                id="closure:" + str(c.id),
                title="Schließzeit: " + c.title,
                start=c.starts_on,
                end=(date.fromisoformat(c.ends_on) + timedelta(days=1)).isoformat(),
                allDay=True,
                classNames=["takt-closure-event"],
                extendedProps=dict(
                    kind="closure",
                    closureId=c.id,
                    orgId=c.org_id,
                    emergencyMinimum=c.emergency_minimum,
                    enrollment=c.enrollment,
                    url=closure_link(db, user, c),
                    canEdit=org.allows(db, user, c.org_id, "leave_settings"),
                ),
            )
            for c in db.scalars(select(Closure).order_by(Closure.starts_on))
            if closure_visible(db, user, c)
        ]
    )


@app.post("/kalender/schliesszeiten", dependencies=[Depends(check_csrf)])
async def create_closure(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from . import leave
    from .leave_extensions import Closure

    data = await calendars.json_payload(request)
    leave.lock(db)
    try:
        unit = int(data.get("org_id"))
        minimum = int(data.get("minimum", 0))
    except (TypeError, ValueError):
        raise HTTPException(422, "Bereich und Notbesetzung prüfen.")
    if not org.allows(db, user, unit, "leave_settings"):
        raise HTTPException(403)
    p = leave.period(
        user.id, dict(starts_on=data.get("start"), ends_on=data.get("end"))
    )
    title = str(data.get("title", "")).strip()
    enrollment = data.get("enrollment", "lead")
    if (
        not title
        or len(title) > 200
        or not 0 <= minimum <= 10000
        or enrollment not in ("lead", "self")
    ):
        raise HTTPException(422, "Schließzeit prüfen.")
    closed = Closure(
        org_id=unit,
        title=title,
        starts_on=p.start.isoformat(),
        ends_on=p.end.isoformat(),
        emergency_minimum=minimum,
        enrollment=enrollment,
    )
    db.add(closed)
    db.flush()
    org.audit(db, user, unit, "leave_closure", closure=closed.id)
    db.commit()
    return dict(id=closed.id)


@app.post("/kalender/quellen", dependencies=[Depends(check_csrf)])
async def attach_source(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from .calendar_sources import SOURCES, enabled
    from .leave import lock

    data = await request.form()
    kind = data.get("source")
    lock(db)
    if not enabled(db, kind):
        raise HTTPException(422)
    if not db.scalar(
        select(Calendar.id).where(Calendar.owner_id == user.id, Calendar.source == kind)
    ):
        db.add(
            Calendar(
                owner_id=user.id,
                title=SOURCES[kind][0],
                source=kind,
                visibility="private",
            )
        )
    db.commit()
    return redirect("/kalender")
