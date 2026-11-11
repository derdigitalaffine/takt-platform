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
@app.get("/kalender/jahr")
def calendar_page(
    request: Request, unit: int | None = None, date: str | None = None,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from datetime import date as calendar_date_type

    if date:
        try:
            chosen_date = calendar_date_type.fromisoformat(date)
            if not 1970 <= chosen_date.year <= 2200:
                raise ValueError("calendar year")
        except (ValueError, TypeError):
            raise HTTPException(422, "Kalenderdatum prüfen.")
    else:
        chosen_date = None
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
    import json
    allowed_units = {n.id for n in units}
    if unit is not None and unit not in allowed_units:
        raise HTTPException(403)
    if unit is None:
        try:
            remembered = json.loads(user.nav_json or "{}").get("last_org_unit")
        except (ValueError, AttributeError):
            remembered = None
        unit = remembered if remembered in allowed_units else (units[0].id if units else None)
    # The calendar entry point is the shared annual overview; the monthly
    # working view remains available via ?ansicht=termine and all old deep links.
    year_mode = request.url.path == "/kalender/jahr" or request.query_params.get("ansicht") != "termine"
    attached = {c.source for c in rows if c.source != "free"}
    # Existing subscriptions remain canonical. Only missing projections get an
    # ephemeral one-click control; no shadow Calendar rows are created.
    source_choices = [
        dict(key=kind, label=meta[0],
             suggested=(kind in (
                 {"holidays", "closures", "seminars", "leave", "birthdays"} if year_mode
                 else {"meetings", "seminars", "tasks", "leave", "holidays", "closures", "birthdays"}
             )))
        for kind, meta in calendar_sources.SOURCES.items()
        if calendar_sources.enabled(db, kind) and kind not in attached
    ]
    shared_year = next((
        c for c in rows
        if c.source == "free"
        and c.title.casefold().strip() in {"jahresplanung", "gemeinsame jahrestermine"}
        and (c.visibility == "internal" or (
            c.visibility == "organization" and c.org_id == unit
        ))
    ), None)
    return render(
        request,
        "calendars.html",
        user,
        calendars=rows,
        year_mode=year_mode,
        calendar_date=chosen_date.isoformat() if chosen_date else "",
        shared_year=shared_year,
        source_choices=source_choices,
        recommended_sources=(
            {"holidays", "closures", "seminars", "leave"} if year_mode
            else {"meetings", "seminars", "tasks", "leave", "holidays", "closures"}
        ),
        has_closure_source=any(c.source == "closures" for c in rows),
        sources={
            key: val[0]
            for key, val in calendar_sources.SOURCES.items()
            if calendar_sources.enabled(db, key)
        },
        writable_calendars={c.id for c in rows if calendars.access(db, user, c, True)},
        units=units,
        selected_org_unit=unit,
        closure_units=[
            n
            for n in db.scalars(select(Organization).order_by(Organization.name))
            if org.allows(db, user, n.id, "leave_settings")
        ],
    )


@app.post("/kalender/jahresplanung", dependencies=[Depends(check_csrf)])
async def create_year_plan(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """One explicit action creates the existing shared-calendar *type*.

    No automatic public sharing, no extra calendar model and no duplicate
    on repeated clicks. A global plan is visible to signed-in users only;
    the organization variant follows existing organization ACLs.
    """
    from .leave import lock

    if not user.can("calendars"):
        raise HTTPException(403)
    data = await request.form()
    scope = str(data.get("scope", ""))
    if scope not in {"internal", "organization"}:
        raise HTTPException(422, "Gültige Sichtbarkeit auswählen.")
    unit = int(data["unit"]) if str(data.get("unit", "")).isdigit() else None
    if scope == "internal":
        if not user.can("calendar_publish"):
            raise HTTPException(403)
        visibility, org_id = "internal", None
    else:
        if unit is None or not org.allows(db, user, unit, "plan"):
            raise HTTPException(403)
        visibility, org_id = "organization", unit

    lock(db)
    from sqlalchemy import or_
    existing = db.scalar(
        select(Calendar).where(
            Calendar.source == "free",
            Calendar.visibility == visibility,
            Calendar.org_id.is_(None) if org_id is None else Calendar.org_id == org_id,
            or_(Calendar.title == "Jahresplanung", Calendar.title == "Gemeinsame Jahrestermine"),
        ).order_by(Calendar.id)
    )
    if existing is None:
        existing = Calendar(
            title="Jahresplanung", source="free",
            owner_id=user.id, visibility=visibility, org_id=org_id,
            include_children=True,
        )
        db.add(existing)
        db.flush()
        calendars.audit(db, user, existing, "create")
    db.commit()
    suffix = "?unit=" + str(unit) if org_id else ""
    return redirect("/kalender/jahr" + suffix + "#shared-calendar")


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
        calendars.delete_event(db, user, cal, row, data.get("version"))
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
        "/urlaub/schliesszeiten"
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
        or enrollment not in ("lead", "self", "both")
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


@app.get("/kalender/buchungen/{bid:int}")
def calendar_booking_detail(
    request: Request, bid: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Restricted details for a single appointment visible via the calendar.

    An assigned provider can see their own appointment without being granted
    blanket access to the rest of a booking page.
    """
    from .db import Booking
    from . import shares, booking_integration
    booking = db.get(Booking, bid)
    if not booking or booking.status not in ("booked", "requested"):
        raise HTTPException(404)
    page = booking.page
    level = shares.access_level(db, "booking", page, user)
    responsible = booking.provider_id == user.id or (
        booking.provider_id is None and page.owner_id == user.id)
    if level < shares.VIEW and not responsible:
        raise HTTPException(404)
    show_details = booking_integration.calendar_visibility(
        booking, can_edit=level >= shares.EDIT, responsible=responsible) == "detail"
    from . import bookings as bk
    return render(
        request, "calendar_booking_detail.html", user,
        booking=booking, page=page, show_details=show_details,
        can_open=level >= shares.VIEW, can_manage=level >= shares.EDIT,
        when=bk.label(booking.starts_at, booking.ends_at),
    )


@app.get("/kalender/quellen/{kind}/data")
def inline_source_events(
    kind: str,
    start: str | None = None,
    end: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Display a canonical Fachkalender without creating a subscription.

    Project() performs live record-level ACL filtering, exactly as for
    attached read-only calendar objects and their ICS/DAV representations.
    """
    from .calendar_recurrence import window

    if not calendar_sources.enabled(db, kind):
        raise HTTPException(404)
    a, b = window(start, end)
    return dict(events=calendar_sources.project(db, user, kind, a, b), canWrite=False)


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
    if kind == "birthdays":
        from . import birthdays
        if not (birthdays.external_allowed(db, user, "caldav") or birthdays.external_allowed(db, user, "ics")):
            raise HTTPException(403)
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


@app.get("/kalender/besprechungen/{mid:int}/oeffnen")
def open_meeting(
    mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from .db import Meeting, Invitee
    from . import seminar_hybrid

    row = db.get(Meeting, mid)
    if not row or row.cancelled_at or seminar_hybrid.is_seminar_room(db, row):
        raise HTTPException(404)
    if row.owner_id == user.id and user.can("video"):
        return redirect("/meetings/" + str(row.id))
    invited = db.scalar(
        select(Invitee).where(
            Invitee.meeting_id == mid,
            Invitee.email == user.email,
            Invitee.join_token.is_not(None),
        )
    )
    if not invited:
        raise HTTPException(403)
    return redirect("/join/" + invited.join_token)
