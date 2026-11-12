"""Native group hierarchy: legacy IDs, idempotent migration, role and staffing safety."""
import secrets

import pytest
from sqlalchemy import select

from app import organization as org, organization_groups as og, person_picker
from app.db import Group, GroupMember, Organization, SessionLocal, User
from app.org_models import OrgMembership, OrgRoleGrant, OrgState
from conftest import csrf_of, login

ADMIN = ("admin@example.org", "admin-passwort-123")


@pytest.fixture
def legacy_group(db):
    owner = db.scalar(select(User).where(User.email == ADMIN[0]))
    member = User(name="Gruppe Mitglied", email="group-member-" + secrets.token_hex(5) + "@example.org",
                  password_hash=owner.password_hash, active=True, permissions="video")
    group = Group(name="Bestandsgruppe " + secrets.token_hex(5),
                  description="Bestehende Mitgliedschaften")
    db.add_all([member, group])
    db.flush()
    db.add(GroupMember(user_id=member.id, group_id=group.id, manual=True))
    db.commit()
    ids = (group.id, member.id)
    yield ids
    with SessionLocal() as clean:
        row = clean.get(Group, ids[0])
        if row:
            node = clean.get(Organization, row.org_id) if row.org_id else None
            clean.delete(row)
            clean.flush()
            if node:
                clean.delete(node)
        person = clean.get(User, ids[1])
        if person:
            clean.delete(person)
        clean.commit()


def _post(client, db, action, **fields):
    row = db.get(OrgState, 1)
    db.refresh(row)
    return client.post("/admin/organization", data={
        "csrf": csrf_of(client.get("/").text), "version": row.version,
        "action": action, **fields
    }, follow_redirects=False)


def test_legacy_group_is_migrated_to_root_once_then_freely_movable(db, legacy_group):
    gid, uid = legacy_group
    before = db.get(Group, gid)
    assert before.org_id is None
    assert og.ensure_all(db) >= 1
    db.commit()
    node_id = before.org_id
    node = db.get(Organization, node_id)
    assert node.kind == "gruppe" and node.parent_id is None
    assert node.name == before.name
    assert node.note == before.description
    assert db.get(GroupMember, (gid, uid)) is not None
    assert og.ensure_all(db) == 0

    parent = Organization(name="Neue übergeordnete Einheit", kind="fachbereich")
    db.add(parent)
    db.commit()
    admin = login(*ADMIN)
    result = _post(admin, db, "unit_save", org_id=node_id,
                   name=before.name, kind="gruppe", parent_id=parent.id,
                   active="1", note=before.description)
    assert result.status_code == 303
    db.expire_all()
    node = db.get(Organization, node_id)
    assert node.parent_id == parent.id
    assert og.ensure_all(db) == 0
    assert db.get(Group, gid).org_id == node_id
    assert db.get(GroupMember, (gid, uid)) is not None
    db.delete(parent)
    node.parent_id = None
    db.commit()


def test_group_node_membership_is_not_hr_primary_or_staffing(db, legacy_group):
    gid, uid = legacy_group
    og.ensure_all(db)
    db.commit()
    node = db.get(Organization, db.get(Group, gid).org_id)
    person = db.get(User, uid)
    ctx = org.context(db, person)
    assert node.id in ctx["own"]
    assert org.allows(db, person, node.id, "view")
    assert db.scalar(select(OrgMembership.id).where(
        OrgMembership.user_id == uid, OrgMembership.org_id == node.id)) is None
    assert uid in org.scoped_people(db, db.scalar(select(User).where(
        User.email == ADMIN[0])), "view")
    directory = org.directory(db)
    assert any(x["id"] == node.id and not x["primary"] for x in directory[uid])
    people = person_picker.prepare_context({"users": [person]})
    assert node.id in people["people"][str(uid)]["orgs"]


