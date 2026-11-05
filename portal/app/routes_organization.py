"""Organization tree, person assignments and explicit scoped roles."""

import re
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import Organization, User, Group, GroupMember
from .org_models import OrgMembership, OrgRoleGrant, OrgAudit, OrgKind, OrgState
from . import organization as os, orgs, people_choices
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
    if unit is None and person is None and group is None:
        import json
        try:
            remembered = json.loads(user.nav_json or "{}").get("last_org_unit")
        except (ValueError, AttributeError):
            remembered = None
        if remembered in visible:
            unit = remembered
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
    # One entry per person or group, with all effective roles collected in it.
    grouped_roles = {}
    for grant in role_rows:
        key = ("user", grant.user_id) if grant.user_id else ("group", grant.group_id)
        grouped_roles.setdefault(key, []).append(grant)
    role_groups = [
        dict(kind=kind, target_id=tid, grants=items)
        for (kind, tid), items in grouped_roles.items()
    ]
    # Group-derived leadership is displayed as a tag without creating a
    # duplicate person or a second, implicit direct role grant.
    members_by_group = {}
    for gid, uid in db.execute(select(GroupMember.group_id, GroupMember.user_id)):
        members_by_group.setdefault(gid, set()).add(uid)
    leadership_tags = {}
    for grant in role_rows:
        if grant.role not in ("lead", "deputy"):
            continue
        affected = ({grant.user_id} if grant.user_id is not None
                    else members_by_group.get(grant.group_id, set()))
        for uid in affected:
            leadership_tags.setdefault(uid, set()).add(grant.role)
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
    primary = {m.user_id: m.org_id for m in memberships if m.is_primary}
    primary_hints = {
        uid: (nodes[oid].name if oid in visible else "Hauptzuordnung vorhanden")
        for uid, oid in primary.items()
        if oid in nodes
    }
    member_remove = [
        dict(
            value=str(m.id),
            label=people[m.user_id].name,
            detail=("Hauptzuordnung" if m.is_primary else "Zusätzliche Zuordnung"),
            kind="person",
            disabled=m.is_primary
            and any(
                other.user_id == m.user_id and other.id != m.id for other in memberships
            ),
        )
        for m in shown
        if m.user_id in people
    ]
    role_remove = [
        dict(
            value=str(g.id),
            label=(
                people[g.user_id].name
                if g.user_id in people
                else (
                    groups[g.group_id].name
                    if g.group_id in groups
                    else "Ehemaliger Eintrag"
                )
            ),
            detail=os.ROLES.get(g.role, (g.role,))[0],
            kind="person" if g.user_id else "group",
            disabled=False,
        )
        for g in role_rows
        if g.org_id == unit
    ]
    return render(
        request,
        "organization.html",
        user,
        org_rows=rows,
        org_nodes=nodes,
        org_access=access,
        selected=selected,
        caps=caps,
        primary_hints=primary_hints,
        selected_member_ids={m.user_id for m in memberships if m.org_id == unit},
        member_choices=people_choices.users(people.values(), hints=primary_hints),
        role_choices=people_choices.users(people.values(), targets=True)
        + people_choices.groups(groups.values()),
        member_remove_choices=member_remove,
        role_remove_choices=role_remove,
        member_selection=(form or {}).get("user_ids", [str(person)] if person else []),
        role_selection=(form or {}).get(
            "targets", ["group:" + str(group)] if group else []
        ),
        org_logo_url=orgs.logo_url,
        org_usage=orgs.usage(db, selected) if selected and caps.get("settings") else {},
        memberships=shown,
        own_memberships=own,
        people=people,
        org_groups=groups,
        role_rows=role_rows,
        role_groups=role_groups,
        leadership_tags=leadership_tags,
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



@app.get("/ui/preferences")
def get_ui_preferences(
    user: User = Depends(current_user),
):
    import json
    try:
        prefs = json.loads(user.nav_json or "{}")
    except ValueError:
        prefs = {}
    prefs = prefs if isinstance(prefs, dict) else {}
    return {
        "density": prefs.get("ui_density", "comfortable"),
        "org_view": prefs.get("org_view", "explorer"),
        "last_org_unit": prefs.get("last_org_unit"),
    }


@app.post("/ui/preferences", dependencies=[Depends(check_csrf)])
async def set_ui_preferences(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    import json
    form = await request.form()
    try:
        state = json.loads(user.nav_json or "{}")
    except ValueError:
        state = {}
    state = state if isinstance(state, dict) else {}
    allowed = {"density": ("ui_density", {"comfortable", "compact"}),
               "org_view": ("org_view", {"explorer", "table"})}
    for name, (stored, choices) in allowed.items():
        if name in form:
            if form[name] not in choices:
                raise HTTPException(422, "Darstellung prüfen.")
            state[stored] = form[name]
    if "last_org_unit" in form:
        oid = os.number(form["last_org_unit"])
        if not os.allows(db, user, oid, "view"):
            raise HTTPException(403)
        state["last_org_unit"] = oid
    user.nav_json = json.dumps(state, ensure_ascii=False)
    db.commit()
    return {"saved": True}


@app.get("/admin/organization")
def organization_page(
    request: Request,
    unit: int | None = None,
    person: int | None = None,
    group: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return view(
        request,
        user,
        db,
        unit,
        person,
        group,
        form=(
            {"action": "unit_create"}
            if request.query_params.get("new") == "1"
            else None
        ),
    )



def _person_editor_entries(db, actor, person, focus=None):
    """One shared, rights-filtered editor in user and organization administration."""
    assigned = {
        row.org_id: row
        for row in db.scalars(
            select(OrgMembership).where(OrgMembership.user_id == person.id)
        )
    }
    direct = {}
    for grant in db.scalars(
        select(OrgRoleGrant).where(OrgRoleGrant.user_id == person.id)
    ):
        direct.setdefault(grant.org_id, {})[grant.role] = grant
    entries = []
    for node in db.scalars(select(Organization).order_by(Organization.name)):
        if not os.allows(db, actor, node.id, "view"):
            continue
        members = os.allows(db, actor, node.id, "members")
        roles = os.allows(db, actor, node.id, "roles")
        if not (members or roles or node.id in assigned or node.id in direct):
            continue
        entries.append(dict(
            node=node, membership=assigned.get(node.id),
            grants=direct.get(node.id, {}),
            can_members=members, can_roles=roles,
            focused=node.id == focus or (focus is None and node.id in assigned),
        ))
    return entries


@app.get("/admin/organization/person/{person_id:int}")
def organization_person_panel(
    request: Request,
    person_id: int,
    unit: int | None = None,
    origin: str = "organization",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not os.has_access(db, user):
        raise HTTPException(403)
    person = db.get(User, person_id)
    if not person:
        raise HTTPException(404)
    entries = _person_editor_entries(db, user, person, unit)
    if not entries:
        raise HTTPException(403)
    return render(
        request, "organization_person_panel.html", user,
        person=person, entries=entries, org_roles=os.ROLES,
        org_version=db.get(OrgState, 1).version,
        origin="users" if origin == "users" else "organization",
    )


@app.post("/admin/organization/person/{person_id:int}", dependencies=[Depends(check_csrf)])
async def organization_person_save(
    request: Request,
    person_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not os.has_access(db, user):
        raise HTTPException(403)
    person = db.get(User, person_id)
    if not person or not person.active:
        raise HTTPException(404, "Aktive Person auswählen.")
    form = await request.form()
    entries = _person_editor_entries(db, user, person)
    editable = [e for e in entries if e["can_members"] or e["can_roles"]]
    if not editable:
        raise HTTPException(403)
    # One optimistic version check and one transaction for all changed units.
    os.lock(db, form.get("version"))
    primary_raw = form.get("primary_unit")
    primary_unit = os.number(primary_raw) if primary_raw else None
    if primary_unit and not any(
        e["node"].id == primary_unit and e["can_members"]
        and form.get(f"member_{primary_unit}") == "1" for e in entries
    ):
        raise HTTPException(422, "Hauptzuordnung muss aktiv und bearbeitbar sein.")
    # Move the primary association first, then update other associations,
    # and only then process removals. Existing scopes outside this editor survive.
    member_entries = sorted(
        (e for e in editable if e["can_members"] and
         form.get(f'member_{e["node"].id}') == "1"),
        key=lambda e: 0 if e["node"].id == primary_unit else 1,
    )
    for entry in member_entries:
        oid = entry["node"].id
        member = entry["membership"]
        want_primary = oid == primary_unit if primary_unit else bool(
            member and member.is_primary
        )
        staff = form.get(f"staff_{oid}")
        capacity = str(form.get(f"capacity_{oid}", "100"))
        if staff not in ("yes", "no"):
            raise HTTPException(422, "Besetzungswirkung prüfen.")
        if (
            member and member.is_primary == want_primary
            and member.counts_staff == (staff == "yes")
            and str(member.capacity_percent) == capacity
        ):
            continue
        os.set_membership(db, user, dict(
            org_id=oid, user_id=person_id,
            is_primary="1" if want_primary else "0",
            staff_mode=staff, capacity_percent=capacity,
        ))
    for entry in editable:
        oid = entry["node"].id
        if entry["can_roles"]:
            selected = form.getlist(f"role_{oid}")
            if len(selected) != len(set(selected)) or any(
                role not in os.ROLES for role in selected
            ):
                raise HTTPException(422, "Bereichsrollen prüfen.")
            current = entry["grants"]
            for role in selected:
                children = form.get(f"child_{oid}_{role}") == "1"
                grant = current.get(role)
                if not grant or grant.include_children != children:
                    os.set_role(db, user, dict(
                        org_id=oid, target=f"user:{person_id}", role=role,
                        include_children="1" if children else "0",
                    ))
            for role, grant in current.items():
                if role not in selected:
                    os.delete_role(db, user, dict(grant=grant.id))
    for entry in editable:
        if not entry["can_members"]:
            continue
        old = entry["membership"]
        if old and form.get(f'member_{entry["node"].id}') != "1":
            os.delete_membership(db, user, dict(membership=old.id))
    db.commit()
    flash(request, "Organisationszuordnungen und Bereichsrollen gemeinsam gespeichert.")
    if form.get("origin") == "users":
        return redirect("/admin/users")
    return redirect("/admin/organization?person=" + str(person_id))


@app.post("/admin/organization", dependencies=[Depends(check_csrf)])
async def organization_action(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return await handle_action(request, user, db, await request.form())


async def handle_action(request, user, db, data):
    new_logo = None
    old_logo = None
    count = None
    action = str(data.get("action", ""))
    oid = os.number(data["org_id"]) if data.get("org_id") else None
    try:
        if not os.has_access(db, user):
            raise HTTPException(403)
        os.lock(db, data.get("version"))
        if action in {
            "membership_many",
            "role_many",
            "membership_remove_many",
            "role_remove_many",
        }:
            field = {
                "membership_many": "user_ids",
                "role_many": "targets",
                "membership_remove_many": "memberships",
                "role_remove_many": "grants",
            }[action]
            selected = list(dict.fromkeys(str(v) for v in data.getlist(field)))
            if not 1 <= len(selected) <= 500:
                raise HTTPException(
                    422, "Zwischen einer und 500 Personen bzw. Einträgen auswählen."
                )
            os.require(
                db, user, oid, "roles" if action.startswith("role") else "members"
            )
            for value in selected:
                values = dict(data)
                if action == "membership_many":
                    values["user_id"] = value
                    os.set_membership(db, user, values)
                elif action == "role_many":
                    roles = list(dict.fromkeys(str(v) for v in data.getlist("roles")))
                    if not roles:
                        roles = [str(data.get("role", ""))]
                    if not 1 <= len(roles) <= len(os.ROLES) or any(
                        role not in os.ROLES for role in roles
                    ):
                        raise HTTPException(422, "Mindestens eine gültige Bereichsrolle wählen.")
                    for role in roles:
                        values["target"] = value
                        values["role"] = role
                        # Every role retains its own subtree scope.
                        if data.getlist("roles"):
                            values["include_children"] = (
                                "1" if data.get(f"children_{role}") == "1" else "0"
                            )
                        os.set_role(db, user, values)
                else:
                    model = (
                        OrgMembership
                        if action == "membership_remove_many"
                        else OrgRoleGrant
                    )
                    item = db.get(model, os.number(value))
                    if not item or item.org_id != oid:
                        raise HTTPException(
                            422,
                            "Die Auswahl gehört nicht vollständig zu dieser Einheit.",
                        )
                    values["membership" if model is OrgMembership else "grant"] = value
                    (
                        os.delete_membership
                        if model is OrgMembership
                        else os.delete_role
                    )(db, user, values)
            count = len(selected)
        elif action == "membership":
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
                keys = (
                    "name",
                    "short_name",
                    "contact",
                    "phone",
                    "email",
                    "website",
                    "street",
                    "zip",
                    "city",
                    "color",
                    "ags",
                    "note",
                )
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
            if user.can("orgs") and "position" in data:
                row.position = os.number(data.get("position"))
                if not -1000000 <= row.position <= 1000000:
                    raise HTTPException(422, "Reihenfolge prüfen.")
            upload = data.get("logo")
            if getattr(upload, "filename", ""):
                new_logo, error = orgs.prepare_logo(
                    await upload.read(orgs.MAX_LOGO + 1)
                )
                if error:
                    raise HTTPException(422, error)
                old_logo = row.logo
                row.logo = new_logo
            elif data.get("logo_remove") == "1":
                old_logo = row.logo
                row.logo = ""
            if existing is None:
                db.add(row)
            db.flush()
            oid = row.id
            os.audit(db, user, oid, "unit_save", name=row.name, parent=row.parent_id)
        elif action == "unit_delete":
            if not user.can("orgs"):
                raise HTTPException(403)
            row = db.get(Organization, oid)
            if not row:
                raise HTTPException(404)
            used = {k: v for k, v in orgs.usage(db, row).items() if v}
            if used:
                raise HTTPException(
                    422,
                    "Die Einheit wird noch verwendet: "
                    + ", ".join(f"{k}: {v}" for k, v in used.items())
                    + ". Alternativ auf inaktiv setzen.",
                )
            old_logo = row.logo
            os.audit(db, user, oid, "unit_delete", name=row.name)
            db.delete(row)
            oid = None
        elif action in {"kind", "kind_remove"}:
            if not user.can("orgs"):
                raise HTTPException(403)
            key = str(data.get("key", "")).strip()
            if action == "kind":
                from .orgs import KINDS

                label = " ".join(str(data.get("label", "")).split())
                if not key and label:
                    import unicodedata

                    key = re.sub(
                        "[^a-z0-9]+",
                        "_",
                        unicodedata.normalize("NFKD", label)
                        .encode("ascii", "ignore")
                        .decode()
                        .lower(),
                    ).strip("_")[:20]
                    if not key or not key[0].isalpha():
                        key = "ebene_" + key[:14]
                    if key in os.kinds(db):
                        raise HTTPException(
                            422,
                            "Dieser Ebenentyp ist bereits vorhanden. Bestehenden Typ verwenden oder umbenennen.",
                        )
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
        orgs.discard_logo(new_logo)
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
            form={
                **dict(data),
                **{
                    key: data.getlist(key)
                    for key in ("user_ids", "targets", "memberships", "grants")
                },
            },
        )
        page.status_code = exc.status_code
        return page
    except Exception:
        db.rollback()
        orgs.discard_logo(new_logo)
        raise
    orgs.discard_logo(old_logo)
    flash(
        request,
        (
            f"Organisation gespeichert · {count} ausgewählte Einträge verarbeitet."
            if count
            else "Organisation gespeichert."
        ),
    )
    return redirect("/admin/organization" + (f"?unit={oid}" if oid else ""))
