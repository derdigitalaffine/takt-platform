"""Central authorization for organizational scopes; never grants global portal permissions."""

import json, re
from sqlalchemy import select, or_, update, func
from fastapi import HTTPException
from .db import Organization, User, Group, GroupMember, Setting
from .org_models import OrgKind, OrgState, OrgMembership, OrgRoleGrant, OrgAudit

ROLES = {
    "viewer": (
        "Bereich ansehen",
        {"view"},
        "Freigegebene Bereichsinformationen und Urlaubsplanungen sehen; keine Planung, Genehmigung oder Verwaltung.",
    ),
    "leave_settings": (
        "Urlaubsregeln verwalten",
        {"view", "leave_settings"},
        "Urlaubsablauf und Besetzungsregeln im freigegebenen Bereich einstellen; keine Rollen vergeben.",
    ),
    "lead": (
        "Leitung",
        {"view", "plan", "approve"},
        "Bereich ansehen, Planung und Genehmigungszuständigkeit; keine Rollen- oder Benutzerverwaltung.",
    ),
    "planner": (
        "Bereichsplanung",
        {"view", "plan"},
        "Planung im zugewiesenen Bereich; keine Genehmigung oder globale Rechte.",
    ),
    "approver": (
        "Genehmigung",
        {"view", "approve"},
        "Genehmigungszuständigkeit im Bereich; keine Konfigurationsrechte.",
    ),
    "members": (
        "Zuordnungen verwalten",
        {"view", "members"},
        "Personen im Bereich zuordnen; keine Konten, Gruppen oder Rollen ändern.",
    ),
    "settings": (
        "Bereichseinstellungen",
        {"view", "settings"},
        "Name und Kontakt der zugewiesenen Einheiten pflegen; keine Rollen vergeben oder Hierarchie verschieben.",
    ),
    "absences": (
        "Abwesenheiten verwalten",
        {"view", "absence_manage"},
        "Bestehende Abwesenheiten für die Hauptzuordnungen dieses Bereichs verwalten; kein globales Vertretungsrecht.",
    ),
}
DEFAULT_KINDS = {
    "verwaltung": "Verwaltung",
    "fachbereich": "Fachbereich",
    "sachgebiet": "Sachgebiet",
    "team": "Team",
    "arbeitsbereich": "Arbeitsbereich",
}


def seed(db):
    if db.get(OrgState, 1) is None:
        db.add(OrgState(id=1, version=1))
    if db.get(Setting, "migrated_organization_structure") is None:
        for key, label in DEFAULT_KINDS.items():
            if db.get(OrgKind, key) is None:
                db.add(OrgKind(key=key, label=label))
        db.add(Setting(key="migrated_organization_structure", value="1"))


def kinds(db):
    from .orgs import KINDS

    return {
        **KINDS,
        **{
            k.key: (k.label, "fa-sitemap", False)
            for k in db.scalars(select(OrgKind).order_by(OrgKind.label))
        },
    }


def grants(db, user):
    gids = select(GroupMember.group_id).where(GroupMember.user_id == user.id)
    return list(
        db.scalars(
            select(OrgRoleGrant).where(
                or_(OrgRoleGrant.user_id == user.id, OrgRoleGrant.group_id.in_(gids))
            )
        )
    )


def context(db, user):
    return dict(
        nodes={n.id: n for n in db.scalars(select(Organization))},
        grants=grants(db, user),
        own=set(
            db.scalars(
                select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)
            )
        ),
    )


def active_path(db, node_id, nodes=None):
    nodes = (
        nodes
        if nodes is not None
        else {n.id: n for n in db.scalars(select(Organization))}
    )
    path = []
    seen = set()
    while node_id:
        if node_id in seen:
            return []
        seen.add(node_id)
        node = nodes.get(node_id)
        if not node or not node.active:
            return []
        path.append(node_id)
        node_id = node.parent_id
    return path


def allows(db, user, node_id, cap="view", ctx=None):
    if not user or not user.active:
        return False
    if user.is_admin:
        return True
    global_right = {
        "structure": "orgs",
        "members": "org_members",
        "roles": "org_roles",
        "settings": "orgs",
    }.get(cap)
    if global_right and user.can(global_right):
        return True
    if cap == "view" and any(
        user.can(p) for p in ("users", "orgs", "org_members", "org_roles")
    ):
        return True
    ctx = ctx if ctx is not None else context(db, user)
    path = active_path(db, node_id, ctx["nodes"])
    if not path:
        return False
    if cap == "view" and node_id in ctx["own"]:
        return True
    return any(
        cap in ROLES.get(g.role, ("", set(), ""))[1]
        and g.org_id in path
        and (g.org_id == node_id or g.include_children)
        for g in ctx["grants"]
    )


