"""Organization tree, person assignments and explicit scoped roles."""

import re
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import Organization, User, Group
from .org_models import OrgMembership, OrgRoleGrant, OrgAudit, OrgKind, OrgState
from . import organization as os, orgs
from .main import app, current_user, get_db, check_csrf, render, redirect, flash


def view(request, user, db, unit=None, person=None, group=None, error="", form=None):
    if not os.has_access(db, user):
        raise HTTPException(403, "Kein Organisationsbereich freigegeben.")
    all_rows = orgs.tree(db)
    nodes = {o.id: o for o, _ in all_rows}
    scope = os.context(db, user)
    access = {
        o.id: {
            cap: os.allows(db, user, o.id, cap, scope)
            for cap in ("view", "members", "roles", "settings", "structure")
        }
        for o, _ in all_rows
    }
    visible = {oid for oid, caps in access.items() if caps["view"]}
    ancestors = set()
    for oid in visible:
        for node in orgs.path(nodes[oid]):
            ancestors.add(node.id)
    rows = [(o, d) for o, d in all_rows if o.id in ancestors]
    if unit is not None and unit not in visible:
        raise HTTPException(403, "Diese Einheit ist nicht freigegeben.")
    if unit is None and person is not None:
        unit = db.scalar(
            select(OrgMembership.org_id)
            .where(OrgMembership.user_id == person, OrgMembership.org_id.in_(visible))
            .order_by(OrgMembership.is_primary.desc())
        )
    if unit is None and group is not None:
        unit = db.scalar(
            select(OrgRoleGrant.org_id).where(
                OrgRoleGrant.group_id == group, OrgRoleGrant.org_id.in_(visible)
            )
        )
    if unit is None and visible:
        unit = next(o.id for o, _ in rows if o.id in visible)
    selected = nodes.get(unit)
    caps = access.get(unit, {})
    memberships = list(
        db.scalars(
            select(OrgMembership).order_by(
                OrgMembership.is_primary.desc(), OrgMembership.user_id
            )
        )
    )
    shown = [
        m
        for m in memberships
        if m.org_id == unit and (person is None or m.user_id == person)
    ]
    all_grants = list(
        db.scalars(select(OrgRoleGrant).order_by(OrgRoleGrant.role, OrgRoleGrant.id))
    )
    path = {node.id for node in orgs.path(selected)} if selected else set()
    role_rows = [
        g
        for g in all_grants
        if (g.org_id == unit or g.include_children and g.org_id in path)
        and (group is None or g.group_id == group)
    ]
    people = {p.id: p for p in db.scalars(select(User).order_by(User.name))}
    groups = {g.id: g for g in db.scalars(select(Group).order_by(Group.name))}
    own = [m for m in memberships if m.user_id == user.id]
    audit = []
    if unit and any(caps.get(c) for c in ("members", "roles", "settings", "structure")):
        audit = list(
            db.scalars(
                select(OrgAudit)
                .where(OrgAudit.org_id == unit)
                .order_by(OrgAudit.id.desc())
                .limit(20)
            )
        )
    return render(
        request,
        "organization.html",
        user,
        org_rows=rows,
        org_nodes=nodes,
        org_access=access,
        selected=selected,
        caps=caps,
        memberships=shown,
        own_memberships=own,
        people=people,
        org_groups=groups,
        role_rows=role_rows,
        org_roles=os.ROLES,
        org_kinds=os.kinds(db),
        org_custom_kinds=list(db.scalars(select(OrgKind).order_by(OrgKind.label))),
        org_version=db.get(OrgState, 1).version,
        membership_edit=next((m for m in shown if m.user_id == person), None),
        org_audit=audit,
        person_filter=person,
        group_filter=group,
        error=error,
        form_data=form or {},
    )


