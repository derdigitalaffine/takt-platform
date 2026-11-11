"""Digital Signage routes: management, privacy-scoped kiosks and revocable credentials."""
import json
from datetime import timedelta
from hmac import compare_digest
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import branding, links, notify, signage, calendars
from .db import Organization, PortalLocation, Resource, User, get_settings, utcnow
from .main import app, check_csrf, current_user, enabled_modules, flash, get_db, rate_limit, redirect, render, require, templates
from .calendar_models import Calendar
from .signage_models import (SignageBuilding, SignageDevice, SignageFloor, SignageLink,
                             SignageOffice, SignageRoom, SignageScreen)

manage_user = require("signage_manage")
VISIBLE = {"private", "public", "link"}


def _enabled():
    if "signage" not in enabled_modules():
        raise HTTPException(404)


def _screen(db, sid):
    _enabled()
    screen = db.get(SignageScreen, sid)
    if not screen:
        raise HTTPException(404)
    return screen


def _int(value):
    return int(value) if str(value or "").isdigit() and int(value) > 0 else None


def _render_display(request, db, screen, *, public, viewer=None):
    if not screen.enabled:
        raise HTTPException(404)
    data = signage.context(db, screen, public=public, viewer=viewer)
    org = db.get(Organization, screen.org_id) if screen.org_id else None
    response = templates.TemplateResponse(request, "signage_display.html", {
        **data, "ui": branding.load(), "org_logo": f"/org/{org.id}/logo" if org and org.logo else None,
    })
    response.headers.update({"Cache-Control": "no-store, max-age=0",
                             "Referrer-Policy": "no-referrer",
                             "X-Content-Type-Options": "nosniff",
                             "X-Robots-Tag": "noindex, nofollow"})
    return response


@app.get("/signage")
def signage_home(request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    return render(request, "signage_admin.html", user,
        screens=list(db.scalars(select(SignageScreen).order_by(SignageScreen.name))),
        buildings=list(db.scalars(select(SignageBuilding).order_by(SignageBuilding.name))),
        floors=list(db.scalars(select(SignageFloor).order_by(SignageFloor.level))),
        rooms=list(db.scalars(select(SignageRoom).order_by(SignageRoom.number))),
        offices=list(db.scalars(select(SignageOffice))),
        staff=list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.name))),
        locations=list(db.scalars(select(PortalLocation).where(PortalLocation.active.is_(True), PortalLocation.owner_id.is_(None)).order_by(PortalLocation.name))),
        organizations=list(db.scalars(select(Organization).order_by(Organization.name))),
        kinds=signage.KINDS,
        calendars=[cal for cal in db.scalars(select(Calendar).where(Calendar.source == "free").order_by(Calendar.title))
                   if calendars.access(db, user, cal)],
        resources=list(db.scalars(select(Resource).where(Resource.active.is_(True)).order_by(Resource.name))))


