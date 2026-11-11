"""Digital Signage routes: management, privacy-scoped kiosks and revocable credentials."""
import json
import logging
import re
from datetime import timedelta, timezone
from hmac import compare_digest
from types import SimpleNamespace
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import branding, links, notify, signage, calendars, signage_passive
from .db import LOCAL_TZ, Organization, PortalLocation, Resource, User, get_settings, utcnow
from .main import app, check_csrf, current_user, enabled_modules, flash, get_db, rate_limit, redirect, render, require, templates
from .calendar_models import Calendar, CalendarEvent
from .signage_models import (SignageBuilding, SignageDevice, SignageFloor, SignageLink,
                             SignageOffice, SignageRoom, SignageScreen, SignageRevision,
                             SignageWayNode, SignageWayEdge, SignageDisplayAnchor, SignagePassiveConfig,
                             SignagePublicDestination, SignageDestinationOverride, SignageSpecial)

class _RedactSignageLinks(logging.Filter):
    """Avoid logging bearer URLs in Uvicorn access logs.

    Reverse-proxy access logs still require their own redaction policy.
    """
    _secret = re.compile(r"(/signage/l/\d+/)[A-Za-z0-9_-]{32,128}")

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(self._secret.sub(r"\1[redacted]", arg) if isinstance(arg, str)
                                else arg for arg in record.args)
        if isinstance(record.msg, str):
            record.msg = self._secret.sub(r"\1[redacted]", record.msg)
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactSignageLinks())


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


def _assert_screen_scope(db, screen):
    """A scoped screen cannot project rooms belonging to another employer."""
    if not screen.org_id or not screen.room_id:
        return
    room = db.get(SignageRoom, screen.room_id)
    floor = db.get(SignageFloor, room.floor_id) if room else None
    building = db.get(SignageBuilding, floor.building_id) if floor else None
    if not building or not building.active or building.org_id != screen.org_id:
        raise HTTPException(403, "Raum und Organisationsumfang stimmen nicht überein.")


def _render_display(request, db, screen, *, public, viewer=None):
    _assert_screen_scope(db, screen)
    if not screen.enabled:
        raise HTTPException(404)
    data = signage.context(db, screen, public=public, viewer=viewer)
    org = db.get(Organization, screen.org_id) if screen.org_id else None
    response = templates.TemplateResponse(request, "signage_display.html", {
        **data, "refresh": request.method == "GET", "ui": branding.load(), "org_logo": f"/org/{org.id}/logo" if org and org.logo else None,
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
        route_nodes=list(db.scalars(select(SignageWayNode).order_by(SignageWayNode.id))),
        route_edges=list(db.scalars(select(SignageWayEdge).order_by(SignageWayEdge.id))),
        staff=list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.name))),
        locations=list(db.scalars(select(PortalLocation).where(PortalLocation.active.is_(True), PortalLocation.owner_id.is_(None)).order_by(PortalLocation.name))),
        organizations=list(db.scalars(select(Organization).order_by(Organization.name))),
        kinds=signage.KINDS, passive_kinds=signage_passive.KINDS, facings=signage_passive.FACINGS,
        published_rooms={row.room_id: row.label for row in db.scalars(select(SignagePublicDestination))},
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
    if kind in signage_passive.KINDS:
        building, floor, node, facing, radius = _passive_fields(db, kind, data)
        screen.org_id = building.org_id
    db.add(screen)
    db.flush()
    if kind in signage_passive.KINDS:
        db.add(SignagePassiveConfig(screen_id=screen.id, building_id=building.id,
                                    floor_id=floor.id if floor else None, facing=facing, radius_m=radius))
        if node:
            db.add(SignageDisplayAnchor(screen_id=screen.id, node_id=node.id))
    db.add(SignageRevision(screen_id=screen.id, version=1,
                           snapshot_json=signage.design_snapshot(screen), actor_id=user.id))
    db.commit()
    return redirect(f"/signage/{screen.id}/edit")


