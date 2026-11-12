"""Central digital-signage campaigns: create once, project to an entire building."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import calendars, signage, signage_campaign, signage_passive, signage_suggestions
from .calendar_models import Calendar, CalendarEvent
from .db import LOCAL_TZ, User, utcnow
from .main import app, check_csrf, flash, get_db, redirect, render
from .routes_signage import _enabled, _int, manage_user
from .signage_models import (
    SignageBuilding, SignageCampaign, SignageCampaignScreen, SignageFloor,
    SignagePassiveConfig, SignagePublicDestination, SignageRoom, SignageScreen,
    SignageGeneratedScreen, SignageRevision, SignageWayNode, SignageDisplayAnchor,
)

SCOPES = {
    "building": "Alle geeigneten Displays im Gebäude",
    "floor": "Displays auf einem Geschoss",
    "selected": "Nur gezielt ausgewählte Displays",
}


def _building(db, bid):
    _enabled()
    building = db.get(SignageBuilding, bid) if bid else None
    if not building or not building.active:
        raise HTTPException(422, "Bitte ein vorhandenes aktives Gebäude auswählen.")
    return building


def _room_in_building(db, room_id, building_id, *, public=False):
    room = db.get(SignageRoom, room_id) if room_id else None
    floor = db.get(SignageFloor, room.floor_id) if room else None
    if not floor or floor.building_id != building_id:
        raise HTTPException(422, "Der Zielraum gehört nicht zum gewählten Gebäude.")
    if public and not db.get(SignagePublicDestination, room.id):
        raise HTTPException(422, "Der Zielraum muss zuerst für Besucheranzeigen freigegeben werden.")
    return room


def _integer(value, minimum, maximum, default):
    try:
        number = int(value) if value not in ("", None) else default
    except (ValueError, TypeError):
        raise HTTPException(422, "Bitte eine gültige Zahl eingeben.")
    if not minimum <= number <= maximum:
        raise HTTPException(422, f"Zulässiger Bereich: {minimum} bis {maximum}.")
    return number


def _screen_candidates(db, building):
    # A building-wide campaign never targets another organization's screens.
    screens = db.scalars(select(SignageScreen).join(
        SignagePassiveConfig, SignagePassiveConfig.screen_id == SignageScreen.id
    ).where(SignagePassiveConfig.building_id == building.id).order_by(
        SignageScreen.name, SignageScreen.id)).all()
    return [screen for screen in screens
            if screen.kind in signage_passive.KINDS and screen.org_id == building.org_id]


def _source_calendars(db, user):
    return [row for row in db.scalars(select(Calendar).where(Calendar.source == "free")
                                      .order_by(Calendar.title))
            if calendars.access(db, user, row)]


@app.get("/signage/campaigns")
def signage_campaigns_page(request: Request, user: User = Depends(manage_user),
                           db: Session = Depends(get_db)):
    _enabled()
    buildings = list(db.scalars(select(SignageBuilding).where(
        SignageBuilding.active.is_(True)).order_by(SignageBuilding.name)))
    rooms = db.execute(select(SignageRoom, SignageFloor, SignageBuilding).join(
        SignageFloor, SignageRoom.floor_id == SignageFloor.id).join(
        SignageBuilding, SignageFloor.building_id == SignageBuilding.id).join(
        SignagePublicDestination, SignagePublicDestination.room_id == SignageRoom.id
    ).where(SignageBuilding.active.is_(True)).order_by(
        SignageBuilding.name, SignageFloor.level, SignageRoom.number)).all()
    floors = list(db.scalars(select(SignageFloor).order_by(SignageFloor.level)))
    screens = []
    for building in buildings:
        screens.extend([(item, building) for item in _screen_candidates(db, building)])
    current = _int(request.query_params.get("edit"))
    row = db.get(SignageCampaign, current) if current else None
    if current and not row:
        raise HTTPException(404)
    selected = {link.screen_id for link in db.scalars(select(SignageCampaignScreen).where(
        SignageCampaignScreen.campaign_id == current, SignageCampaignScreen.included.is_(True)))} if row else set()
    excluded = {link.screen_id for link in db.scalars(select(SignageCampaignScreen).where(
        SignageCampaignScreen.campaign_id == current, SignageCampaignScreen.included.is_(False)))} if row else set()
    listed = list(db.scalars(select(SignageCampaign).order_by(
        SignageCampaign.published.desc(), SignageCampaign.id.desc()).limit(200)))
    affected = {c.id: signage_campaign.assigned_screen_ids(db, c) for c in listed}
    conflicts = {c.id: signage_campaign.conflict_warnings(db, c) for c in listed if c.published}
    available_calendars = _source_calendars(db, user)
    calendar_id = _int(request.query_params.get("calendar"))
    source_events = []
    if calendar_id and any(calendar_id == cal.id for cal in available_calendars):
        q = select(CalendarEvent).where(CalendarEvent.calendar_id == calendar_id)
        source_events = [ev for ev in db.scalars(q.order_by(CalendarEvent.starts_at.desc()).limit(150))
                         if signage_passive.source_access(db, user, ev, SimpleNamespace(org_id=None))]
    suggested_event = None
    selected_suggestion_id = _int(request.query_params.get("suggest")) if not row else None
    if selected_suggestion_id and calendar_id in {cal.id for cal in available_calendars}:
        event = db.get(CalendarEvent, selected_suggestion_id)
        if (event and event.calendar_id == calendar_id
                and signage_passive.source_access(db, user, event, SimpleNamespace(org_id=None))):
            suggested_preset = signage_suggestions.classify_title(event.title)
            if suggested_preset:
                suggested_event = {
                    "id": event.id, "preset": suggested_preset,
                    "public_title": signage_passive.PRESETS[suggested_preset][0],
                }
                if all(item.id != event.id for item in source_events):
                    source_events.insert(0, event)
    suggestions = signage_suggestions.suggest(db, user)
    return render(request, "signage_campaigns.html", user,
        buildings=buildings, rooms=rooms, floors=floors, screens=screens,
        campaigns=listed, affected=affected, conflicts=conflicts,
        selected=selected, excluded=excluded, editing=row, calendars=available_calendars,
        source_events=source_events, selected_calendar=calendar_id,
        suggestions=suggestions, suggested_event=suggested_event,
        scopes=SCOPES, presets=signage_passive.PRESETS, now=utcnow(),
        local_now=datetime.now(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M"),
        start_local=(row.starts_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M")
                     if row and row.starts_at else ""),
        end_local=(row.ends_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M")
                   if row and row.ends_at else ""))


@app.post("/signage/campaigns/save", dependencies=[Depends(check_csrf)])
async def signage_campaign_save(request: Request, user: User = Depends(manage_user),
                                db: Session = Depends(get_db)):
    _enabled()
    form = await request.form()
    cid = _int(form.get("campaign_id"))
    campaign = db.get(SignageCampaign, cid) if cid else None
    if cid and not campaign:
        raise HTTPException(404)
    building = _building(db, _int(form.get("building_id")))
    room = _room_in_building(db, _int(form.get("room_id")), building.id,
                             public=form.get("published") == "1")
    preset = str(form.get("preset") or "event")
    scope = str(form.get("scope") or "building")
    mode = str(form.get("mode") or "overlay")
    if preset not in signage_passive.PRESETS or scope not in SCOPES or mode not in ("overlay", "replace"):
        raise HTTPException(422, "Vorlage, Anzeigebereich oder Darstellungsmodus prüfen.")
    floor_id = _int(form.get("floor_id")) if scope == "floor" else None
    if scope == "floor":
        floor = db.get(SignageFloor, floor_id) if floor_id else None
        if not floor or floor.building_id != building.id:
            raise HTTPException(422, "Das ausgewählte Geschoss gehört nicht zum Gebäude.")
    choices = set()
    for value in form.getlist("screen_ids"):
        screen_id = _int(value)
        if not screen_id:
            raise HTTPException(422, "Ungültige Display-ID.")
        choices.add(screen_id)
    exclusions = set()
    for value in form.getlist("excluded_ids"):
        screen_id = _int(value)
        if not screen_id:
            raise HTTPException(422, "Ungültige Display-ID.")
        exclusions.add(screen_id)
    available = {screen.id for screen in _screen_candidates(db, building)}
    if (choices | exclusions) - available or choices & exclusions:
        raise HTTPException(403, "Ein Display liegt außerhalb des gewählten Gebäudes.")
    if scope == "selected" and not choices:
        raise HTTPException(422, "Mindestens ein Display auswählen.")
    title = str(form.get("title") or "").strip()[:120] or signage_passive.PRESETS[preset][0]
    message = str(form.get("message") or "").strip()[:250]
    priority = _integer(form.get("priority"), 0, 100, signage_passive.PRESETS[preset][1])
    lead = _integer(form.get("lead_minutes"), 0, 240, 30)
    tail = _integer(form.get("tail_minutes"), 0, 240, 0)
    event_id = _int(form.get("event_id"))
    if form.get("event_id") and not event_id:
        raise HTTPException(422, "Ungültiger Kalendertermin.")
    starts = ends = None
    if event_id:
        event = db.get(CalendarEvent, event_id)
        if not signage_passive.source_access(
                db, user, event, SimpleNamespace(org_id=building.org_id)):
            raise HTTPException(403, "Der Kalendertermin ist nicht freigegeben.")
    else:
        try:
            starts = signage_passive.schedule_time(str(form.get("starts_at") or ""))
            ends = signage_passive.schedule_time(str(form.get("ends_at") or ""))
        except (ValueError, OverflowError):
            raise HTTPException(422, "Eindeutige Start- und Endzeit erforderlich.")
        if ends <= starts:
            raise HTTPException(422, "Das Ende muss nach dem Beginn liegen.")
    if campaign is None:
        campaign = SignageCampaign(created_by=user.id)
        db.add(campaign)
    campaign.building_id = building.id
    campaign.floor_id = floor_id
    campaign.room_id = room.id
    campaign.created_by = user.id
    campaign.event_id = event_id
    campaign.scope = scope
    campaign.preset, campaign.mode = preset, mode
    campaign.title, campaign.message = title, message
    campaign.priority = priority
    campaign.starts_at, campaign.ends_at = starts, ends
    campaign.lead_minutes, campaign.tail_minutes = lead, tail
    campaign.published = form.get("published") == "1"
    db.flush()
    db.query(SignageCampaignScreen).filter(
        SignageCampaignScreen.campaign_id == campaign.id).delete(synchronize_session=False)
    if scope == "selected":
        db.add_all(SignageCampaignScreen(campaign_id=campaign.id, screen_id=sid, included=True)
                   for sid in sorted(choices))
    else:
        db.add_all(SignageCampaignScreen(campaign_id=campaign.id, screen_id=sid, included=False)
                   for sid in sorted(exclusions))
    db.commit()
    affected = len(signage_campaign.assigned_screen_ids(db, campaign))
    flash(request, f"Sonderanzeige gespeichert. {affected} passende Displays werden automatisch berücksichtigt.")
    return redirect("/signage/campaigns")


@app.post("/signage/campaigns/{cid:int}/status", dependencies=[Depends(check_csrf)])
async def signage_campaign_status(cid: int, request: Request,
                                  user: User = Depends(manage_user),
                                  db: Session = Depends(get_db)):
    _enabled()
    campaign = db.get(SignageCampaign, cid)
    if not campaign:
        raise HTTPException(404)
    form = await request.form()
    action = form.get("action")
    if action == "withdraw":
        campaign.published = False
    elif action == "publish":
        _room_in_building(db, campaign.room_id, campaign.building_id, public=True)
        if campaign.event_id:
            event = db.get(CalendarEvent, campaign.event_id)
            building = _building(db, campaign.building_id)
            if not signage_passive.source_access(db, user, event,
                                                 SimpleNamespace(org_id=building.org_id)):
                raise HTTPException(403, "Kalenderfreigabe nicht mehr gültig.")
            campaign.created_by = user.id
        campaign.published = True
    elif action == "delete":
        db.delete(campaign)
    else:
        raise HTTPException(422)
    db.commit()
    flash(request, "Sonderbetrieb aktualisiert.")
    return redirect("/signage/campaigns")


@app.get("/signage/campaigns/simulate")
def signage_campaign_simulate(request: Request, user: User = Depends(manage_user),
                              db: Session = Depends(get_db)):
    """Read-only what-if projection for a chosen instant and building."""
    _enabled()
    bid = _int(request.query_params.get("building_id"))
    building = _building(db, bid)
    raw = str(request.query_params.get("at") or "").strip()
    try:
        at = signage_passive.schedule_time(raw).replace(tzinfo=timezone.utc) if raw else datetime.now(timezone.utc)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Simulationsdatum prüfen.")
    if abs((at - datetime.now(timezone.utc)).days) > 366:
        raise HTTPException(422, "Simulation maximal ein Jahr in die Zukunft oder Vergangenheit.")
    preview = []
    for screen in _screen_candidates(db, building)[:80]:
        _, special, _ = signage_passive.project(db, screen, at)
        preview.append({"screen": screen, "special": special})
    return render(request, "signage_campaign_simulation.html", user,
                  building=building, at=at, preview=preview)


@app.post("/signage/generate", dependencies=[Depends(check_csrf)])
async def signage_generate_for_building(request: Request,
                                        user: User = Depends(manage_user),
                                        db: Session = Depends(get_db)):
    """Create private starter displays for a building without duplicate entries.

    Flur displays get their real graph node but no invented viewing direction.
    A human still validates sightlines and explicitly publishes the screens.
    """
    _enabled()
    form = await request.form()
    building = _building(db, _int(form.get("building_id")))
    with_building = form.get("building") == "1"
    with_floors = form.get("floors") == "1"
    with_corridors = form.get("corridors") == "1"
    if not any((with_building, with_floors, with_corridors)):
        raise HTTPException(422, "Mindestens einen Anzeigetyp auswählen.")
    floors = list(db.scalars(select(SignageFloor).where(
        SignageFloor.building_id == building.id).order_by(SignageFloor.level, SignageFloor.id)).all())
    requests = []
    if with_building:
        requests.append((f"building:{building.id}", "sign_building", f"{building.name} · Gebäudeübersicht", None, None))
    if with_floors:
        requests.extend((f"floor:{floor.id}", "sign_floor",
                         f"{building.name} · {floor.name} · Geschossübersicht", floor.id, None)
                        for floor in floors)
    if with_corridors:
        for floor in floors:
            nodes = db.scalars(select(SignageWayNode).where(
                SignageWayNode.floor_id == floor.id,
                SignageWayNode.room_id.is_(None),
                SignageWayNode.kind.in_(("entrance", "corridor"))
            ).order_by(SignageWayNode.id).limit(30)).all()
            requests.extend((f"corridor:{node.id}", "sign_corridor",
                             f"{building.name} · {floor.name} · {node.label}",
                             floor.id, node.id) for node in nodes)
    if len(requests) > 90:
        raise HTTPException(422, "Zu viele automatische Anzeigen. Gebäude in Etappen einrichten.")
    created = []
    for key, kind, name, floor_id, node_id in requests:
        if db.scalar(select(SignageGeneratedScreen).where(
                SignageGeneratedScreen.generator_key == key)) is not None:
            continue
        screen = SignageScreen(
            name=name[:180], kind=kind, visibility="private", owner_id=user.id,
            org_id=building.org_id, enabled=True,
            layout_json=json.dumps(signage.TEMPLATES[kind]))
        db.add(screen)
        db.flush()
        db.add(SignagePassiveConfig(
            screen_id=screen.id, building_id=building.id, floor_id=floor_id,
            facing="", radius_m=25))
        if node_id:
            db.add(SignageDisplayAnchor(screen_id=screen.id, node_id=node_id))
        db.add(SignageRevision(screen_id=screen.id, version=1,
                               snapshot_json=signage.design_snapshot(screen), actor_id=user.id))
        db.add(SignageGeneratedScreen(generator_key=key, screen_id=screen.id))
        created.append(screen.id)
    db.commit()
    flash(request, f"{len(created)} interne Displays vorbereitet. Vor öffentlicher Freigabe Blickrichtung und Ziele prüfen.")
    return redirect(f"/signage/{created[0]}/edit" if len(created) == 1 else "/signage")
