"""Real routes and scoped privileges, including legacy user/group mutation paths."""

import pytest
from sqlalchemy import select, delete
from app import organization as os, orgs, absence
from app.db import Organization, User, Group, GroupMember
from app.org_models import OrgState, OrgMembership, OrgRoleGrant, OrgAudit, OrgKind
from conftest import login, csrf_of
from test_native_tasks import task_people

ADMIN = ("admin@example.org", "admin-passwort-123")


def client(person):
    return login(person.email, "task-passwort-123")


def post(c, db, action, **data):
    version = db.get(OrgState, 1)
    db.refresh(version)
    return c.post(
        "/admin/organization",
        data={
            "csrf": csrf_of(c.get("/").text),
            "version": version.version,
            "action": action,
            **data,
        },
        follow_redirects=False,
    )


@pytest.fixture
def units(db, task_people):
    root = Organization(name="Organisationstest VG", kind="vg")
    db.add(root)
    db.flush()
    a = Organization(name="Bereich A", kind="fachbereich", parent_id=root.id)
    b = Organization(name="Bereich B", kind="fachbereich", parent_id=root.id)
    db.add_all([a, b])
    db.flush()
    team = Organization(name="Team A", kind="team", parent_id=a.id)
    db.add(team)
    db.commit()
    yield root, a, team, b
    ids = [n.id for n in (root, a, team, b)]
    db.execute(delete(OrgAudit).where(OrgAudit.org_id.in_(ids)))
    db.execute(delete(OrgRoleGrant).where(OrgRoleGrant.org_id.in_(ids)))
    db.execute(delete(OrgMembership).where(OrgMembership.org_id.in_(ids)))
    db.execute(delete(Organization).where(Organization.id.in_(ids)))
    db.commit()


def grant(db, node, user, role, children=True):
    row = OrgRoleGrant(
        org_id=node.id, user_id=user.id, role=role, include_children=children
    )
    db.add(row)
    db.commit()
    return row


def test_primary_additional_counts_and_cross_scope_changes(db, task_people, units):
    _, a, team, b = units
    person, manager = task_people[:2]
    admin = login(*ADMIN)
    assert (
        post(admin, db, "membership", org_id=b.id, user_id=person.id).status_code == 303
    )
    primary = db.scalar(select(OrgMembership).where(OrgMembership.user_id == person.id))
    assert primary.is_primary and primary.counts_staff
    grant(db, a, manager, "members")
    c = client(manager)
    assert (
        post(
            c,
            db,
            "membership",
            org_id=team.id,
            user_id=person.id,
            capacity_percent="40",
        ).status_code
        == 303
    )
    extra = db.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == person.id, OrgMembership.org_id == team.id
        )
    )
    assert (
        not extra.is_primary and not extra.counts_staff and extra.capacity_percent == 40
    )
    assert (
        post(
            c, db, "membership", org_id=team.id, user_id=person.id, is_primary="1"
        ).status_code
        == 403
    )
    db.refresh(primary)
    assert primary.is_primary
    assert (
        post(
            c,
            db,
            "membership",
            org_id=team.id,
            user_id=person.id,
            staff_mode="yes",
            capacity_percent="101",
        ).status_code
        == 422
    )
    assert (
        post(
            admin,
            db,
            "membership",
            org_id=team.id,
            user_id=person.id,
            is_primary="1",
            staff_mode="yes",
            capacity_percent="60",
        ).status_code
        == 303
    )
    db.refresh(primary)
    db.refresh(extra)
    assert not primary.is_primary and extra.is_primary and extra.capacity_percent == 60
    assert (
        post(
            admin, db, "membership_remove", org_id=team.id, membership=extra.id
        ).status_code
        == 422
    )


def test_group_scope_revocation_and_no_global_permissions(db, task_people, units):
    _, a, team, b = units
    person = task_people[2]
    group = Group(name="Organization role group")
    db.add(group)
    db.flush()
    gm = GroupMember(user_id=person.id, group_id=group.id)
    db.add(gm)
    g = OrgRoleGrant(
        org_id=a.id, group_id=group.id, role="planner", include_children=True
    )
    db.add(g)
    db.commit()
    try:
        assert os.allows(db, person, team.id, "plan") and not os.allows(
            db, person, b.id, "view"
        )
        assert not person.can("orgs") and not person.can("users")
        c = client(person)
        page = c.get(f"/admin/organization?unit={team.id}")
        assert page.status_code == 200 and "Organisation" in page.text
        assert c.get(f"/admin/organization?unit={b.id}").status_code == 403
        assert (
            post(
                c,
                db,
                "role",
                org_id=team.id,
                target=f"user:{person.id}",
                role="members",
            ).status_code
            == 403
        )
        assert (
            post(c, db, "unit_create", name="Unzulässig", kind="team").status_code
            == 403
        )
        db.delete(gm)
        db.commit()
        assert not os.allows(db, person, team.id, "plan")
        assert c.get("/admin/organization").status_code == 403
    finally:
        db.delete(group)
        db.commit()


