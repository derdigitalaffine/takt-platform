"""Explicit owner-controlled ACLs, public views and revocable read-only feeds."""

import hashlib, secrets, re, logging
from fastapi import Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app, get_db, current_user, check_csrf, render, redirect
from .db import User, Group, Organization
from .calendar_models import (
    Calendar,
    CalendarGrant,
    CalendarFeed,
    CalendarEvent,
    CalendarAudit,
)
from . import calendars, leave, organization as org
from .config import settings
from . import people_choices


class _RedactFeed(logging.Filter):
    def filter(self, record):
        if (
            isinstance(record.args, tuple)
            and len(record.args) >= 3
            and isinstance(record.args[2], str)
        ):
            args = list(record.args)
            args[2] = re.sub(
                r"(/kalender/abos/)[A-Za-z0-9_-]+", r"\1[redacted]", args[2]
            )
            record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactFeed())


def owned(db, user, cid):
    cal = db.get(Calendar, cid)
    if not cal:
        raise HTTPException(404)
    if cal.source != "free":
        raise HTTPException(
            403, "Fachkalender werden über das zuständige Modul freigegeben."
        )
    if not user.is_admin and cal.owner_id != user.id:
        raise HTTPException(403)
    return cal


@app.get("/kalender/{cid:int}/teilen")
def sharing(
    request: Request,
    cid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    cal = owned(db, user, cid)
    people = {u.id: u for u in db.scalars(select(User).order_by(User.name))}
    groups = {g.id: g for g in db.scalars(select(Group).order_by(Group.name))}
    return render(
        request,
        "calendar_sharing.html",
        user,
        calendar=cal,
        history=list(
            db.scalars(
                select(CalendarAudit)
                .where(CalendarAudit.calendar_id == cid)
                .order_by(CalendarAudit.id.desc())
                .limit(100)
            )
        ),
        units=[
            n
            for n in db.scalars(select(Organization).order_by(Organization.name))
            if org.allows(db, user, n.id, "plan")
        ],
        grants=list(
            db.scalars(select(CalendarGrant).where(CalendarGrant.calendar_id == cid))
        ),
        people=people,
        groups=groups,
        sharing_choices=people_choices.users(people.values(), targets=True)
        + people_choices.groups(groups.values()),
    )


@app.post("/kalender/{cid:int}/teilen", dependencies=[Depends(check_csrf)])
async def grant(
    request: Request,
    cid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = await request.form()
    leave.lock(db)
    cal = owned(db, user, cid)
    if str(cal.version) != str(data.get("version")):
        raise HTTPException(
            409, "Der Kalender wurde inzwischen geändert. Bitte neu laden."
        )
    if data.get("action") == "metadata":
        title = str(data.get("title", "")).strip()
        visibility = data.get("visibility")
        if (
            not title
            or len(title) > 200
            or visibility not in ("private", "organization", "internal", "public")
        ):
            raise HTTPException(422, "Kalendername und Sichtbarkeit prüfen.")
        if (
            visibility in ("internal", "public")
            and visibility != cal.visibility
            and not user.can("calendar_publish")
        ):
            raise HTTPException(403)
        oid = int(data.get("org_id")) if str(data.get("org_id", "")).isdigit() else None
        if visibility == "organization" and (
            not oid or not org.allows(db, user, oid, "plan")
        ):
            raise HTTPException(403)
        cal.title = title
        cal.visibility = visibility
        cal.org_id = oid if visibility == "organization" else None
        cal.include_children = data.get("include_children") == "1"
    elif data.get("action") == "delete":
        if data.get("confirm_title") != cal.title:
            raise HTTPException(
                422, "Zum Löschen den vollständigen Kalendernamen eingeben."
            )
        db.delete(cal)
        db.commit()
        return redirect("/kalender")
    elif data.get("action") == "revoke":
        try:
            gid = int(data.get("grant"))
        except (TypeError, ValueError):
            raise HTTPException(422)
        row = db.get(CalendarGrant, gid)
        if not row or row.calendar_id != cid:
            raise HTTPException(404)
        db.delete(row)
    else:
        selected = list(
            dict.fromkeys(data.getlist("targets") or [data.get("target", "")])
        )
        if not 1 <= len(selected) <= 500:
            raise HTTPException(
                422, "Zwischen einer und 500 Personen oder Gruppen auswählen."
            )
        # Validate every target before changing any grant (also for direct/no-JS submissions).
        for value in selected:
            kind, _, raw = value.partition(":")
            if kind not in ("user", "group") or not raw.isdigit():
                raise HTTPException(422, "Ungültige Auswahl.")
            obj = db.get(User if kind == "user" else Group, int(raw))
            if not obj or kind == "user" and not obj.active:
                raise HTTPException(
                    422, "Die Auswahl enthält ein nicht verfügbares Konto."
                )
        for value in selected:
            kind, _, raw = value.partition(":")
            try:
                target = int(raw)
            except ValueError:
                raise HTTPException(422)
            if kind not in ("user", "group"):
                raise HTTPException(422)
            obj = db.get(User if kind == "user" else Group, target)
            if not obj or kind == "user" and not obj.active:
                raise HTTPException(422)
            field = CalendarGrant.user_id if kind == "user" else CalendarGrant.group_id
            row = db.scalar(
                select(CalendarGrant).where(
                    CalendarGrant.calendar_id == cid, field == target
                )
            ) or CalendarGrant(
                calendar_id=cid,
                user_id=target if kind == "user" else None,
                group_id=target if kind == "group" else None,
            )
            row.can_write = data.get("write") == "1"
            db.add(row)
    cal.version += 1
    calendars.audit(
        db, user, cal, "metadata" if data.get("action") == "metadata" else "share"
    )
    db.commit()
    return redirect("/kalender/" + str(cid) + "/teilen")


@app.get("/kalender/oeffentlich/{cid:int}")
def public_page(request: Request, cid: int, db: Session = Depends(get_db)):
    cal = db.get(Calendar, cid)
    if not cal or not calendars.access(db, None, cal):
        raise HTTPException(404)
    return render(
        request,
        "calendar_public.html",
        calendar=cal,
    )


@app.get("/kalender/oeffentlich/{cid:int}/data")
def public_data(
    cid: int,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
):
    from .calendar_recurrence import window, occurrences

    cal = db.get(Calendar, cid)
    if not cal or cal.visibility != "public" or cal.source != "free":
        raise HTTPException(404)
    a, b = window(start, end)
    events = []
    for row in db.scalars(
        select(CalendarEvent).where(CalendarEvent.calendar_id == cid)
    ):
        if calendars.event_access(db, None, cal, row):
            events.extend(occurrences(row, a, b))
        if len(events) > 10000:
            raise HTTPException(507)
    return Response(
        __import__("json").dumps(events),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/kalender/abos")
def feed_page(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = list(
        db.scalars(
            select(CalendarFeed)
            .where(CalendarFeed.user_id == user.id)
            .order_by(CalendarFeed.id.desc())
        )
    )
    from . import birthdays
    return render(
        request,
        "calendar_feeds.html",
        user,
        feeds=rows,
        calendars=[
            c
            for c in db.scalars(select(Calendar).order_by(Calendar.title))
            if calendars.access(db, user, c) and (
                c.source != "birthdays" or birthdays.external_allowed(db, user, "ics")
            )
        ],
    )


@app.post("/kalender/abos", dependencies=[Depends(check_csrf)])
async def feed_create(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if request.url.scheme != "https" or not settings.portal_base_url.startswith(
        "https://"
    ):
        raise HTTPException(422, "Kalenderabonnements benötigen HTTPS.")
    data = await request.form()
    try:
        cid = int(data.get("calendar_id"))
    except (TypeError, ValueError):
        raise HTTPException(422)
    cal = db.get(Calendar, cid)
    from . import birthdays
    if not cal or not calendars.access(db, user, cal) or (cal.source == "birthdays" and not birthdays.external_allowed(db, user, "ics")):
        raise HTTPException(403)
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 100:
        raise HTTPException(422)
    secret = secrets.token_urlsafe(32)
    db.add(
        CalendarFeed(
            user_id=user.id,
            calendar_id=cid,
            name=name,
            token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        )
    )
    db.commit()
    response = render(
        request,
        "calendar_feed_created.html",
        user,
        url=settings.portal_base_url + "/kalender/abos/" + secret + ".ics",
    )
    response.headers.update(
        {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )
    return response


@app.post("/kalender/abos/{fid:int}/widerrufen", dependencies=[Depends(check_csrf)])
def revoke_feed(
    fid: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.get(CalendarFeed, fid)
    if not row or row.user_id != user.id:
        raise HTTPException(404)
    row.revoked = True
    db.commit()
    return redirect("/kalender/abos")


@app.get("/kalender/abos/{token}.ics")
def feed_read(token: str, db: Session = Depends(get_db)):
    if not re.fullmatch("[A-Za-z0-9_-]{43}", token):
        raise HTTPException(404)
    feed = db.scalar(
        select(CalendarFeed).where(
            CalendarFeed.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            CalendarFeed.revoked.is_(False),
        )
    )
    if not feed:
        raise HTTPException(404)
    user = db.get(User, feed.user_id)
    cal = db.get(Calendar, feed.calendar_id)
    from . import birthdays
    if not user or not user.active or not cal or not calendars.access(db, user, cal) or (cal.source == "birthdays" and not birthdays.external_allowed(db, user, "ics")):
        raise HTTPException(404)
    return Response(
        calendars.export(db, user, cal),
        media_type="text/calendar",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