@app.get("/signage/{sid:int}/edit")
def signage_edit(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    devices = list(db.scalars(select(SignageDevice).where(SignageDevice.screen_id == sid).order_by(SignageDevice.id)))
    keys = list(db.scalars(select(SignageLink).where(SignageLink.screen_id == sid).order_by(SignageLink.id.desc())))
    passive_config = db.get(SignagePassiveConfig, sid)
    candidate_building = passive_config.building_id if passive_config and screen.kind in signage_passive.KINDS else None
    destinations = db.execute(signage_passive.destination_rows(db, screen, candidate_building).order_by(
        SignageBuilding.name, SignageFloor.level, SignageRoom.number)).all()
    source_calendars = [cal for cal in db.scalars(select(Calendar).where(
        Calendar.source == "free").order_by(Calendar.title)) if calendars.access(db, user, cal)]
    specials = list(db.scalars(select(SignageSpecial).where(SignageSpecial.screen_id == sid)
                               .order_by(SignageSpecial.published.desc(), SignageSpecial.priority.desc(), SignageSpecial.id)))
    editing_special = next((item for item in specials
                            if item.id == _int(request.query_params.get("special"))), None)
    linked_ids = {item.event_id for item in specials if item.event_id is not None}
    special_calendars = {
        event.id: event.calendar_id for event in db.scalars(select(CalendarEvent).where(CalendarEvent.id.in_(linked_ids)))
        if signage_passive.source_access(db, user, event, screen)
    } if linked_ids else {}
    source_id = _int(request.query_params.get("calendar"))
    source_events = []
    if any(cal.id == source_id for cal in source_calendars):
        event_query = select(CalendarEvent).where(CalendarEvent.calendar_id == source_id)
        search = request.query_params.get("event_search", "").strip()[:120]
        if search:
            event_query = event_query.where(CalendarEvent.title.icontains(search, autoescape=True))
        source_events = [event for event in db.scalars(event_query.order_by(
            CalendarEvent.starts_at.desc(), CalendarEvent.id.desc()).limit(200))
            if signage_passive.source_access(db, user, event, screen)]
        if editing_special and special_calendars.get(editing_special.event_id) == source_id:
            linked = db.get(CalendarEvent, editing_special.event_id)
            if linked and linked not in source_events:
                source_events.insert(0, linked)
    return render(request, "signage_editor.html", user, screen=screen, widgets=signage.WIDGETS,
        passive_config=passive_config, passive_kinds=signage_passive.KINDS, facings=signage_passive.FACINGS,
        arrows=signage_passive.ARROWS, destinations=destinations, presets=signage_passive.PRESETS,
        buildings=list(db.scalars(select(SignageBuilding).where(SignageBuilding.active.is_(True)).order_by(SignageBuilding.name))),
        floors=list(db.scalars(select(SignageFloor).order_by(SignageFloor.level))),
        overrides=list(db.scalars(select(SignageDestinationOverride).where(SignageDestinationOverride.screen_id == sid))),
        specials=specials, editing_special=editing_special, special_calendars=special_calendars,
        format_local=_format_local,
        source_calendars=source_calendars, source_id=source_id, source_events=source_events,
        kinds=signage.KINDS, theme=signage.theme(screen.theme_json),
        selected_widgets=signage.widgets(screen.layout_json, screen.kind),
        resources=list(db.scalars(select(Resource).where(Resource.active.is_(True)).order_by(Resource.name))),
        rooms=list(db.scalars(select(SignageRoom).order_by(SignageRoom.number))),
        organizations=list(db.scalars(select(Organization).order_by(Organization.name))),
        revisions=list(db.scalars(select(SignageRevision).where(SignageRevision.screen_id == sid)
                                  .order_by(SignageRevision.version.desc()).limit(30))),
        route_nodes=list(db.scalars(select(SignageWayNode).order_by(SignageWayNode.label))),
        anchor=db.get(SignageDisplayAnchor, sid),
        devices=devices, keys=keys, now=utcnow())


@app.post("/signage/{sid:int}/save", dependencies=[Depends(check_csrf)])
async def signage_save(sid: int, request: Request, user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    form = await request.form()
    if str(form.get("version") or "").isdigit() and int(form["version"]) != screen.version:
        raise HTTPException(409, "Die Anzeige wurde zwischenzeitlich geändert. Bitte neu laden.")
    kind = str(form.get("kind") or screen.kind)
    if kind not in signage.KINDS or (kind in signage_passive.KINDS and kind != screen.kind):
        raise HTTPException(422, "Passive Vorlagen werden über den Schnellstart eingerichtet.")
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
    if kind in signage_passive.KINDS:
        rid, room_id, org_id = None, None, screen.org_id
    screen.resource_id, screen.room_id, screen.org_id = rid, room_id, org_id
    _assert_screen_scope(db, screen)
    screen.version += 1
    screen.updated_at = utcnow()
    db.add(SignageRevision(screen_id=sid, version=screen.version,
                           snapshot_json=signage.design_snapshot(screen), actor_id=user.id))
    db.commit()
    flash(request, "Anzeige gespeichert und aktualisiert.")
    return redirect(f"/signage/{sid}/edit")


@app.post("/signage/{sid:int}/revision/{revision_id:int}/restore",
          dependencies=[Depends(check_csrf)])
async def signage_restore_revision(sid: int, revision_id: int, request: Request,
                                  user: User = Depends(manage_user),
                                  db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    revision = db.get(SignageRevision, revision_id)
    if not revision or revision.screen_id != sid:
        raise HTTPException(404)
    form = await request.form()
    if str(form.get("version") or "").isdigit() and int(form["version"]) != screen.version:
        raise HTTPException(409, "Die Anzeige wurde zwischenzeitlich geändert.")
    try:
        signage.apply_design_snapshot(screen, revision.snapshot_json)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "Diese Designversion ist nicht lesbar.")
    screen.version += 1
    screen.updated_at = utcnow()
    db.add(SignageRevision(screen_id=sid, version=screen.version,
                           snapshot_json=signage.design_snapshot(screen), actor_id=user.id))
    db.commit()
    flash(request, f"Designversion {revision.version} wurde wiederhergestellt. Zugriffsrechte und Freigaben bleiben unverändert.")
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


@app.post("/signage/{sid:int}/preview-live", dependencies=[Depends(check_csrf)])
async def signage_live_preview(sid: int, request: Request,
                               user: User = Depends(manage_user),
                               db: Session = Depends(get_db)):
    """Read-only WYSIWYG preview of unsaved form values; never flush to the DB."""
    original = _screen(db, sid)
    form = await request.form()
    kind = str(form.get("kind") or original.kind)
    if kind not in signage.KINDS or (kind in signage_passive.KINDS and kind != original.kind):
        raise HTTPException(422, "Unbekannte Vorlage.")

    rid, room_id, org_id = (_int(form.get(k)) for k in
                             ("resource_id", "room_id", "org_id"))
    if (rid and not db.get(Resource, rid)
            or room_id and not db.get(SignageRoom, room_id)
            or org_id and not db.get(Organization, org_id)):
        raise HTTPException(422, "Datenquelle nicht gefunden.")
    if kind in signage_passive.KINDS:
        rid, room_id, org_id = None, None, original.org_id
    draft = SimpleNamespace(
        id=original.id, owner_id=original.owner_id,
        name=(str(form.get("name") or original.name).strip()[:180] or original.name),
        subtitle=str(form.get("subtitle") or "")[:250],
        direction=str(form.get("direction") or "")[:100],
        kind=kind, resource_id=rid, room_id=room_id, org_id=org_id,
        enabled=True, data_level="title" if form.get("data_level") == "title" else "busy",
        theme_json=json.dumps(signage.theme({
            key: str(form.get(key) or "") for key in signage.THEME_DEFAULTS
        })),
        layout_json=json.dumps(signage.widgets(form.get("layout_json"), kind)),
    )
    return _render_display(request, db, draft, public=False, viewer=user)


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
        "destinations": projected["destinations"],
        "manual_direction": projected["manual_direction"],
        "special": projected["special"],
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


@app.post("/signage/structure/{kind}/{item_id:int}", dependencies=[Depends(check_csrf)])
async def signage_edit_structure(kind: str, item_id: int, request: Request,
                                 user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    model = {"building": SignageBuilding, "floor": SignageFloor, "room": SignageRoom}.get(kind)
    item = db.get(model, item_id) if model else None
    if not item:
        raise HTTPException(404)
    form = await request.form()
    name = str(form.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Bitte eine Bezeichnung eingeben.")
    if kind == "room":
        item.number = name[:40]
        item.name = str(form.get("label") or "").strip()[:180]
        item.accessible = form.get("accessible") == "1"
    elif kind == "floor":
        item.name = name[:100]
        item.level = _bounded(form, "level", -20, 200, item.level)
    else:
        item.name = name[:180]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Diese Zimmer- oder Geschossnummer ist bereits vergeben.")
    flash(request, "Stammdaten aktualisiert.")
    return redirect(f"/signage#sg-{kind}-{item_id}")


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


NODE_KINDS = {"entrance", "corridor", "stairs", "elevator", "room", "exit"}


@app.post("/signage/route/node", dependencies=[Depends(check_csrf)])
async def signage_route_node(request: Request, user: User = Depends(manage_user),
                            db: Session = Depends(get_db)):
    _enabled()
    form = await request.form()
    label = str(form.get("label") or "").strip()[:120]
    floor_id, room_id = _int(form.get("floor_id")), _int(form.get("room_id"))
    kind = str(form.get("kind") or "corridor")
    if not label or kind not in NODE_KINDS or not floor_id or not db.get(SignageFloor, floor_id):
        raise HTTPException(422)
    room = db.get(SignageRoom, room_id) if room_id else None
    if room_id and (not room or room.floor_id != floor_id):
        raise HTTPException(422, "Das Zielzimmer liegt nicht auf diesem Geschoss.")
    try:
        x, y = float(form.get("x_pct") or 50), float(form.get("y_pct") or 50)
    except (TypeError, ValueError):
        raise HTTPException(422)
    if not 0 <= x <= 100 or not 0 <= y <= 100:
        raise HTTPException(422, "Die Plan-Koordinaten müssen zwischen 0 und 100 liegen.")
    db.add(SignageWayNode(floor_id=floor_id, room_id=room_id, label=label,
                          kind=kind, x_pct=x, y_pct=y,
                          accessible=kind != "stairs" and form.get("accessible") == "1"))
    db.commit()
    flash(request, "Wegepunkt gespeichert.")
    return redirect("/signage#routing")


@app.post("/signage/route/edge", dependencies=[Depends(check_csrf)])
async def signage_route_edge(request: Request, user: User = Depends(manage_user),
                            db: Session = Depends(get_db)):
    _enabled()
    form = await request.form()
    a, b = _int(form.get("from_node_id")), _int(form.get("to_node_id"))
    if not a or not b or a == b or not db.get(SignageWayNode, a) or not db.get(SignageWayNode, b):
        raise HTTPException(422, "Bitte zwei verschiedene gültige Wegepunkte auswählen.")
    try:
        distance = int(form.get("distance_m") or 5)
    except (ValueError, TypeError):
        raise HTTPException(422)
    if not 1 <= distance <= 5000:
        raise HTTPException(422, "Entfernung zwischen 1 und 5000 Metern.")
    existing = db.scalar(select(SignageWayEdge).where(
        SignageWayEdge.from_node_id == a, SignageWayEdge.to_node_id == b))
    if existing:
        existing.distance_m = distance
        existing.accessible = form.get("accessible") == "1"
        existing.bidirectional = form.get("bidirectional") == "1"
    else:
        db.add(SignageWayEdge(from_node_id=a, to_node_id=b, distance_m=distance,
                               accessible=form.get("accessible") == "1",
                               bidirectional=form.get("bidirectional") == "1"))
    db.commit()
    flash(request, "Wegeverbindung gespeichert.")
    return redirect("/signage#routing")


@app.post("/signage/route/node/{node_id:int}/delete", dependencies=[Depends(check_csrf)])
def signage_delete_route_node(node_id: int, request: Request,
                              user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    node = db.get(SignageWayNode, node_id)
    if not node:
        raise HTTPException(404)
    # Explicit deletes are coordinated with the DB's ON DELETE CASCADE for edges
    # and display anchors, so no screen can retain a stale starting node.
    db.delete(node)
    db.commit()
    flash(request, "Wegepunkt entfernt. Betroffene Wege und Displaypositionen bitte prüfen.")
    return redirect("/signage#routing")


@app.post("/signage/route/edge/{edge_id:int}/delete", dependencies=[Depends(check_csrf)])
def signage_delete_route_edge(edge_id: int, request: Request,
                              user: User = Depends(manage_user), db: Session = Depends(get_db)):
    _enabled()
    edge = db.get(SignageWayEdge, edge_id)
    if not edge:
        raise HTTPException(404)
    db.delete(edge)
    db.commit()
    flash(request, "Wegeverbindung entfernt.")
    return redirect("/signage#routing")


@app.post("/signage/{sid:int}/anchor", dependencies=[Depends(check_csrf)])
async def signage_route_anchor(sid: int, request: Request,
                               user: User = Depends(manage_user), db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    form = await request.form()
    node_id = _int(form.get("node_id"))
    node = db.get(SignageWayNode, node_id) if node_id else None
    if node_id and not node:
        raise HTTPException(422)
    if node and screen.org_id:
        floor = db.get(SignageFloor, node.floor_id)
        building = db.get(SignageBuilding, floor.building_id) if floor else None
        if not building or building.org_id != screen.org_id:
            raise HTTPException(403, "Der Display-Standort gehört nicht zur gewählten Organisation.")
    anchor = db.get(SignageDisplayAnchor, sid)
    if node:
        if not anchor:
            db.add(SignageDisplayAnchor(screen_id=sid, node_id=node_id))
        else:
            anchor.node_id = node_id
    elif anchor:
        db.delete(anchor)
    db.commit()
    flash(request, "Position des Wegweisers gespeichert.")
    return redirect(f"/signage/{sid}/edit")


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


@app.post("/profile/signage/office/{office_id:int}/visibility",
          dependencies=[Depends(check_csrf)])
async def signage_own_directory_visibility(
        office_id: int, request: Request,
        user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A person can withdraw (or explicitly enable) their own directory entry.

    They may not invent workplace assignments or alter a colleague's location.
    """
    _enabled()
    office = db.get(SignageOffice, office_id)
    if not office or office.user_id != user.id:
        raise HTTPException(404)
    form = await request.form()
    if form.get("public") not in ("0", "1"):
        raise HTTPException(422)
    office.public = form.get("public") == "1"
    db.commit()
    flash(request, "Sichtbarkeit deiner dienstlichen Bürozuordnung aktualisiert.")
    return redirect("/profile#signage-offices")


def _format_local(value, fmt):
    return value.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime(fmt) if value else ""


def _passive_fields(db, kind, form):
    building_id = _int(form.get("building_id"))
    floor_id = _int(form.get("floor_id"))
    node_id = _int(form.get("node_id"))
    building = db.get(SignageBuilding, building_id) if building_id else None
    floor = db.get(SignageFloor, floor_id) if floor_id else None
    node = db.get(SignageWayNode, node_id) if node_id else None
    node_floor = db.get(SignageFloor, node.floor_id) if node else None
    facing = str(form.get("facing") or "")
    if not building or not building.active:
        raise HTTPException(422, "Bitte ein aktives Gebäude auswählen.")
    if (floor_id or kind in ("sign_floor", "sign_corridor")) and (
            not floor or floor.building_id != building.id):
        raise HTTPException(422, "Bitte ein Geschoss des gewählten Gebäudes auswählen.")
    if (node_id or kind == "sign_corridor") and (
            not node_floor or node_floor.building_id != building.id
            or (kind == "sign_corridor" and node.floor_id != floor.id)):
        raise HTTPException(422, "Bitte einen passenden Displaystandort im gewählten Bereich auswählen.")
    if facing and facing not in signage_passive.FACINGS:
        raise HTTPException(422, "Ungültige Blickrichtung.")
    return building, floor, node, facing, _bounded(form, "radius_m", 1, 250, 25)


def _bounded(form, field, minimum, maximum, default):
    try:
        value = int(form.get(field) or default)
    except (TypeError, ValueError):
        raise HTTPException(422, "Ungültige Zahl.")
    if not minimum <= value <= maximum:
        raise HTTPException(422, f"Zahl zwischen {minimum} und {maximum} erforderlich.")
    return value


def _destination(db, screen, room_id):
    config = db.get(SignagePassiveConfig, screen.id) if screen.kind in signage_passive.KINDS else None
    if not room_id or (screen.kind in signage_passive.KINDS and not config):
        raise HTTPException(422, "Bitte einen freigegebenen Zielraum wählen.")
    if not db.execute(signage_passive.destination_rows(db, screen, config.building_id if config else None)
                      .where(SignageRoom.id == room_id)).first():
        raise HTTPException(422, "Der Zielraum ist für diese Anzeige nicht freigegeben.")


@app.post("/signage/{sid:int}/passive", dependencies=[Depends(check_csrf)])
async def signage_passive_config(sid: int, request: Request, user: User = Depends(manage_user),
                                 db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    if screen.kind not in signage_passive.KINDS:
        raise HTTPException(404)
    form = await request.form()
    building, floor, node, facing, radius = _passive_fields(db, screen.kind, form)
    config = db.get(SignagePassiveConfig, sid) or SignagePassiveConfig(screen_id=sid)
    config.building_id, config.floor_id = building.id, floor.id if floor else None
    config.facing, config.radius_m = facing, radius
    manual_arrow = str(form.get("manual_arrow") or "")
    if manual_arrow and manual_arrow not in signage_passive.ARROWS:
        raise HTTPException(422, "Ungültiger Pfeil.")
    config.manual_arrow = manual_arrow
    config.manual_label = str(form.get("manual_label") or "").strip()[:120]
    config.manual_only = form.get("manual_only") == "1" and bool(config.manual_label)
    config.barrier_free = form.get("barrier_free") == "1"
    db.add(config)
    anchor = db.get(SignageDisplayAnchor, sid)
    if node:
        anchor = anchor or SignageDisplayAnchor(screen_id=sid)
        anchor.node_id = node.id
        db.add(anchor)
    elif anchor:
        db.delete(anchor)
    screen.org_id = building.org_id
    db.commit()
    flash(request, "Anzeigebereich gespeichert.")
    return redirect(f"/signage/{sid}/edit#passive")


@app.post("/signage/room/{room_id:int}/destination", dependencies=[Depends(check_csrf)])
async def signage_publish_destination(room_id: int, request: Request, user: User = Depends(manage_user),
                                      db: Session = Depends(get_db)):
    _enabled()
    if not db.get(SignageRoom, room_id):
        raise HTTPException(404)
    form = await request.form()
    entry = db.get(SignagePublicDestination, room_id)
    if form.get("listed") == "1":
        entry = entry or SignagePublicDestination(room_id=room_id)
        entry.label = str(form.get("label") or "").strip()[:120]
        db.add(entry)
    elif entry:
        db.delete(entry)
    db.commit()
    flash(request, "Raumfreigabe gespeichert.")
    return redirect("/signage#buildings")


@app.post("/signage/{sid:int}/destination", dependencies=[Depends(check_csrf)])
async def signage_destination_override(sid: int, request: Request, user: User = Depends(manage_user),
                                       db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    form = await request.form()
    room_id = _int(form.get("room_id"))
    entry = db.get(SignageDestinationOverride, (sid, room_id)) if room_id else None
    if form.get("action") == "reset":
        if entry:
            db.delete(entry)
    else:
        _destination(db, screen, room_id)
        arrow = str(form.get("arrow") or "")
        if arrow and arrow not in (*signage_passive.ARROWS, "none"):
            raise HTTPException(422, "Ungültiger Pfeil.")
        entry = entry or SignageDestinationOverride(screen_id=sid, room_id=room_id)
        entry.arrow = arrow
        entry.label = str(form.get("label") or "").strip()[:120]
        entry.rank = _bounded(form, "rank", -100, 100, 0)
        entry.hidden = form.get("hidden") == "1"
        db.add(entry)
    db.commit()
    flash(request, "Zielausnahme gespeichert.")
    return redirect(f"/signage/{sid}/edit#destinations")


@app.post("/signage/{sid:int}/special", dependencies=[Depends(check_csrf)])
async def signage_special_save(sid: int, request: Request, user: User = Depends(manage_user),
                               db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    form = await request.form()
    special_id = _int(form.get("special_id"))
    entry = db.get(SignageSpecial, special_id) if special_id else None
    if special_id and (not entry or entry.screen_id != sid):
        raise HTTPException(404)
    action = form.get("action")
    if action in ("remove", "withdraw"):
        if not entry:
            raise HTTPException(404)
        if action == "remove":
            db.delete(entry)
        else:
            entry.published = False
    else:
        room_id = _int(form.get("room_id"))
        _destination(db, screen, room_id)
        preset, mode = str(form.get("preset") or ""), str(form.get("mode") or "overlay")
        if preset not in signage_passive.PRESETS or mode not in ("overlay", "replace"):
            raise HTTPException(422, "Ungültige Sonderanzeige.")
        default_title, default_priority = signage_passive.PRESETS[preset]
        event_id = _int(form.get("event_id"))
        starts_at = ends_at = None
        if form.get("event_id"):
            event = db.get(CalendarEvent, event_id) if event_id else None
            if not signage_passive.source_access(db, user, event, screen):
                raise HTTPException(403, "Dieser Termin kann nicht freigegeben werden.")
        else:
            try:
                starts_at = signage_passive.schedule_time(str(form.get("starts_at") or ""))
                ends_at = signage_passive.schedule_time(str(form.get("ends_at") or ""))
            except (ValueError, OverflowError):
                raise HTTPException(422, "Bitte gültige und eindeutige Start- und Endzeiten eingeben.")
            if ends_at <= starts_at:
                raise HTTPException(422, "Das Ende muss nach dem Beginn liegen.")
        entry = entry or SignageSpecial(screen_id=sid)
        entry.room_id, entry.event_id, entry.actor_id = room_id, event_id, user.id
        entry.preset, entry.mode = preset, mode
        entry.title = str(form.get("title") or "").strip()[:120] or default_title
        entry.message = str(form.get("message") or "").strip()[:250]
        entry.priority = _bounded(form, "priority", 0, 100, default_priority)
        entry.starts_at, entry.ends_at = starts_at, ends_at
        entry.published = form.get("published") == "1"
        db.add(entry)
    db.commit()
    flash(request, "Sonderanzeige gespeichert.")
    return redirect(f"/signage/{sid}/edit#special")
