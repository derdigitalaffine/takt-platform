"""Isolated organization fixture, reusing the portal browser test account."""

from navigation_controls_app import app
from app.db import SessionLocal, Organization, User, Group, GroupMember
from app.org_models import OrgRoleGrant, OrgMembership
from app.security import hash_password

with SessionLocal() as db:
    root = Organization(name="Verwaltung", kind="verwaltung")
    db.add(root)
    db.flush()
    team = Organization(name="Finanzen", kind="fachbereich", parent_id=root.id)
    other = Organization(name="Bauen", kind="fachbereich", parent_id=root.id)
    manager = User(
        name="Lea Bereich",
        email="scope@example.org",
        password_hash=hash_password("browser-test-password"),
    )
    group = Group(name="Finanzplanung")
    db.add_all([team, other, manager, group])
    db.flush()
    db.add_all(
        [
            GroupMember(user_id=manager.id, group_id=group.id),
            OrgRoleGrant(org_id=team.id, group_id=group.id, role="settings"),
            OrgRoleGrant(org_id=team.id, user_id=manager.id, role="members"),
            OrgMembership(
                user_id=manager.id, org_id=team.id, is_primary=True, counts_staff=True
            ),
        ]
    )
    db.commit()