def test_settings_preserve_legacy_fields_and_cannot_move_subtree(
    db, task_people, units
):
    _, a, team, b = units
    actor = task_people[2]
    team.street = "Geschützte Adresse"
    team.phone = "123"
    db.commit()
    grant(db, team, actor, "settings", False)
    c = client(actor)
    assert (
        post(
            c,
            db,
            "unit_save",
            org_id=team.id,
            parent_id=a.id,
            kind="team",
            active="1",
            name="Umbenannt",
            email="team@example.org",
        ).status_code
        == 303
    )
    db.refresh(team)
    assert (
        team.street == "Geschützte Adresse"
        and team.phone == "123"
        and team.name == "Umbenannt"
    )
    assert (
        post(
            c,
            db,
            "unit_save",
            org_id=team.id,
            parent_id=b.id,
            kind="team",
            active="1",
            name="Verschoben",
        ).status_code
        == 403
    )
    db.refresh(team)
    assert team.parent_id == a.id


def test_admin_user_and_group_routes_cannot_escalate_scoped_roles(
    db, task_people, units
):
    _, a, _, _ = units
    actor, target = task_people[2:]
    actor.permissions = "users"
    db.commit()
    grant(db, a, target, "lead")
    group = Group(name="Protected organization group")
    db.add(group)
    db.flush()
    db.add(OrgRoleGrant(org_id=a.id, group_id=group.id, role="members"))
    db.commit()
    try:
        c = client(actor)
        csrf = csrf_of(c.get("/").text)
        assert (
            c.post(
                f"/admin/groups/{group.id}",
                data={
                    "csrf": csrf,
                    "action": "save",
                    "name": group.name,
                    "members": [actor.id],
                },
            ).status_code
            == 403
        )
        assert not db.get(GroupMember, (group.id, actor.id))
        response = c.post(
            f"/admin/users/{actor.id}",
            data={
                "csrf": csrf,
                "action": "edit",
                "name": actor.name,
                "perm": ["users"],
                "groups": [group.id],
            },
            follow_redirects=False,
        )
        assert response.status_code == 403
        old = target.password_hash
        response = c.post(
            f"/admin/users/{target.id}",
            data={"csrf": csrf, "action": "reset_password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(target)
        assert target.password_hash == old
        assert c.get("/admin/users").status_code == 200
    finally:
        db.delete(group)
        db.commit()


def test_stale_state_inactive_ancestors_and_invalid_edits(db, task_people, units):
    root, a, team, _ = units
    actor = task_people[2]
    grant(db, a, actor, "settings")
    c = client(actor)
    admin = login(*ADMIN)
    version = db.get(OrgState, 1).version
    csrf = csrf_of(c.get("/").text)
    assert (
        post(
            admin, db, "membership", org_id=team.id, user_id=task_people[0].id
        ).status_code
        == 303
    )
    response = c.post(
        "/admin/organization",
        data={
            "csrf": csrf,
            "version": version,
            "action": "unit_save",
            "org_id": team.id,
            "parent_id": a.id,
            "kind": "team",
            "active": "1",
            "name": "Mein Entwurf",
        },
    )
    assert response.status_code == 409 and "Mein Entwurf" in response.text
    root.active = False
    db.commit()
    assert not os.allows(db, actor, team.id, "settings")
    assert (
        post(
            admin, db, "membership", org_id=team.id, user_id=task_people[1].id
        ).status_code
        == 422
    )
    root.active = True
    db.commit()


def test_hierarchy_cycle_checks_beyond_old_depth_limit(db, units):
    root, _, _, _ = units
    parent = root
    extra = []
    try:
        for i in range(25):
            n = Organization(name=f"Depth {i}", kind="team", parent_id=parent.id)
            db.add(n)
            db.flush()
            extra.append(n)
            parent = n
        db.commit()
        assert orgs.would_cycle(root, parent)
        assert len(orgs.path(parent)) == 26 and orgs.body_of(parent).id == root.id
        assert next(depth for n, depth in orgs.tree(db) if n.id == parent.id) == 25
        c = login(*ADMIN)
        assert (
            post(
                c,
                db,
                "unit_save",
                org_id=root.id,
                name=root.name,
                kind="vg",
                parent_id=parent.id,
                active="1",
            ).status_code
            == 422
        )
    finally:
        for n in reversed(extra):
            db.delete(n)
        db.commit()


def test_explicit_absence_role_uses_primary_memberships_only(db, task_people, units):
    _, a, team, b = units
    actor = task_people[2]
    person = task_people[0]
    admin = login(*ADMIN)
    assert (
        post(admin, db, "membership", org_id=b.id, user_id=person.id).status_code == 303
    )
    assert (
        post(admin, db, "membership", org_id=team.id, user_id=person.id).status_code
        == 303
    )
    grant(db, a, actor, "absences")
    assert not absence.may_manage(db, actor, person.id)
    assert (
        post(
            admin, db, "membership", org_id=team.id, user_id=person.id, is_primary="1"
        ).status_code
        == 303
    )
    assert absence.may_manage(db, actor, person.id)
    assert not actor.can("absences")


def test_csv_cannot_add_members_to_role_groups(db, task_people, units):
    from app import user_import

    _, a, _, _ = units
    actor = task_people[2]
    actor.permissions = "users"
    db.commit()
    group = Group(name="CSV protected organization")
    db.add(group)
    db.flush()
    db.add(OrgRoleGrant(org_id=a.id, group_id=group.id, role="lead"))
    db.commit()
    try:
        rows, errors = user_import.parse(
            f"email,name,groups\n{actor.email},CSV,{group.name}\n".encode(), db, actor
        )
        assert rows and not errors
        token = user_import.stash(rows)
        c = client(actor)
        response = c.post(
            "/admin/users/import/apply",
            data={"csrf": csrf_of(c.get("/").text), "token": token},
        )
        assert response.status_code == 403
        assert not db.get(GroupMember, (group.id, actor.id))
    finally:
        db.delete(group)
        db.commit()


def test_legacy_editor_serializes_and_cannot_expand_inherited_roles(
    db, task_people, units
):
    root, a, team, b = units
    actor = task_people[2]
    actor.permissions = "orgs,org_members"
    db.commit()
    grant(db, a, task_people[1], "lead")
    c = client(actor)
    admin = login(*ADMIN)
    v = db.get(OrgState, 1)
    db.refresh(v)
    old = v.version
    page = c.get(f"/admin/orgs/{b.id}", follow_redirects=True)
    response = c.post(
        f"/admin/orgs/{b.id}",
        data={
            "csrf": csrf_of(page.text),
            "version": old,
            "kind": b.kind,
            "name": b.name,
            "parent_id": a.id,
            "active": "1",
        },
    )
    assert response.status_code == 403
    assert (
        post(
            admin,
            db,
            "unit_save",
            org_id=team.id,
            name=team.name,
            kind=team.kind,
            parent_id=a.id,
            active="1",
        ).status_code
        == 303
    )
    response = c.post(
        f"/admin/orgs/{b.id}",
        data={
            "csrf": csrf_of(page.text),
            "version": old,
            "kind": b.kind,
            "name": "Veraltet",
            "parent_id": root.id,
            "active": "1",
        },
    )
    assert response.status_code == 409
    db.refresh(b)
    assert b.name == "Bereich B" and b.parent_id == root.id


def test_custom_types_and_plain_member_cannot_manage(db, task_people, units):
    _, a, team, _ = units
    admin = login(*ADMIN)
    person = task_people[0]
    try:
        assert (
            post(admin, db, "kind", key="projekt", label="Projektbereich").status_code
            == 303
        )
        assert (
            post(
                admin,
                db,
                "unit_save",
                org_id=team.id,
                name=team.name,
                kind="projekt",
                parent_id=a.id,
                active="1",
            ).status_code
            == 303
        )
        assert post(admin, db, "kind_remove", key="projekt").status_code == 422
        assert (
            post(admin, db, "membership", org_id=team.id, user_id=person.id).status_code
            == 303
        )
        c = client(person)
        page = c.get(f"/admin/organization?unit={team.id}")
        assert page.status_code == 200 and "Projektbereich" in page.text
        assert 'name="capacity_percent"' not in page.text
        assert (
            post(c, db, "membership", org_id=team.id, user_id=person.id).status_code
            == 403
        )
        assert (
            post(
                c,
                db,
                "unit_save",
                org_id=team.id,
                name="Fremd",
                kind="projekt",
                parent_id=a.id,
                active="1",
            ).status_code
            == 403
        )
        assert (
            c.post(
                "/admin/organization",
                data={"action": "kind", "key": "bad", "label": "Bad"},
            ).status_code
            == 400
        )
    finally:
        db.refresh(team)
        team.kind = "team"
        db.commit()
        kind = db.get(OrgKind, "projekt")
        if kind:
            db.delete(kind)
            db.commit()


def test_bulk_memberships_are_atomic_and_scoped(db, task_people, units):
    _, a, team, b = units
    person, manager, other = task_people[:3]
    grant(db, a, manager, "members")
    c = client(manager)
    # A bad entry must roll back the preceding valid entry too.
    response = post(
        c, db, "membership_many", org_id=team.id, user_ids=[str(person.id), "999999999"]
    )
    assert response.status_code == 422
    assert not db.scalar(
        select(OrgMembership.id).where(OrgMembership.org_id == team.id)
    )
    response = post(
        c,
        db,
        "membership_many",
        org_id=team.id,
        user_ids=[str(person.id), str(other.id), str(person.id)],
    )
    assert response.status_code == 303
    rows = list(
        db.scalars(select(OrgMembership).where(OrgMembership.org_id == team.id))
    )
    assert {r.user_id for r in rows} == {person.id, other.id}
    # Reapplying a batch preserves existing primary memberships without a forced move.
    assert (
        post(
            c,
            db,
            "membership_many",
            org_id=team.id,
            user_ids=[str(person.id), str(other.id)],
        ).status_code
        == 303
    )
    assert (
        post(
            c, db, "membership_many", org_id=b.id, user_ids=[str(person.id)]
        ).status_code
        == 403
    )
    foreign = OrgMembership(org_id=b.id, user_id=manager.id, is_primary=True)
    db.add(foreign)
    db.commit()
    assert (
        post(
            c,
            db,
            "membership_remove_many",
            org_id=team.id,
            memberships=[str(rows[0].id), str(foreign.id)],
        ).status_code
        == 422
    )
    assert db.get(OrgMembership, rows[0].id)
    assert (
        post(
            c,
            db,
            "role_many",
            org_id=team.id,
            targets=[f"user:{person.id}"],
            role="planner",
        ).status_code
        == 403
    )


def test_bulk_roles_and_unified_legacy_entry(db, task_people, units):
    _, a, team, _ = units
    admin = login(*ADMIN)
    person, other = task_people[:2]
    response = admin.get(f"/admin/orgs/{team.id}", follow_redirects=False)
    assert response.status_code == 303
    assert (
        response.headers["location"]
        == f"/admin/organization?unit={team.id}#org-settings"
    )
    response = post(
        admin,
        db,
        "role_many",
        org_id=a.id,
        targets=[f"user:{person.id}", f"user:{other.id}"],
        role="planner",
        include_children="1",
    )
    assert response.status_code == 303
    assert all(os.allows(db, u, team.id, "plan") for u in (person, other))
    rows = list(db.scalars(select(OrgRoleGrant).where(OrgRoleGrant.org_id == a.id)))
    assert (
        post(
            admin, db, "role_remove_many", org_id=a.id, grants=[str(r.id) for r in rows]
        ).status_code
        == 303
    )
    assert not os.allows(db, person, team.id, "plan")


def test_unified_logo_update_keeps_old_file_on_failure(
    db, task_people, units, monkeypatch
):
    from test_orgs import PNG

    _, a, _, _ = units
    old, error = orgs.prepare_logo(PNG)
    assert not error
    a.logo = old
    db.commit()
    c = login(*ADMIN)
    before = set(orgs.logo_dir().iterdir())

    def broken_audit(*args, **kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(os, "audit", broken_audit)
    version = db.get(OrgState, 1)
    db.refresh(version)
    try:
        with pytest.raises(RuntimeError, match="simulated write failure"):
            c.post(
                "/admin/organization",
                data=dict(
                    csrf=csrf_of(c.get("/").text),
                    version=version.version,
                    action="unit_save",
                    org_id=a.id,
                    name=a.name,
                    kind=a.kind,
                    parent_id=a.parent_id,
                    active="1",
                ),
                files={"logo": ("new.png", PNG, "image/png")},
            )
        db.refresh(a)
        assert a.logo == old and (orgs.logo_dir() / old).is_file()
        assert set(orgs.logo_dir().iterdir()) == before
    finally:
        a.logo = ""
        db.commit()
        orgs.discard_logo(old)