def test_org_editor_updates_same_group_and_preserves_members(db, legacy_group):
    gid, uid = legacy_group
    og.ensure_all(db)
    db.commit()
    group = db.get(Group, gid)
    org_id = group.org_id
    admin = login(*ADMIN)
    new_name = "Umbenannt " + secrets.token_hex(5)
    response = _post(admin, db, "unit_save", org_id=org_id,
                     name=new_name, kind="gruppe", parent_id="", active="1",
                     note="Im Organisationsbaum geändert")
    assert response.status_code == 303
    db.expire_all()
    group = db.get(Group, gid)
    assert group.name == new_name and group.description == "Im Organisationsbaum geändert"
    assert group.org_id == org_id and db.get(GroupMember, (gid, uid)) is not None
    page = admin.get(f"/admin/organization?unit={org_id}")
    assert page.status_code == 200
    assert "Mitglieder der Gruppe" in page.text
    assert db.get(User, uid).name in page.text
    assert "Manuell" in page.text
    assert 'name="action" value="group_members_save"' in page.text


def test_creating_group_from_org_tree_creates_single_canonical_group(db):
    admin = login(*ADMIN)
    name = "Gruppe aus Baum " + secrets.token_hex(5)
    response = _post(admin, db, "unit_create", name=name, kind="gruppe",
                     parent_id="", active="1")
    assert response.status_code == 303
    group = db.scalar(select(Group).where(Group.name == name))
    assert group is not None and group.org_id is not None
    node = db.get(Organization, group.org_id)
    assert node.kind == "gruppe" and node.parent_id is None
    assert og.ensure_all(db) == 0
    db.delete(group)
    db.flush()
    db.delete(node)
    db.commit()


def test_group_member_editor_keeps_oidc_members_and_changes_manual_only(db, legacy_group):
    gid, uid = legacy_group
    og.ensure_all(db)
    admin = db.scalar(select(User).where(User.email == ADMIN[0]))
    db.add(GroupMember(group_id=gid, user_id=admin.id, manual=False))
    db.commit()
    c = login(*ADMIN)
    org_id = db.get(Group, gid).org_id
    # Empty manual selection must remove manual members, not OIDC members.
    result = _post(c, db, "group_members_save", org_id=org_id)
    assert result.status_code == 303
    db.expire_all()
    assert db.get(GroupMember, (gid, uid)) is None
    automatic = db.get(GroupMember, (gid, admin.id))
    assert automatic is not None and not automatic.manual
    # Can add a manual member to a group while leaving OIDC membership intact.
    result = _post(c, db, "group_members_save", org_id=org_id, members=str(uid))
    assert result.status_code == 303
    db.expire_all()
    assert db.get(GroupMember, (gid, uid)) is not None
    assert db.get(GroupMember, (gid, admin.id)) is not None


def test_group_node_must_remain_group_and_prevents_unsafe_move(db, legacy_group):
    gid, uid = legacy_group
    og.ensure_all(db)
    db.commit()
    node = db.get(Organization, db.get(Group, gid).org_id)
    admin = login(*ADMIN)
    bad = _post(admin, db, "unit_save", org_id=node.id,
                name=node.name, kind="team", active="1")
    assert bad.status_code == 422
    db.refresh(node)
    assert node.kind == "gruppe"
    first = Organization(name="Gruppenbaum A", kind="fachbereich")
    second = Organization(name="Gruppenbaum B", kind="fachbereich")
    db.add_all([first, second])
    db.commit()
    # Scoped authority cannot be expanded by a user with orgs alone.
    other = User(name="Nur Struktur", email="struct-" + secrets.token_hex(5) + "@example.org",
                 password_hash=db.scalar(select(User).where(User.email == ADMIN[0])).password_hash,
                 active=True, permissions="orgs")
    db.add(other)
    db.commit()
    user = login(other.email, "admin-passwort-123")
    denied = _post(user, db, "unit_save", org_id=node.id,
                   name=node.name, kind="gruppe", parent_id=first.id, active="1")
    assert denied.status_code == 403
    assert db.get(Organization, node.id).parent_id is None
    db.delete(first)
    db.delete(second)
    db.delete(other)
    db.commit()
