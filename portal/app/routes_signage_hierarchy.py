"""Hierarchical building browser and dependency-safe Signage CRUD.

Existing canonical building/floor/room IDs never change when a wing/annex is
added. The part-floor table is optional; old installations need no migration.
"""
from collections import defaultdict

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import calendars, signage_passive
from .calendar_models import Calendar
from .db import Organization, PortalLocation, Resource, User
from .main import app, check_csrf, flash, get_db, redirect, render
from .routes_signage import _enabled, _int, _signage_context, _screen, manage_user
from .signage_models import (
    SignageBuilding, SignageBuildingPart, SignagePartFloor, SignageFloor,
    SignageRoom, SignageScreen, SignageOffice, SignagePublicDestination,
    SignageDestinationOverride, SignagePassiveConfig, SignageCampaign,
    SignageCampaignScreen, SignageSpecial, SignageWayNode, SignageDisplayAnchor,
    SignageGeneratedScreen, SignageLink, SignageDevice, SignageDeviceTelemetry,
    SignageRevision,
)

KINDS = {"building": SignageBuilding, "part": SignageBuildingPart,
         "floor": SignageFloor, "room": SignageRoom}
PART_KINDS = {"wing": "Gebäudeflügel", "annex": "Anbau / Nebengebäude",
              "section": "Gebäudebereich", "other": "Sonstiger Gebäudeteil"}


def _exists(db, model, *conditions):
    return db.scalar(select(model.id).where(*conditions).limit(1)) is not None


def _label(data, key, maximum, *, required=True):
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise HTTPException(422, f"{key}: Bezeichnung erforderlich.")
    if len(value) > maximum:
        raise HTTPException(422, f"{key}: höchstens {maximum} Zeichen.")
    return value


def _integer(data, key, minimum, maximum, default=0):
    try:
        val = int(data.get(key) if str(data.get(key) or "").strip() else default)
    except (TypeError, ValueError):
        raise HTTPException(422, "Ungültige Zahl.")
    if val < minimum or val > maximum:
        raise HTTPException(422, "Zahl außerhalb des erlaubten Bereichs.")
    return val


def _require(db, kind, ident):
    model = KINDS.get(kind)
    obj = db.get(model, ident) if model else None
    if not obj:
        raise HTTPException(404, "Gebäudeelement nicht gefunden.")
    return obj


def _part_parent(db, building_id, parent_id, *, self_id=None):
    if not parent_id:
        return None
    if parent_id == self_id:
        raise HTTPException(422, "Ein Gebäudeteil kann sich nicht selbst enthalten.")
    parent = db.get(SignageBuildingPart, parent_id)
    if not parent or parent.building_id != building_id:
        raise HTTPException(422, "Elternbereich liegt nicht im ausgewählten Gebäude.")
    seen = set()
    while parent:
        if parent.id in seen or parent.id == self_id:
            raise HTTPException(422, "Zyklische Gebäudehierarchie ist nicht erlaubt.")
        seen.add(parent.id)
        parent = db.get(SignageBuildingPart, parent.parent_id) if parent.parent_id else None
    return parent_id


def _part_for_floor(db, floor, part_id):
    if not part_id:
        return None
    part = db.get(SignageBuildingPart, part_id)
    if not part or part.building_id != floor.building_id:
        raise HTTPException(422, "Gebäudeteil und Geschoss gehören zu verschiedenen Gebäuden.")
    return part


def _set_floor_part(db, floor, part_id):
    _part_for_floor(db, floor, part_id)
    mapping = db.get(SignagePartFloor, floor.id)
    if part_id:
        if mapping:
            mapping.part_id = part_id
        else:
            db.add(SignagePartFloor(floor_id=floor.id, part_id=part_id))
    elif mapping:
        db.delete(mapping)


def _room_sources(db, user, data, room):
    resource_id = _int(data.get("resource_id"))
    calendar_id = _int(data.get("calendar_id"))
    if str(data.get("resource_id") or "").strip() and not resource_id:
        raise HTTPException(422, "Ungültige Ressource.")
    if str(data.get("calendar_id") or "").strip() and not calendar_id:
        raise HTTPException(422, "Ungültiger Kalender.")
    if resource_id and not db.get(Resource, resource_id):
        raise HTTPException(422, "Ressource nicht gefunden.")
    calendar = db.get(Calendar, calendar_id) if calendar_id else None
    if calendar_id and (not calendar or calendar.source != "free"
                        or not calendars.access(db, user, calendar)):
        raise HTTPException(403, "Kein Zugriff auf den Raumkalender.")
    room.resource_id = resource_id
    room.calendar_id = calendar_id


