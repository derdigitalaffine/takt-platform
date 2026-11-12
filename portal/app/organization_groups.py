"""Shared identity of TAKT user groups and organizational tree nodes.

Group and GroupMember remain the canonical identity and membership tables for
all existing invitations, task permissions, OIDC and every other module.
Their linked Organization is a normal movable hierarchy node, not a copy of
the group. Existing group nodes are created at the tree ROOT exactly once.
"""
from sqlalchemy import func, select
from fastapi import HTTPException

from .db import Group, GroupMember, Organization, User
from .org_models import OrgMembership, OrgRoleGrant

KIND = "gruppe"


def node_of(db, group: Group) -> Organization | None:
    return db.get(Organization, group.org_id) if group.org_id else None


def group_of(db, node: Organization | None) -> Group | None:
    if node is None or node.kind != KIND:
        return None
    return db.scalar(select(Group).where(Group.org_id == node.id))


def available_name(db, value: str, *, exclude_group: int | None = None) -> bool:
    name = value.strip()
    if not name or len(name) > 120:
        return False
    stmt = select(Group.id).where(func.lower(Group.name) == name.lower())
    if exclude_group is not None:
        stmt = stmt.where(Group.id != exclude_group)
    return db.scalar(stmt) is None


def ensure_node(db, group: Group) -> Organization:
    """Make a new root node for unlinked legacy/new groups; never reuse another
    Organization just because its name happens to be the same.
    """
    node = node_of(db, group)
    if node is not None:
        if node.kind != KIND:
            raise ValueError("A user group references a non-group organizational node")
        return node
    if group.org_id is not None:
        raise ValueError("A user group references a missing organizational node")
    node = Organization(name=group.name, kind=KIND, parent_id=None,
                        short_name="", note=group.description or "",
                        active=True, position=0)
    db.add(node)
    db.flush()
    group.org_id = node.id
    db.flush()
    return node


def ensure_all(db) -> int:
    """Startup migration, idempotent and safe when run repeatedly.

    Existing user groups are added as root nodes exactly once. Their stable
    group IDs, membership rows, lead, ACL and share references do not change.
    """
    created = 0
    for group in db.scalars(select(Group).order_by(Group.id)).all():
        if group.org_id is None:
            ensure_node(db, group)
            created += 1
        elif node_of(db, group) is None:
            raise ValueError(f"Group {group.id} references missing org node {group.org_id}")
    return created


def sync_from_group(db, group: Group) -> Organization:
    node = ensure_node(db, group)
    node.name = group.name
    node.note = group.description or ""
    return node


def sync_from_node(db, node: Organization, *, allow_create=False) -> Group:
    if node.kind != KIND:
        raise HTTPException(422, "Dies ist kein Benutzergruppenknoten.")
    group = group_of(db, node)
    name = " ".join((node.name or "").split())
    if not available_name(db, name, exclude_group=group.id if group else None):
        raise HTTPException(422, "Gruppenname bereits vorhanden oder länger als 120 Zeichen.")
    if group is None:
        if not allow_create:
            raise HTTPException(409, "Gruppenknoten ist nicht mit einer Benutzergruppe verknüpft.")
        group = Group(name=name, description=(node.note or "")[:255])
        db.add(group)
        db.flush()
        group.org_id = node.id
    else:
        group.name = name
        group.description = (node.note or "")[:255]
    return group


def set_group_members(db, group: Group, user_ids: set[int]) -> None:
    """Update manual membership while retaining external/OIDC-managed rows.

    GroupMember membership is the single source of truth; never create
    duplicate OrgMembership rows or turn group members into staffing entries.
    """
    if len(user_ids) > 5000:
        raise HTTPException(422, "Zu viele Mitglieder gewählt.")
    users = set(db.scalars(select(User.id).where(
        User.id.in_(user_ids), User.active.is_(True)))) if user_ids else set()
    if users != user_ids:
        raise HTTPException(422, "Bitte nur aktive Benutzer auswählen.")
    current = {m.user_id: m for m in db.scalars(
        select(GroupMember).where(GroupMember.group_id == group.id))}
    for uid, membership in current.items():
        if uid not in user_ids and membership.manual:
            db.delete(membership)
    for uid in user_ids - set(current):
        db.add(GroupMember(group_id=group.id, user_id=uid, manual=True))
    # Existing OIDC-managed memberships remain under provider control.


def removable(db, node: Organization) -> list[str]:
    """No dangling hierarchy or destructive deletion of a referenced group."""
    from .orgs import usage
    counts = usage(db, node)
    used = [name for name, count in counts.items() if count]
    # A group can be deleted only after children and scoped references are
    # moved/removed; legacy ACL/group shares have their own FK behaviour.
    return used
