"""TAKT Wissen P1: live organization ACL, status, CSRF and module disablement."""
import pytest
from sqlalchemy import select

from app.db import Organization, SessionLocal, User
from app.knowledge_models import KnowledgeArticle, KnowledgeGrant, KnowledgeSpace
from app.org_models import OrgMembership
from app.security import hash_password
from conftest import csrf_of, login, settings


ADMIN = ("admin@example.org", "admin-passwort-123")


@pytest.fixture
def sample():
    settings(module_knowledge="1", module_ai="0")
    with SessionLocal() as db:
        org = Organization(name="Wissen Test-Fachgebiet", kind="team")
        db.add(org)
        db.flush()
        reader = User(email="wissen-reader@example.org", name="Wissensredaktion",
                      password_hash=hash_password("knowledge-test-123"),
                      permissions="knowledge_read,knowledge_edit,knowledge_publish",
                      must_change_password=False)
        outsider = User(email="wissen-outsider@example.org", name="Fremder Bereich",
                        password_hash=hash_password("knowledge-test-123"),
                        permissions="knowledge_read", must_change_password=False)
        checker = User(email="wissen-checker@example.org", name="Zweite Fachprüfung",
                       password_hash=hash_password("knowledge-test-123"),
                       permissions="knowledge_read,knowledge_publish",
                       must_change_password=False)
        for u in (reader, outsider, checker):
            existing = db.scalar(select(User).where(User.email == u.email))
            if existing:
                db.delete(existing)
                db.flush()
            db.add(u)
        db.flush()
        db.add(OrgMembership(user_id=reader.id, org_id=org.id, is_primary=True))
        db.add(OrgMembership(user_id=checker.id, org_id=org.id, is_primary=True))
        space = KnowledgeSpace(title="Wissensraum Sachgebiet", description="Intern",
                               org_id=org.id, owner_id=reader.id)
        db.add(space)
        db.flush()
        article = KnowledgeArticle(space_id=space.id, owner_id=reader.id,
                                   title="Beschaffung Dienstmaterial", body_md="Interne Abläufe",
                                   status="draft", version=1)
        db.add(article)
        db.commit()
        data = (org.id, space.id, article.id, reader.id, outsider.id, checker.id)
    try:
        yield data
    finally:
        settings(module_knowledge="0")
        with SessionLocal() as db:
            org_id, space_id, _, *_ = data
            for model in (KnowledgeGrant,):
                for row in db.scalars(select(model).where(
                    model.resource_kind == "space", model.resource_id == space_id)):
                    db.delete(row)
            space = db.get(KnowledgeSpace, space_id)
            if space:
                # SQLite has no ORM cascade from the space model.
                from app.knowledge_models import KnowledgeRevision, KnowledgeAudit
                ids = [r.id for r in db.scalars(select(KnowledgeArticle).where(
                    KnowledgeArticle.space_id == space_id))]
                for rid in ids:
                    for rev in db.scalars(select(KnowledgeRevision).where(
                        KnowledgeRevision.article_id == rid)):
                        db.delete(rev)
                    for g in db.scalars(select(KnowledgeGrant).where(
                        KnowledgeGrant.resource_kind == "article",
                        KnowledgeGrant.resource_id == rid)):
                        db.delete(g)
                    for a in db.scalars(select(KnowledgeAudit).where(
                        KnowledgeAudit.article_id == rid)):
                        a.article_id = None
                    db.delete(db.get(KnowledgeArticle, rid))
                for audit in db.scalars(select(KnowledgeAudit).where(
                    KnowledgeAudit.space_id == space_id)):
                    db.delete(audit)
                db.delete(space)
            for uid in data[3:]:
                for member in db.scalars(select(OrgMembership).where(OrgMembership.user_id == uid)):
                    db.delete(member)
                db.delete(db.get(User, uid))
            db.delete(db.get(Organization, org_id))
            db.commit()