def blockers(db, kind, obj):
    """Dependencies that must be managed before destructive hierarchy changes."""
    checks = []
    if kind == "building":
        checks = [
            ("Geschosse", SignageFloor, SignageFloor.building_id == obj.id),
            ("Gebäudeteile", SignageBuildingPart, SignageBuildingPart.building_id == obj.id),
            ("Passive Anzeigen", SignagePassiveConfig, SignagePassiveConfig.building_id == obj.id),
            ("Sonderanzeigen", SignageCampaign, SignageCampaign.building_id == obj.id),
        ]
    elif kind == "part":
        checks = [
            ("Untergeordnete Gebäudeteile", SignageBuildingPart, SignageBuildingPart.parent_id == obj.id),
            ("Zugeordnete Geschosse", SignagePartFloor, SignagePartFloor.part_id == obj.id),
        ]
    elif kind == "floor":
        checks = [
            ("Räume", SignageRoom, SignageRoom.floor_id == obj.id),
            ("Wegepunkte", SignageWayNode, SignageWayNode.floor_id == obj.id),
            ("Anzeigen", SignagePassiveConfig, SignagePassiveConfig.floor_id == obj.id),
            ("Sonderanzeigen", SignageCampaign, SignageCampaign.floor_id == obj.id),
        ]
    elif kind == "room":
        checks = [
            ("Raumanzeigen", SignageScreen, SignageScreen.room_id == obj.id),
            ("Bürozuordnungen", SignageOffice, SignageOffice.room_id == obj.id),
            ("Wegepunkte", SignageWayNode, SignageWayNode.room_id == obj.id),
            ("Sonderanzeigen", SignageSpecial, SignageSpecial.room_id == obj.id),
            ("Gebäudeaktionen", SignageCampaign, SignageCampaign.room_id == obj.id),
            ("Anzeigeausnahmen", SignageDestinationOverride, SignageDestinationOverride.room_id == obj.id),
        ]
    return [label for label, model, predicate in checks if _exists(db, model, predicate)]


def _select_context(db, user, query):
    all_data = _signage_context(db, user)
    buildings, floors, rooms = all_data["buildings"], all_data["floors"], all_data["rooms"]
    parts = list(db.scalars(select(SignageBuildingPart).order_by(
        SignageBuildingPart.name, SignageBuildingPart.id)))
    assignments = list(db.scalars(select(SignagePartFloor)))
    membership = {item.floor_id: item.part_id for item in assignments}
    room_groups = defaultdict(list)
    for room in rooms:
        room_groups[room.floor_id].append(room)
    floor_groups = defaultdict(list)
    for floor in floors:
        floor_groups[floor.building_id].append(floor)
    part_groups = defaultdict(list)
    for part in parts:
        part_groups[part.building_id].append(part)

    selected_kind = "building"
    selected_id = buildings[0].id if buildings else None
    raw = str(query or "").split(":")
    if len(raw) == 2 and raw[0] in KINDS and raw[1].isdigit():
        selected_kind, selected_id = raw[0], int(raw[1])
    selected = db.get(KINDS[selected_kind], selected_id) if selected_id else None
    if not selected and buildings:
        selected_kind, selected = "building", buildings[0]

    def part_node(part, stack=None):
        stack = stack or set()
        if part.id in stack:
            return None
        branch = stack | {part.id}
        nested = [part_node(child, branch) for child in part_groups[part.building_id]
                  if child.parent_id == part.id]
        return {
            "part": part,
            "parts": [child for child in nested if child],
            "floors": [{"floor": floor, "rooms": room_groups[floor.id]}
                       for floor in floor_groups[part.building_id]
                       if membership.get(floor.id) == part.id],
        }

    tree = []
    for building in buildings:
        tree.append({
            "building": building,
            "parts": [node for part in part_groups[building.id] if not part.parent_id
                      for node in [part_node(part)] if node],
            "floors": [{"floor": floor, "rooms": room_groups[floor.id]}
                       for floor in floor_groups[building.id]
                       if floor.id not in membership],
        })
    selected_building_id = None
    if selected:
        if selected_kind == "building":
            selected_building_id = selected.id
        elif selected_kind == "part":
            selected_building_id = selected.building_id
        elif selected_kind == "floor":
            selected_building_id = selected.building_id
        else:
            selected_floor = db.get(SignageFloor, selected.floor_id)
            selected_building_id = selected_floor.building_id if selected_floor else None
    selected_floor_mapping = db.get(SignagePartFloor, selected.id) if selected_kind == "floor" and selected else None
    return {
        **all_data,
        "tree": tree, "parts": parts, "floor_parts": membership,
        "selected_kind": selected_kind, "selected": selected,
        "selected_building_id": selected_building_id,
        "selected_floor_mapping": selected_floor_mapping,
        "blockers": blockers(db, selected_kind, selected) if selected else [],
        "part_kinds": PART_KINDS,
    }