def has_access(db, user):
    if not user:
        return False
    if user.is_admin or any(
        user.can(p) for p in ("users", "orgs", "org_members", "org_roles")
    ):
        return True
    return bool(
        db.scalar(select(OrgMembership.id).where(OrgMembership.user_id == user.id))
        or any(active_path(db, g.org_id) for g in grants(db, user))
    )


def require(db, user, node_id, cap):
    if not db.get(Organization, node_id):
        raise HTTPException(404, "Organisationseinheit nicht gefunden.")
    if not allows(db, user, node_id, cap):
        raise HTTPException(
            403, "Für diese Organisationseinheit fehlt die Berechtigung."
        )


def lock(db, raw):
    try:
        version = int(raw)
    except (ValueError, TypeError):
        raise HTTPException(409, "Bitte den aktuellen Organisationsstand laden.")
    result = db.execute(
        update(OrgState)
        .where(OrgState.id == 1, OrgState.version == version)
        .values(version=OrgState.version + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(
            409,
            "Die Organisation wurde inzwischen geändert. Bitte neu laden; Ihre Änderung wurde nicht gespeichert.",
        )
    db.expire_all()


def audit(db, actor, org_id, action, **detail):
    db.add(
        OrgAudit(
            actor_id=actor.id,
            org_id=org_id,
            action=action,
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )


def number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        raise HTTPException(422, "Bitte eine gültige Auswahl treffen.")


def set_membership(db, actor, data):
    oid = number(data.get("org_id"))
    uid = number(data.get("user_id"))
    require(db, actor, oid, "members")
    person = db.get(User, uid)
    if not person or not person.active:
        raise HTTPException(422, "Aktive Person wählen.")
    if not active_path(db, oid):
        raise HTTPException(
            422,
            "Zuordnungen benötigen eine aktive Organisationseinheit mit aktiven übergeordneten Einheiten.",
        )
    primary = db.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == uid, OrgMembership.is_primary.is_(True)
        )
    )
    main = data.get("is_primary") == "1" or primary is None or primary.org_id == oid
    if main and primary and primary.org_id != oid:
        require(db, actor, primary.org_id, "members")
        primary.is_primary = False
        db.flush()
    row = db.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == uid, OrgMembership.org_id == oid
        )
    )
    if row and row.is_primary and not main:
        raise HTTPException(422, "Zuerst eine andere Hauptzuordnung festlegen.")
    if row is None:
        row = OrgMembership(user_id=uid, org_id=oid)
        db.add(row)
    raw = data.get("staff_mode", "default")
    if raw not in {"default", "yes", "no"}:
        raise HTTPException(422, "Besetzungsrelevanz prüfen.")
    percent = number(data.get("capacity_percent", 100))
    if not 0 <= percent <= 100:
        raise HTTPException(
            422, "Einsatzanteil muss zwischen 0 und 100 Prozent liegen."
        )
    row.is_primary = main
    row.counts_staff = main if raw == "default" else raw == "yes"
    row.capacity_percent = percent
    audit(
        db,
        actor,
        oid,
        "membership",
        user=uid,
        primary=main,
        counts_staff=row.counts_staff,
        capacity_percent=percent,
    )
    return row


def delete_membership(db, actor, data):
    row = db.get(OrgMembership, number(data.get("membership")))
    if not row:
        raise HTTPException(404)
    require(db, actor, row.org_id, "members")
    if row.is_primary and db.scalar(
        select(OrgMembership.id).where(
            OrgMembership.user_id == row.user_id, OrgMembership.id != row.id
        )
    ):
        raise HTTPException(
            422,
            "Zuerst eine andere Hauptzuordnung festlegen; zusätzliche Zuordnungen bleiben erhalten.",
        )
    audit(db, actor, row.org_id, "membership_remove", user=row.user_id)
    db.delete(row)


def set_role(db, actor, data):
    oid = number(data.get("org_id"))
    require(db, actor, oid, "roles")
    if not active_path(db, oid):
        raise HTTPException(422, "Rollen nur für aktive Einheiten vergeben.")
    role = str(data.get("role", ""))
    kind, _, raw = str(data.get("target", "")).partition(":")
    target = number(raw)
    if role not in ROLES or kind not in {"user", "group"}:
        raise HTTPException(422, "Rolle und Person oder Gruppe prüfen.")
    obj = db.get(User if kind == "user" else Group, target)
    if not obj or kind == "user" and not obj.active:
        raise HTTPException(422, "Auswahl nicht verfügbar.")
    field = OrgRoleGrant.user_id if kind == "user" else OrgRoleGrant.group_id
    row = db.scalar(
        select(OrgRoleGrant).where(
            OrgRoleGrant.org_id == oid, field == target, OrgRoleGrant.role == role
        )
    )
    if row is None:
        row = OrgRoleGrant(
            org_id=oid,
            role=role,
            user_id=target if kind == "user" else None,
            group_id=target if kind == "group" else None,
        )
        db.add(row)
    row.include_children = data.get("include_children") == "1"
    audit(
        db,
        actor,
        oid,
        "role",
        target_kind=kind,
        target=target,
        role=role,
        include_children=row.include_children,
    )