def test_module_off_by_default_blocks_routes_even_for_admin():
    settings(module_knowledge="0")
    assert login(*ADMIN).get("/wissen").status_code == 404
    assert login(*ADMIN).get("/wissen/raum/1").status_code == 404


def test_access_requires_org_scope_and_published_status(sample):
    org_id, space_id, article_id, reader_id, outsider_id, checker_id = sample
    author = login("wissen-reader@example.org", "knowledge-test-123")
    outsider = login("wissen-outsider@example.org", "knowledge-test-123")
    assert author.get(f"/wissen/raum/{space_id}").status_code == 200
    assert author.get(f"/wissen/artikel/{article_id}").status_code == 200
    assert outsider.get(f"/wissen/raum/{space_id}").status_code == 403
    assert outsider.get(f"/wissen/artikel/{article_id}").status_code == 403
    assert "Beschaffung Dienstmaterial" not in outsider.get("/wissen?q=Beschaffung").text
    assert "Beschaffung Dienstmaterial" in author.get("/wissen?q=Beschaffung").text
    # Unpublished drafts are never exposed simply because of a read grant.
    with SessionLocal() as db:
        db.add(KnowledgeGrant(resource_kind="article", resource_id=article_id,
                              principal_kind="user", principal_id=outsider_id,
                              capability="read", effect="allow"))
        db.commit()
    assert outsider.get(f"/wissen/artikel/{article_id}").status_code == 403


def test_two_person_publication_and_optimistic_lock(sample):
    _, space_id, article_id, *_ = sample
    author = login("wissen-reader@example.org", "knowledge-test-123")
    reviewer = login("wissen-checker@example.org", "knowledge-test-123")
    csrf = csrf_of(author.get(f"/wissen/artikel/{article_id}").text)
    assert author.post(f"/wissen/artikel/{article_id}/save", data={
        "title": "Versuch", "kind": "article", "body_md": "abc",
        "version": 999, "csrf": csrf,
    }).status_code == 409
    response = author.post(f"/wissen/artikel/{article_id}/status", data={
        "status": "review", "version": 1, "csrf": csrf,
    })
    assert response.status_code == 303
    assert author.post(f"/wissen/artikel/{article_id}/status", data={
        "status": "published", "version": 2, "csrf": csrf,
    }).status_code == 403
    csrf_check = csrf_of(reviewer.get(f"/wissen/artikel/{article_id}").text)
    assert reviewer.post(f"/wissen/artikel/{article_id}/status", data={
        "status": "published", "version": 2, "csrf": csrf_check,
    }).status_code == 303
    with SessionLocal() as db:
        item = db.get(KnowledgeArticle, article_id)
        assert item.status == "published" and item.version == 3


def test_explicit_deny_overrides_organization_and_admin_can_recover(sample):
    _, space_id, article_id, reader_id, *_ = sample
    admin = login(*ADMIN)
    author = login("wissen-reader@example.org", "knowledge-test-123")
    token = csrf_of(admin.get(f"/wissen/raum/{space_id}").text)
    res = admin.post(f"/wissen/space/{space_id}/rechte", data={
        "csrf": token, "principal_kind": "user", "principal_id": reader_id,
        "capability": "read", "effect": "deny",
    })
    assert res.status_code == 303
    assert author.get(f"/wissen/raum/{space_id}").status_code == 403
    assert author.get(f"/wissen/artikel/{article_id}").status_code == 403
    assert admin.get(f"/wissen/artikel/{article_id}").status_code == 200
    assert admin.post(f"/wissen/space/{space_id}/rechte", data={
        "csrf": token, "principal_kind": "user", "principal_id": reader_id,
        "capability": "read", "effect": "remove",
    }).status_code == 303
    assert author.get(f"/wissen/raum/{space_id}").status_code == 200


def test_csrf_required_for_writes(sample):
    _, space_id, article_id, *_ = sample
    author = login("wissen-reader@example.org", "knowledge-test-123")
    assert author.post(f"/wissen/raum/{space_id}/artikel", data={
        "title": "Ohne Schutz", "kind": "article",
    }).status_code == 400