@app.get("/signage/buildings")
def signage_building_browser(request: Request, user: User = Depends(manage_user),
                            db: Session = Depends(get_db)):
    _enabled()
    return render(request, "signage_buildings.html", user,
                  **_select_context(db, user, request.query_params.get("select")))


@app.post("/signage/hierarchy/create", dependencies=[Depends(check_csrf)])
async def signage_hierarchy_create(request: Request, user: User = Depends(manage_user),
                                   db: Session = Depends(get_db)):
    _enabled()
    form = await request.form()
    kind = str(form.get("kind") or "")
    if kind not in KINDS:
        raise HTTPException(422)
    name = _label(form, "name", 40 if kind == "room" else 100 if kind == "floor" else 120 if kind == "part" else 180)
    if kind == "building":
        location_id, org_id = _int(form.get("location_id")), _int(form.get("org_id"))
        if location_id and not db.get(PortalLocation, location_id) or org_id and not db.get(Organization, org_id):
            raise HTTPException(422, "Ungültiger Standort oder Organisation.")
        obj = SignageBuilding(name=name, code=_label(form, "code", 40, required=False),
                              location_id=location_id, org_id=org_id, active=True)
    elif kind == "part":
        bid = _int(form.get("building_id"))
        building = db.get(SignageBuilding, bid) if bid else None
        if not building:
            raise HTTPException(422, "Gebäude auswählen.")
        part_kind = str(form.get("part_kind") or "wing")
        if part_kind not in PART_KINDS:
            raise HTTPException(422, "Ungültiger Gebäudeteil-Typ.")
        obj = SignageBuildingPart(building_id=building.id,
                                 parent_id=_part_parent(db, building.id, _int(form.get("parent_id"))),
                                 name=name, kind=part_kind,
                                 code=_label(form, "code", 32, required=False),
                                 description=_label(form, "description", 250, required=False))
    elif kind == "floor":
        bid = _int(form.get("building_id"))
        if not bid or not db.get(SignageBuilding, bid):
            raise HTTPException(422, "Gebäude nicht vorhanden.")
        obj = SignageFloor(building_id=bid, name=name,
                           level=_integer(form, "level", -20, 200))
    else:
        fid = _int(form.get("floor_id"))
        if not fid or not db.get(SignageFloor, fid):
            raise HTTPException(422, "Geschoss nicht vorhanden.")
        obj = SignageRoom(floor_id=fid, number=name,
                          name=_label(form, "label", 180, required=False),
                          accessible=form.get("accessible") == "1")
        _room_sources(db, user, form, obj)
    db.add(obj)
    try:
        db.flush()
        if kind == "floor":
            _set_floor_part(db, obj, _int(form.get("part_id")))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Name, Zimmernummer oder Geschossebene bereits vorhanden.")
    flash(request, "Gebäudeelement angelegt.")
    return redirect(f"/signage/buildings?select={kind}:{obj.id}")


