"""Canonical, permission-safe organization responsibility for applications.

An organization assignment is a *direct* assignment to one active hierarchy
node, not permission to see all applications of its ancestors/descendants.
A node of kind 'gruppe' resolves through the canonical GroupMember table.
Other nodes use explicit OrgMembership rows. No global OrgRoleGrant('view')
nor automatic descendant expansion grants access to personal application data.
"""
from fastapi import HTTPException
from sqlalchemy import select

from .db import Group, GroupMember, Organization, User
from .org_models import OrgMembership
from . import organization


def validate(db, value) -> int | None:
    if value in (None, ""):
        return None
    try:
        oid = int(value)
    except (ValueError, TypeError):
        raise HTTPException(422, "Bitte eine gültige Organisationseinheit auswählen.")
    if oid <= 0 or not organization.active_path(db, oid):
        raise HTTPException(422, "Die Organisationseinheit ist nicht aktiv oder nicht vorhanden.")
    return oid


def member_ids(db, org_id: int | None) -> set[int]:
    if not org_id or not organization.active_path(db, org_id):
        return set()
    node = db.get(Organization, org_id)
    if node.kind == "gruppe":
        return set(db.scalars(
            select(GroupMember.user_id).join(Group, Group.id == GroupMember.group_id)
            .where(Group.org_id == org_id)))
    return set(db.scalars(select(OrgMembership.user_id).where(
        OrgMembership.org_id == org_id)))


def assigned_org_ids(db, user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    orgs = set(db.scalars(select(OrgMembership.org_id).where(
        OrgMembership.user_id.in_(user_ids))))
    orgs.update(db.scalars(
        select(Group.org_id).join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id.in_(user_ids),
               Group.org_id.is_not(None))))
    # Filter missing/inactive nodes; parent deactivation is also respected.
    return {oid for oid in orgs if organization.active_path(db, oid)}


def can_handle(db, user, org_id: int | None) -> bool:
    if not user or not user.active or not org_id:
        return False
    from . import absence
    return org_id in assigned_org_ids(db, absence.acting_ids(db, user))


def emails(db, org_id: int | None) -> list[str]:
    ids = member_ids(db, org_id)
    if not ids:
        return []
    return list(db.scalars(select(User.email).where(
        User.id.in_(ids), User.active.is_(True),
        User.email.is_not(None)).order_by(User.name)))


def options(db) -> list[tuple[int, str]]:
    from .orgs import tree
    return [(row.id, "— " * depth + row.name)
            for row, depth in tree(db, active_only=True)]
