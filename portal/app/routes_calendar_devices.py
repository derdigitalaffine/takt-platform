"""Credential issuance and one-shot Apple profile download; no recoverable secrets."""

from fastapi import Depends, Request, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app, current_user, get_db, check_csrf, render, redirect, flash
from .db import User, get_settings, set_setting
from .calendar_models import Calendar, CalendarDevice, CalendarDeviceScope
from . import calendar_devices as devices, calendars
from .calendar_profiles import ios_profile
from .config import settings


@app.get("/kalender/geraete")
def page(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = list(
        db.scalars(
            select(CalendarDevice)
            .where(CalendarDevice.user_id == user.id)
            .order_by(CalendarDevice.id.desc())
        )
    )
    available = [
        c
        for c in db.scalars(select(Calendar).order_by(Calendar.title))
        if calendars.access(db, user, c)
    ]
    return render(
        request,
        "calendar_devices.html",
        user,
        devices=rows,
        calendars=available,
        writable={c.id: calendars.access(db, user, c, True) for c in available},
        scopes={
            (s.device_id, s.calendar_id): s.can_write
            for s in db.scalars(
                select(CalendarDeviceScope)
                .join(
                    CalendarDevice, CalendarDevice.id == CalendarDeviceScope.device_id
                )
                .where(CalendarDevice.user_id == user.id)
            )
        },
        device_days=get_settings(db).get("calendar_device_days", "0"),
    )


@app.post("/kalender/geraete", dependencies=[Depends(check_csrf)])
async def issue(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if request.url.scheme != "https" or not settings.portal_base_url.startswith(
        "https://"
    ):
        raise HTTPException(
            422, "Kalendergeräte benötigen eine HTTPS-Adresse für Takt."
        )
    data = await request.form()
    choices = []
    for value in data.getlist("calendars"):
        try:
            cid = int(value)
        except ValueError:
            raise HTTPException(422)
        choices.append((cid, str(cid) in data.getlist("write")))
    from .leave import lock

    lock(db)
    device, secret = devices.create(db, user, data.get("name", ""), choices)
    if data.get("platform") == "ios":
        try:
            profile = ios_profile(
                server_url=settings.portal_base_url,
                device_username=device.username,
                device_password=secret,
            )
        except ValueError as e:
            raise HTTPException(422, str(e))
        db.commit()
        return Response(
            profile,
            media_type="application/x-apple-aspen-config",
            headers={
                "Content-Disposition": 'attachment; filename="takt-kalender.mobileconfig"',
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )
    db.commit()
    response = render(
        request,
        "calendar_device_created.html",
        user,
        device=device,
        secret=secret,
        server=settings.portal_base_url + "/caldav/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post("/kalender/geraete/{did:int}/widerrufen", dependencies=[Depends(check_csrf)])
def revoke(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(CalendarDevice, did)
    if not row or row.user_id != user.id:
        raise HTTPException(404)
    row.revoked = True
    db.commit()
    return redirect("/kalender/geraete")


@app.post("/kalender/geraete/{did:int}/auswahl", dependencies=[Depends(check_csrf)])
async def change(
    request: Request,
    did: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from .leave import lock

    lock(db)
    row = db.get(CalendarDevice, did)
    if not row or row.user_id != user.id or row.revoked:
        raise HTTPException(404)
    data = await request.form()
    scopes = []
    for raw in data.getlist("calendars"):
        try:
            cid = int(raw)
        except ValueError:
            raise HTTPException(422)
        cal = db.get(Calendar, cid)
        write = raw in data.getlist("write")
        if not cal or not calendars.access(db, user, cal, write):
            raise HTTPException(403)
        scopes.append((cid, write))
    from sqlalchemy import delete

    db.execute(delete(CalendarDeviceScope).where(CalendarDeviceScope.device_id == did))
    for cid, write in set(scopes):
        db.add(CalendarDeviceScope(device_id=did, calendar_id=cid, can_write=write))
    db.commit()
    return redirect("/kalender/geraete")


@app.post("/kalender/geraete/laufzeit", dependencies=[Depends(check_csrf)])
async def lifetime(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not user.is_admin:
        raise HTTPException(403)
    data = await request.form()
    try:
        days = int(data.get("days", "0"))
    except (TypeError, ValueError):
        raise HTTPException(422)
    if not 0 <= days <= 3650:
        raise HTTPException(422, "Laufzeit muss zwischen 0 und 3650 Tagen liegen.")
    set_setting(db, "calendar_device_days", str(days))
    db.commit()
    return redirect("/kalender/geraete")


@app.get("/kalender/hilfe")
def help_page(request: Request, user: User = Depends(current_user)):
    return render(request, "calendar_help.html", user)
