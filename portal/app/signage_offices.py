"""Consistent Signage workplace assignments across admin, room board and profile."""
from sqlalchemy import select
from fastapi import HTTPException

from .db import Organization, User
from .org_models import OrgMembership
from .signage_models import (
    SignageOffice, SignageRoom, SignageFloor, SignageBuilding
)


def active_room(db, room_id):
    row = db.execute(select(SignageRoom, SignageFloor, SignageBuilding)
        .join(SignageFloor, SignageRoom.floor_id == SignageFloor.id)
        .join(SignageBuilding, SignageFloor.building_id == SignageBuilding.id)
        .where(SignageRoom.id == room_id, SignageBuilding.active.is_(True))).first()
    if not row:
        raise HTTPException(422, "Raum oder Gebäude ist nicht verfügbar.")
    return row


def permitted_for_self(db, user, room_id):
    """Allow own office only in a fitting organizational branch, or unscoped sites."""
    room, floor, building = active_room(db, room_id)
    if user.is_admin or building.org_id is None:
        return room
    memberships = db.scalars(select(OrgMembership.org_id).where(
        OrgMembership.user_id == user.id)).all()
    if not memberships:
        raise HTTPException(403, "Dieser Standort gehört nicht zu deinen Organisationseinheiten.")
    nodes = {o.id: o.parent_id for o in db.scalars(select(Organization))}
    def path(org_id):
        out = set()
        while org_id and org_id not in out:
            out.add(org_id)
            org_id = nodes.get(org_id)
        return out
    building_path = path(building.org_id)
    if not any(building.org_id in path(oid) or oid in building_path for oid in memberships):
        raise HTTPException(403, "Dieser Standort gehört nicht zu deinen Organisationseinheiten.")
    return room


def assign(db, *, user_id, room_id, make_primary=False):
    person = db.get(User, user_id)
    if not person or not person.active:
        raise HTTPException(422, "Person nicht vorhanden oder nicht aktiv.")
    active_room(db, room_id)
    current = db.scalar(select(SignageOffice).where(
        SignageOffice.user_id == user_id, SignageOffice.room_id == room_id))
    if current is None:
        current = SignageOffice(user_id=user_id, room_id=room_id, public=False,
                                is_primary=False)
        db.add(current)
    other = db.scalars(select(SignageOffice).where(
        SignageOffice.user_id == user_id, SignageOffice.room_id != room_id)).all()
    if make_primary or not any(item.is_primary for item in other):
        current.is_primary = True
        for item in other:
            item.is_primary = False
    db.flush()
    return current


def remove(db, office):
    """Remove one location only; select a consistent new primary if needed."""
    uid, is_primary = office.user_id, office.is_primary
    db.delete(office)
    db.flush()
    if is_primary:
        next_one = db.scalar(select(SignageOffice).where(
            SignageOffice.user_id == uid).order_by(SignageOffice.id).limit(1))
        if next_one:
            next_one.is_primary = True