@app.get("/admin/organization")
def organization_page(
    request: Request,
    unit: int | None = None,
    person: int | None = None,
    group: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return view(request, user, db, unit, person, group)


@app.post("/admin/organization", dependencies=[Depends(check_csrf)])
async def organization_action(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    data = await request.form()
    action = str(data.get("action", ""))
    oid = os.number(data["org_id"]) if data.get("org_id") else None
    try:
        if not os.has_access(db, user):
            raise HTTPException(403)
        os.lock(db, data.get("version"))
        if action == "membership":
            os.set_membership(db, user, data)
        elif action == "membership_remove":
            os.delete_membership(db, user, data)
        elif action == "role":
            os.set_role(db, user, data)
        elif action == "role_remove":
            os.delete_role(db, user, data)
        elif action in {"unit_create", "unit_save"}:
            existing = db.get(Organization, oid) if action == "unit_save" else None
            if action == "unit_save":
                os.require(db, user, oid, "settings")
            elif not user.can("orgs"):
                raise HTTPException(403)
            parent_id = os.number(data["parent_id"]) if data.get("parent_id") else None
            parent = db.get(Organization, parent_id) if parent_id else None
            if parent_id and not parent:
                raise HTTPException(422, "Übergeordnete Einheit nicht gefunden.")
            values, errors = orgs.clean(data, existing, os.kinds(db))
            if errors:
                raise HTTPException(422, " ".join(errors))
            if str(data.get("kind", "")) not in os.kinds(db):
                raise HTTPException(422, "Gültigen Ebenentyp wählen.")
            if existing and not user.can("orgs"):
                if (
                    parent_id != existing.parent_id
                    or values["kind"] != existing.kind
                    or (data.get("active") == "1") != existing.active
                ):
                    raise HTTPException(
                        403,
                        "Hierarchie, Ebenentyp und Aktivierung sind nur mit globalen Strukturrechten änderbar.",
                    )
                keys = ("name", "short_name", "contact", "phone", "email", "website")
            else:
                if existing and parent and orgs.would_cycle(existing, parent):
                    raise HTTPException(
                        422,
                        "Eine Einheit kann nicht unter sich selbst oder ihren Untereinheiten liegen.",
                    )
                os.check_structure_change(
                    db, user, existing, parent_id, data.get("active") == "1"
                )
                keys = values.keys()
            row = existing or Organization()
            for key in keys:
                if existing is None or key in data:
                    setattr(row, key, values[key])
            if user.can("orgs"):
                row.parent = parent
                row.active = data.get("active") == "1"
            if existing is None:
                db.add(row)
            db.flush()
            oid = row.id
            os.audit(db, user, oid, "unit_save", name=row.name, parent=row.parent_id)
        elif action in {"kind", "kind_remove"}:
            if not user.can("orgs"):
                raise HTTPException(403)
            key = str(data.get("key", "")).strip()
            if action == "kind":
                from .orgs import KINDS

                label = " ".join(str(data.get("label", "")).split())
                if (
                    not re.fullmatch("[a-z][a-z0-9_]{0,19}", key)
                    or key in KINDS
                    or not label
                    or len(label) > 100
                ):
                    raise HTTPException(
                        422,
                        "Typ benötigt einen eindeutigen Schlüssel (a-z, 0-9, _, maximal 20 Zeichen) und einen Namen.",
                    )
                row = db.get(OrgKind, key)
                if row is None:
                    row = OrgKind(key=key, label=label)
                    db.add(row)
                else:
                    row.label = label
            else:
                row = db.get(OrgKind, key)
                if not row:
                    raise HTTPException(404)
                if db.scalar(select(Organization.id).where(Organization.kind == key)):
                    raise HTTPException(422, "Der Ebenentyp wird noch verwendet.")
                db.delete(row)
            os.audit(db, user, None, action, key=key)
        else:
            raise HTTPException(422, "Aktion nicht verfügbar.")
        db.commit()
    except HTTPException as exc:
        db.rollback()
        if exc.status_code not in {409, 422}:
            raise
        page = view(
            request,
            user,
            db,
            (
                oid
                if oid and db.get(Organization, oid) and os.allows(db, user, oid)
                else None
            ),
            error=str(exc.detail),
            form=dict(data),
        )
        page.status_code = exc.status_code
        return page
    flash(request, "Organisation gespeichert.")
    return redirect("/admin/organization" + (f"?unit={oid}" if oid else ""))