@app.post("/signage/hierarchy/{kind}/{item_id:int}/save", dependencies=[Depends(check_csrf)])
async def signage_hierarchy_save(kind: str, item_id: int, request: Request,
                                 user: User = Depends(manage_user),
                                 db: Session = Depends(get_db)):
    _enabled()
    obj = _require(db, kind, item_id)
    form = await request.form()
    name = _label(form, "name", 40 if kind == "room" else 100 if kind == "floor" else 120 if kind == "part" else 180)
    if kind == "building":
        location_id, org_id = _int(form.get("location_id")), _int(form.get("org_id"))
        if location_id and not db.get(PortalLocation, location_id) or org_id and not db.get(Organization, org_id):
            raise HTTPException(422)
        if obj.org_id != org_id and (
                _exists(db, SignagePassiveConfig, SignagePassiveConfig.building_id == obj.id)
                or _exists(db, SignageCampaign, SignageCampaign.building_id == obj.id)):
            raise HTTPException(409, "Mit bestehenden Anzeigen oder Aktionen ist der Organisationswechsel gesperrt.")
        obj.name, obj.code = name, _label(form, "code", 40, required=False)
        obj.location_id, obj.org_id = location_id, org_id
        obj.active = form.get("active") == "1"
    elif kind == "part":
        part_kind = str(form.get("part_kind") or "wing")
        if part_kind not in PART_KINDS:
            raise HTTPException(422)
        obj.parent_id = _part_parent(db, obj.building_id, _int(form.get("parent_id")), self_id=obj.id)
        obj.name, obj.kind = name, part_kind
        obj.code = _label(form, "code", 32, required=False)
        obj.description = _label(form, "description", 250, required=False)
        obj.active = form.get("active") == "1"
    elif kind == "floor":
        obj.name, obj.level = name, _integer(form, "level", -20, 200, obj.level)
        _set_floor_part(db, obj, _int(form.get("part_id")))
    else:
        obj.number, obj.name = name, _label(form, "label", 180, required=False)
        obj.accessible = form.get("accessible") == "1"
        _room_sources(db, user, form, obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Gebäudehierarchie enthält eine doppelte Nummer oder einen Konflikt.")
    flash(request, "Änderungen gespeichert.")
    return redirect(f"/signage/buildings?select={kind}:{item_id}")


@app.post("/signage/hierarchy/{kind}/{item_id:int}/delete", dependencies=[Depends(check_csrf)])
async def signage_hierarchy_delete(kind: str, item_id: int, request: Request,
                                   user: User = Depends(manage_user),
                                   db: Session = Depends(get_db)):
    _enabled()
    obj = _require(db, kind, item_id)
    form = await request.form()
    expected = obj.number if kind == "room" else obj.name
    if str(form.get("confirm") or "") != expected:
        raise HTTPException(422, "Zum Löschen die exakte Bezeichnung eingeben.")
    blocked = blockers(db, kind, obj)
    if blocked:
        raise HTTPException(409, "Löschen gesperrt. Zuerst entfernen: " + ", ".join(blocked))
    if kind == "room":
        db.execute(delete(SignagePublicDestination).where(
            SignagePublicDestination.room_id == item_id))
    elif kind == "floor":
        db.execute(delete(SignagePartFloor).where(SignagePartFloor.floor_id == item_id))
    db.delete(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dieses Element wird noch verwendet und kann nicht gelöscht werden.")
    flash(request, "Gebäudeelement endgültig gelöscht.")
    return redirect("/signage/buildings")


@app.get("/signage/{sid:int}/delete")
def signage_screen_delete_page(sid: int, request: Request,
                               user: User = Depends(manage_user),
                               db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    devices = list(db.scalars(select(SignageDevice).where(SignageDevice.screen_id == sid)))
    links = list(db.scalars(select(SignageLink).where(SignageLink.screen_id == sid)))
    campaigns = list(db.scalars(select(SignageCampaignScreen).where(
        SignageCampaignScreen.screen_id == sid)))
    revisions = list(db.scalars(select(SignageRevision).where(
        SignageRevision.screen_id == sid)))
    return render(request, "signage_delete_screen.html", user,
                  screen=screen, devices=devices, links=links,
                  campaigns=campaigns, revisions=revisions)


@app.post("/signage/{sid:int}/delete", dependencies=[Depends(check_csrf)])
async def signage_screen_delete(sid: int, request: Request,
                                user: User = Depends(manage_user),
                                db: Session = Depends(get_db)):
    screen = _screen(db, sid)
    form = await request.form()
    if (str(form.get("confirm") or "") != screen.name
            or str(form.get("version") or "") != str(screen.version)):
        raise HTTPException(409, "Anzeigename oder Bearbeitungsversion stimmt nicht überein.")
    device_ids = select(SignageDevice.id).where(SignageDevice.screen_id == sid)
    db.execute(delete(SignageDeviceTelemetry).where(SignageDeviceTelemetry.device_id.in_(device_ids)))
    for model in (SignageDevice, SignageLink, SignageRevision, SignageSpecial,
                  SignageDisplayAnchor, SignagePassiveConfig, SignageDestinationOverride,
                  SignageCampaignScreen, SignageGeneratedScreen):
        db.execute(delete(model).where(model.screen_id == sid))
    db.delete(screen)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Anzeige wird noch verwendet.")
    flash(request, "Anzeige und alle Geräte-/Freigabezugänge endgültig gelöscht.")
    return redirect("/signage/screens")