@app.post("/signage/new", dependencies=[Depends(check_csrf)])
async def signage_new(request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    data = await request.form()
    kind = str(data.get("kind") or "agenda")
    kind = kind if kind in signage.KINDS else "agenda"
    name = str(data.get("name") or "").strip()[:180]
    if not name:
        raise HTTPException(422, "Bitte eine Bezeichnung eingeben.")
    screen = SignageScreen(name=name, kind=kind, visibility="private", owner_id=user.id,
                           layout_json=json.dumps(signage.TEMPLATES[kind]))
    db.add(screen)
    db.commit()
    return redirect(f"/signage/{screen.id}/edit")


@app.get("/signage/{sid:int}/edit")
def signage_edit(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    devices = list(db.scalars(select(SignageDevice).where(SignageDevice.screen_id == sid).order_by(SignageDevice.id)))
    keys = list(db.scalars(select(SignageLink).where(SignageLink.screen_id == sid).order_by(SignageLink.id.desc())))
    return render(request, "signage_editor.html", user, screen=screen, widgets=signage.WIDGETS,
        kinds=signage.KINDS, theme=signage.theme(screen.theme_json),
        selected_widgets=signage.widgets(screen.layout_json, screen.kind),
        resources=list(db.scalars(select(Resource).where(Resource.active.is_(True)).order_by(Resource.name))),
        rooms=list(db.scalars(select(SignageRoom).order_by(SignageRoom.number))),
        organizations=list(db.scalars(select(Organization).order_by(Organization.name))),
        devices=devices, keys=keys, now=utcnow())


@app.post("/signage/{sid:int}/save", dependencies=[Depends(check_csrf)])
async def signage_save(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    form = await request.form()
    kind = str(form.get("kind") or screen.kind)
    if kind not in signage.KINDS:
        raise HTTPException(422)
    visibility = str(form.get("visibility") or "private")
    if visibility not in VISIBLE:
        raise HTTPException(422)
    screen.name = (str(form.get("name") or screen.name).strip()[:180] or screen.name)
    screen.kind = kind
    screen.visibility = visibility
    screen.data_level = "title" if form.get("data_level") == "title" else "busy"
    screen.subtitle = str(form.get("subtitle") or "").strip()[:250]
    screen.direction = str(form.get("direction") or "").strip()[:100]
    screen.enabled = form.get("enabled") == "1"
    screen.theme_json = json.dumps(signage.theme({
        key: str(form.get(key) or "") for key in signage.THEME_DEFAULTS
    }))
    screen.layout_json = json.dumps(signage.widgets(form.get("layout_json"), kind))
    rid = _int(form.get("resource_id"))
    room_id = _int(form.get("room_id"))
    org_id = _int(form.get("org_id"))
    if rid and not db.get(Resource, rid) or room_id and not db.get(SignageRoom, room_id) or org_id and not db.get(Organization, org_id):
        raise HTTPException(422, "Verknüpfung nicht vorhanden.")
    screen.resource_id, screen.room_id, screen.org_id = rid, room_id, org_id
    screen.version += 1
    screen.updated_at = utcnow()
    db.commit()
    flash(request, "Anzeige gespeichert und aktualisiert.")
    return redirect(f"/signage/{sid}/edit")


@app.get("/signage/{sid:int}/preview")
def signage_preview(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    # A preview stays readable even if publication is disabled.
    active = screen.enabled
    screen.enabled = True
    try:
        return _render_display(request, db, screen, public=False, viewer=user)
    finally:
        screen.enabled = active


@app.get("/signage/view/{sid:int}")
def signage_public(sid: int, request: Request, db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    if screen.visibility != "public":
        raise HTTPException(404)
    return _render_display(request, db, screen, public=True)


def _authorized_link(db, sid, raw):
    screen = _screen(db, sid)
    if screen.visibility != "link" or not screen.enabled or len(raw) < 32 or len(raw) > 128:
        raise HTTPException(404)
    row = db.scalar(select(SignageLink).where(
        SignageLink.screen_id == sid, SignageLink.token_hash == signage.digest(raw)))
    if row is None or row.revoked or row.expires_at <= utcnow():
        raise HTTPException(404)
    return screen, row


@app.get("/signage/l/{sid:int}/{token}")
def signage_linked(sid: int, token: str, request: Request, db: Session = Depends(get_db)):
    """Exchange a one-time URL visit for an HttpOnly scoped cookie.

    The initial email URL is necessarily a bearer secret; redirect removes it
    from the browser address bar, subsequent reloads and history entries.
    Access proxy logs must additionally redact incoming /signage/l/* paths.
    """
    _, row = _authorized_link(db, sid, token)
    age = min(7 * 86400, max(1, int((row.expires_at - utcnow()).total_seconds())))
    response = RedirectResponse(f"/signage/access/{sid}", status_code=303)
    response.set_cookie(key=f"sg_access_{sid}", value=token, max_age=age,
                        path=f"/signage/access/{sid}", secure=True,
                        httponly=True, samesite="lax")
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                             "X-Robots-Tag": "noindex, nofollow"})
    return response


@app.get("/signage/access/{sid:int}")
def signage_link_session(sid: int, request: Request, db: Session = Depends(get_db)):
    raw = request.cookies.get(f"sg_access_{sid}", "")
    screen, _ = _authorized_link(db, sid, raw)
    return _render_display(request, db, screen, public=True)


@app.post("/signage/{sid:int}/share", dependencies=[Depends(check_csrf)])
async def signage_share(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    if not screen.enabled or screen.visibility != "link":
        raise HTTPException(409, "Bitte zuerst den Zugriff 'Sicherer Link' einschalten.")
    rate_limit(request, "signage-share", limit=8, window=3600, key=str(user.id))
    form = await request.form()
    try:
        days = int(form.get("days") or 7)
    except ValueError:
        raise HTTPException(422)
    if not 1 <= days <= 90:
        raise HTTPException(422, "Ablauf zwischen 1 und 90 Tagen.")
    raw = signage.token()
    row = SignageLink(screen_id=sid, token_hash=signage.digest(raw),
                      created_by=user.id, expires_at=utcnow() + timedelta(days=days))
    url = links.module_url(db, "signage", f"/signage/l/{sid}/{raw}")
    db.add(row)
    mail = form.get("mail") == "1"
    if mail:
        if not notify.enqueue(db, user.email, f"TAKT Display: {screen.name}",
                f"Dein persönlicher Anzeigelink ist {days} Tage gültig:\n\n{url}\n\n"
                "Der Link kann in TAKT jederzeit widerrufen werden. Bitte vertraulich behandeln.",
                "signage_link", per_hour=8):
            db.rollback()
            flash(request, "E-Mail ist nicht eingerichtet oder das Versandlimit wurde erreicht.", "error")
            return redirect(f"/signage/{sid}/edit")
    db.commit()
    if mail:
        flash(request, "Der Link wurde zum Versand an deine Konto-E-Mail-Adresse eingereiht.")
        return redirect(f"/signage/{sid}/edit")
    # Secret is displayed once only; the database contains solely its hash.
    resp = render(request, "signage_secret.html", user, label="Geschützter Link", secret=url, screen=screen)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.post("/signage/{sid:int}/link/{link_id:int}/revoke", dependencies=[Depends(check_csrf)])
def signage_revoke(sid: int, link_id: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _screen(db, sid)
    key = db.get(SignageLink, link_id)
    if not key or key.screen_id != sid:
        raise HTTPException(404)
    key.revoked = True
    db.commit()
    flash(request, "Freigabelink widerrufen.")
    return redirect(f"/signage/{sid}/edit")


@app.post("/signage/{sid:int}/device", dependencies=[Depends(check_csrf)])
async def signage_register_device(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _screen(db, sid)
    form = await request.form()
    raw = signage.token()
    name = str(form.get("name") or "").strip()[:180]
    if not name:
        raise HTTPException(422)
    device = SignageDevice(screen_id=sid, name=name, secret_hash=signage.digest(raw))
    db.add(device)
    db.commit()
    resp = render(request, "signage_secret.html", user, screen=db.get(SignageScreen, sid),
                  label="Geräteschlüssel – nur für Player-API, nicht in URLs einsetzen",
                  secret=f"Gerät-ID: {device.id}\nBearer: {raw}")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/signage/{sid:int}/device/{device_id:int}/revoke", dependencies=[Depends(check_csrf)])
def signage_revoke_device(sid: int, device_id: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _screen(db, sid)
    device = db.get(SignageDevice, device_id)
    if not device or device.screen_id != sid:
        raise HTTPException(404)
    device.revoked = True
    db.commit()
    flash(request, "Gerätezugang widerrufen.")
    return redirect(f"/signage/{sid}/edit")


def _device_access(request: Request, db, device_id: int):
    """Dedicated player bearer: no portal session, no access to CRUD."""
    _enabled()
    secret = request.headers.get("Authorization", "")
    secret = secret[len("Bearer "):].strip() if secret.startswith("Bearer ") else ""
    device = db.get(SignageDevice, device_id)
    if not device or device.revoked or len(secret) < 32 or len(secret) > 128:
        raise HTTPException(403)
    if not compare_digest(signage.digest(secret), device.secret_hash):
        raise HTTPException(403)
    screen = db.get(SignageScreen, device.screen_id)
    if not screen or not screen.enabled:
        raise HTTPException(404)
    return device, screen


@app.post("/signage/api/device/{device_id:int}/heartbeat")
def signage_heartbeat(device_id: int, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "signage-device", limit=90, window=60)
    device, screen = _device_access(request, db, device_id)
    device.last_seen_at = utcnow()
    db.commit()
    return JSONResponse({"ok": True, "screen_id": screen.id, "version": screen.version,
                         "kind": screen.kind}, headers={"Cache-Control": "no-store"})


@app.get("/signage/api/device/{device_id:int}/manifest")
def signage_device_manifest(device_id: int, request: Request, db: Session = Depends(get_db)):
    """Machine-readable player feed, limited to the same safe kiosk projection."""
    rate_limit(request, "signage-manifest", limit=120, window=60)
    _, screen = _device_access(request, db, device_id)
    projected = signage.context(db, screen, public=True)
    events = [{
        "start": ev["start"].isoformat(), "end": ev["end"].isoformat(),
        "busy": True, "ongoing": ev["ongoing"], "label": "Belegt",
    } for ev in projected["events"]]
    org = db.get(Organization, screen.org_id) if screen.org_id else None
    return JSONResponse({
        "screen": {"id": screen.id, "version": screen.version, "name": screen.name,
                   "kind": screen.kind, "subtitle": screen.subtitle,
                   "direction": screen.direction},
        "theme": projected["theme"], "widgets": projected["widgets"],
        "brand": {"name": branding.load()["name"],
                  "logo": f"/org/{org.id}/logo" if org and org.logo else None},
        "room": {"number": projected["room"].number,
                 "name": projected["room"].name} if projected["room"] else None,
        "status": {"busy": bool(projected["busy"]), "updated_at": projected["now"].isoformat()},
        "events": events,
        "directory": projected["staff"],
        "waypoints": projected["waypoints"],
    }, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/signage/structure", dependencies=[Depends(check_csrf)])
async def signage_structure(request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    form = await request.form()
    action = str(form.get("action") or "")
    name = str(form.get("name") or "").strip()[:180]
    if not name:
        raise HTTPException(422)
    if action == "building":
        loc, org = _int(form.get("location_id")), _int(form.get("org_id"))
        if loc and not db.get(PortalLocation, loc) or org and not db.get(Organization, org):
            raise HTTPException(422)
        db.add(SignageBuilding(name=name, location_id=loc, org_id=org))
    elif action == "floor":
        bid = _int(form.get("building_id"))
        if not bid or not db.get(SignageBuilding, bid):
            raise HTTPException(422)
        try:
            level = int(form.get("level") or 0)
        except ValueError:
            raise HTTPException(422)
        if not -20 <= level <= 200:
            raise HTTPException(422)
        db.add(SignageFloor(building_id=bid, name=name, level=level))
    elif action == "room":
        fid, rid = _int(form.get("floor_id")), _int(form.get("resource_id"))
        cid = _int(form.get("calendar_id"))
        calendar = db.get(Calendar, cid) if cid else None
        if cid and (not calendar or calendar.source != "free" or not calendars.access(db, user, calendar)):
            raise HTTPException(403, "Kein Zugriff auf den gewählten Kalender.")
        if not fid or not db.get(SignageFloor, fid) or rid and not db.get(Resource, rid):
            raise HTTPException(422)
        db.add(SignageRoom(floor_id=fid, number=name[:40], name=str(form.get("label") or "").strip()[:180],
                           resource_id=rid, calendar_id=cid, accessible=form.get("accessible") == "1"))
    else:
        raise HTTPException(422)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "Eintrag bereits vorhanden oder Datenkonflikt.")
    flash(request, "Gebäudestammdaten gespeichert.")
    return redirect("/signage#buildings")


@app.post("/signage/room/{room_id:int}/calendar", dependencies=[Depends(check_csrf)])
async def signage_update_room_calendar(room_id: int, request: Request,
                                      user: User = Depends(manage_user),
                                      db: Session = Depends(get_db)):
    """Explicitly opt a room into a real TAKT calendar (no shadow events)."""
    _enabled()
    room = db.get(SignageRoom, room_id)
    if not room:
        raise HTTPException(404)
    form = await request.form()
    cid = _int(form.get("calendar_id"))
    calendar = db.get(Calendar, cid) if cid else None
    if cid and (not calendar or calendar.source != "free" or not calendars.access(db, user, calendar)):
        raise HTTPException(403, "Der Kalender ist nicht freigegeben.")
    room.calendar_id = cid
    db.commit()
    flash(request, "Raumkalender aktualisiert.")
    return redirect("/signage#buildings")


@app.post("/signage/office", dependencies=[Depends(check_csrf)])
async def signage_office(request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    form = await request.form()
    uid, rid = _int(form.get("user_id")), _int(form.get("room_id"))
    staff = db.get(User, uid) if uid else None
    room = db.get(SignageRoom, rid) if rid else None
    if not staff or not staff.active or not room:
        raise HTTPException(422)
    row = db.scalar(select(SignageOffice).where(SignageOffice.user_id == uid, SignageOffice.room_id == rid))
    if not row:
        row = SignageOffice(user_id=uid, room_id=rid)
        db.add(row)
    row.public = form.get("public") == "1"
    row.is_primary = form.get("primary") == "1"
    db.commit()
    flash(request, "Bürozuordnung gespeichert; öffentliche Freigabe wird separat gesteuert.")
    return redirect("/signage#offices")