def delete_role(db, actor, data):
    row = db.get(OrgRoleGrant, number(data.get("grant")))
    if not row:
        raise HTTPException(404)
    require(db, actor, row.org_id, "roles")
    audit(
        db,
        actor,
        row.org_id,
        "role_remove",
        role=row.role,
        user=row.user_id,
        group=row.group_id,
    )
    db.delete(row)


def protected_group(db, group_id):
    return bool(
        db.scalar(select(OrgRoleGrant.id).where(OrgRoleGrant.group_id == group_id))
    )


def check_group_changes(db, actor, before, after):
    if actor.is_admin or actor.can("org_roles"):
        return
    for gid in set(before) ^ set(after):
        if protected_group(db, gid):
            raise HTTPException(
                403,
                "Gruppen mit Bereichsrollen dürfen nur mit dem Recht „Organisationsrollen vergeben“ geändert werden.",
            )


def protected_user(db, user):
    return bool(grants(db, user))


def check_structure_change(db, actor, node, parent_id, active):
    """Moving or reactivating populated branches must not silently expand scoped authority."""
    if node is None or node.parent_id == parent_id and node.active == active:
        return
    from .orgs import tree, path

    nodes = {o.id: o for o, _ in tree(db)}
    ids = {node.id}
    changed = True
    while changed:
        more = {o.id for o in nodes.values() if o.parent_id in ids}
        changed = not more <= ids
        ids |= more
    role_scope = ids | {n.id for n in path(node)}
    if parent_id:
        role_scope |= {n.id for n in path(nodes[parent_id])}
    if db.scalar(
        select(OrgRoleGrant.id).where(OrgRoleGrant.org_id.in_(role_scope))
    ) and not (actor.is_admin or actor.can("org_roles")):
        raise HTTPException(
            403,
            "Für Strukturänderungen an Bereichen mit Rollen ist zusätzlich „Organisationsrollen vergeben“ erforderlich.",
        )
    if db.scalar(
        select(OrgMembership.id).where(OrgMembership.org_id.in_(ids))
    ) and not (actor.is_admin or actor.can("org_members")):
        raise HTTPException(
            403,
            "Für Strukturänderungen an zugeordneten Bereichen ist zusätzlich „Organisationszuordnungen verwalten“ erforderlich.",
        )


def scoped_people(db, user, cap, primary_only=False):
    ctx = context(db, user)
    ids = {o.id for o in ctx["nodes"].values() if allows(db, user, o.id, cap, ctx)}
    q = select(OrgMembership.user_id).where(OrgMembership.org_id.in_(ids))
    if primary_only:
        q = q.where(OrgMembership.is_primary.is_(True))
    return set(db.scalars(q))


def directory(db):
    """Batched profile summary for the existing user/group administration."""
    nodes = {o.id: o for o in db.scalars(select(Organization))}
    result = {}
    for m in db.scalars(
        select(OrgMembership).order_by(
            OrgMembership.is_primary.desc(), OrgMembership.id
        )
    ):
        result.setdefault(m.user_id, []).append(
            dict(id=m.org_id, name=nodes[m.org_id].name, primary=m.is_primary)
        )
    return result


def role_directory(db):
    memberships = {}
    for gid, uid in db.execute(select(GroupMember.group_id, GroupMember.user_id)):
        memberships.setdefault(gid, set()).add(uid)
    nodes = {o.id: o for o in db.scalars(select(Organization))}
    groups = {g.id: g for g in db.scalars(select(Group))}
    result = {}
    for grant in db.scalars(select(OrgRoleGrant)):
        users = (
            {grant.user_id} if grant.user_id else memberships.get(grant.group_id, set())
        )
        for uid in users:
            result.setdefault(uid, []).append(
                dict(
                    org_id=grant.org_id,
                    org=nodes[grant.org_id].name,
                    role=ROLES[grant.role][0],
                    source=groups[grant.group_id].name if grant.group_id else "direkt",
                    children=grant.include_children,
                )
            )
    return result
