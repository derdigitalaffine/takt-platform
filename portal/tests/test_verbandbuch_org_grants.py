"""Review scope for explicitly delegated organizational subtrees."""
from uuid import uuid4
from app.db import Organization, SessionLocal, User
from app.verbandbuch_models import FirstAidSite, FirstAidOrgGrant
from app import verbandbuch as aid


def test_subtree_review_permission_requires_global_right_and_active_path():
    with SessionLocal() as db:
        parent = Organization(name="Review parent " + uuid4().hex, active=True)
        child = Organization(name="Review child " + uuid4().hex, active=True)
        outsider = Organization(name="Outside subtree " + uuid4().hex, active=True)
        db.add_all([parent, child, outsider]); db.flush()
        child.parent_id = parent.id
        site = FirstAidSite(org_id=child.id, title="Child site")
        other_site = FirstAidSite(org_id=outsider.id, title="Other site")
        db.add_all([site, other_site]); db.flush()
        reviewer = User(name="Subtree reviewer", email=uuid4().hex+"@example.org",
                        password_hash="disabled-test-credentials", permissions="verbandbuch_review",
                        is_admin=False, active=True, must_change_password=False)
        db.add(reviewer); db.flush()
        grant = FirstAidOrgGrant(org_id=parent.id, user_id=reviewer.id, role="review",
                                 include_children=True, created_by_id=reviewer.id)
        db.add(grant); db.flush()
        assert site.id in {s.id for s in aid.sites_for(db, reviewer, "review")}
        assert other_site.id not in {s.id for s in aid.sites_for(db, reviewer, "review")}
        grant.include_children = False; db.flush()
        assert site.id not in {s.id for s in aid.sites_for(db, reviewer, "review")}
        grant.include_children = True
        parent.active = False; db.flush()
        assert site.id not in {s.id for s in aid.sites_for(db, reviewer, "review")}
        db.rollback()
