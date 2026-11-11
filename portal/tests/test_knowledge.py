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



def _publish_sample(sample):
    """Use a real two-person approval; fixture itself starts unpublished."""
    _, _, article_id, *_ = sample
    author = login("wissen-reader@example.org", "knowledge-test-123")
    reviewer = login("wissen-checker@example.org", "knowledge-test-123")
    assert author.post(f"/wissen/artikel/{article_id}/status", data={
        "csrf": csrf_of(author.get(f"/wissen/artikel/{article_id}").text),
        "status": "review", "version": 1,
    }).status_code == 303
    assert reviewer.post(f"/wissen/artikel/{article_id}/status", data={
        "csrf": csrf_of(reviewer.get(f"/wissen/artikel/{article_id}").text),
        "status": "published", "version": 2,
    }).status_code == 303
    return author, reviewer


def test_published_amendment_stays_private_until_second_approval(sample):
    _, space_id, article_id, _, outsider_id, _ = sample
    author, reviewer = _publish_sample(sample)
    outsider = login("wissen-outsider@example.org", "knowledge-test-123")
    # Explicit read-only article share: outsider can see released content, never drafts.
    with SessionLocal() as db:
        db.add(KnowledgeGrant(resource_kind="article", resource_id=article_id,
                              principal_kind="user", principal_id=outsider_id,
                              capability="read", effect="allow"))
        db.commit()
    assert outsider.get(f"/wissen/artikel/{article_id}").status_code == 200
    author_csrf = csrf_of(author.get(f"/wissen/artikel/{article_id}").text)
    assert author.post(f"/wissen/artikel/{article_id}/entwurf/start", data={
        "csrf": author_csrf, "version": 3,
    }).status_code == 303
    assert outsider.get(f"/wissen/artikel/{article_id}/entwurf").status_code == 403
    text = outsider.get(f"/wissen/artikel/{article_id}").text
    assert "Interne Abläufe" in text
    assert "Änderungsentwurf prüfen" not in text
    amendment = author.get(f"/wissen/artikel/{article_id}/entwurf")
    assert amendment.status_code == 200
    assert "data-knowledge-editor" in amendment.text
    assert "Veröffentlichte Fassung" in amendment.text
    assert author.post(f"/wissen/artikel/{article_id}/entwurf/save", data={
        "csrf": author_csrf, "title": "Beschaffung und Ausgabe",
        "kind": "process", "body_md": "## Neuer Ablauf\n\n<script>alert(1)</script>",
        "version": 1,
    }).status_code == 303
    assert author.post(f"/wissen/artikel/{article_id}/entwurf/save", data={
        "csrf": author_csrf, "title": "Veraltet",
        "kind": "process", "body_md": "Kein Datenverlust", "version": 1,
    }).status_code == 409
    assert "Neuer Ablauf" not in outsider.get(f"/wissen/artikel/{article_id}").text
    assert outsider.post("/wissen/vorschau", data={
        "csrf": csrf_of(outsider.get(f"/wissen/artikel/{article_id}").text),
        "article_id": article_id, "body_md": "unberechtigt",
    }).status_code == 403
    preview = author.post("/wissen/vorschau", data={
        "csrf": author_csrf, "article_id": article_id,
        "body_md": "## Titel\n\n<script>alert(1)</script>\n\n[unsicher](javascript:alert(1))",
    })
    assert preview.status_code == 200
    assert "<h2>" in preview.json()["html"]
    assert "<script>" not in preview.json()["html"]
    assert 'href="javascript:' not in preview.json()["html"]

    assert author.post(f"/wissen/artikel/{article_id}/entwurf/status", data={
        "csrf": author_csrf, "status": "review", "version": 2,
    }).status_code == 303
    assert author.post(f"/wissen/artikel/{article_id}/entwurf/status", data={
        "csrf": author_csrf, "status": "published", "version": 3,
    }).status_code == 403
    reviewer_csrf = csrf_of(reviewer.get(f"/wissen/artikel/{article_id}/entwurf").text)
    assert reviewer.post(f"/wissen/artikel/{article_id}/entwurf/status", data={
        "csrf": reviewer_csrf, "status": "published", "version": 3,
    }).status_code == 303
    from app.knowledge_models import KnowledgeAmendment, KnowledgeRevision
    with SessionLocal() as db:
        item = db.get(KnowledgeArticle, article_id)
        assert item.version == 4 and item.title == "Beschaffung und Ausgabe"
        assert item.kind == "process" and "Neuer Ablauf" in item.body_md
        assert item.authority == "verified" and item.last_reviewed_at is not None
        assert item.review_due_on is not None
        assert len(list(db.scalars(select(KnowledgeRevision).where(
            KnowledgeRevision.article_id == article_id)))) >= 3
        proposal = db.scalar(select(KnowledgeAmendment).where(
            KnowledgeAmendment.article_id == article_id))
        assert proposal.status == "applied"
    assert "Neuer Ablauf" in outsider.get(f"/wissen/artikel/{article_id}").text
    assert "<script>" not in outsider.get(f"/wissen/artikel/{article_id}").text
    assert author.get(f"/wissen/artikel/{article_id}/entwurf").status_code == 404


def test_amendment_revocation_and_disabled_module_fail_closed(sample):
    _, space_id, article_id, reader_id, *_ = sample
    author, reviewer = _publish_sample(sample)
    admin = login(*ADMIN)
    token = csrf_of(author.get(f"/wissen/artikel/{article_id}").text)
    assert author.post(f"/wissen/artikel/{article_id}/entwurf/start",
                       data={"csrf": token, "version": 3}).status_code == 303
    assert author.get(f"/wissen/artikel/{article_id}/entwurf").status_code == 200
    admin_csrf = csrf_of(admin.get(f"/wissen/raum/{space_id}").text)
    assert admin.post(f"/wissen/space/{space_id}/rechte", data={
        "csrf": admin_csrf, "principal_kind": "user", "principal_id": reader_id,
        "capability": "read", "effect": "deny",
    }).status_code == 303
    assert author.get(f"/wissen/artikel/{article_id}/entwurf").status_code == 403
    assert author.post(f"/wissen/artikel/{article_id}/entwurf/save", data={
        "csrf": token, "title": "Versuch", "kind": "article",
        "body_md": "Versuch", "version": 1,
    }).status_code == 403
    settings(module_knowledge="0")
    assert admin.get(f"/wissen/artikel/{article_id}/entwurf").status_code == 404
    assert admin.post("/wissen/vorschau", data={
        "csrf": admin_csrf, "article_id": article_id, "body_md": "Aus",
    }).status_code == 404


def test_review_due_date_authority_and_version_conflict(sample):
    _, _, article_id, *_ = sample
    author, reviewer = _publish_sample(sample)
    reviewer_csrf = csrf_of(reviewer.get(f"/wissen/artikel/{article_id}").text)
    url = f"/wissen/artikel/{article_id}/pruefung"
    assert reviewer.post(url, data={
        "csrf": reviewer_csrf, "authority": "binding",
        "review_due_on": "2030-10-01", "version": 3,
    }).status_code == 422
    assert reviewer.post(url, data={
        "csrf": reviewer_csrf, "authority": "verified",
        "review_due_on": "not-a-date", "version": 3,
    }).status_code == 422
    assert author.post(url, data={
        "csrf": csrf_of(author.get(f"/wissen/artikel/{article_id}").text),
        "authority": "verified", "review_due_on": "2030-10-01", "version": 3,
    }).status_code == 403
    assert reviewer.post(url, data={
        "csrf": reviewer_csrf, "authority": "experience",
        "review_due_on": "2030-10-01", "version": 3,
    }).status_code == 303
    assert reviewer.post(url, data={
        "csrf": reviewer_csrf, "authority": "experience",
        "review_due_on": "2031-10-01", "version": 3,
    }).status_code == 409
    with SessionLocal() as db:
        item = db.get(KnowledgeArticle, article_id)
        assert item.authority == "experience"
        assert item.review_due_on.isoformat() == "2030-10-01"
        assert item.version == 4



def test_delegated_management_is_scoped_to_exact_org_and_read_edit_only(sample):
    """A room-level manager cannot expand own scope into admin/AI or other units."""
    org_id, space_id, article_id, author_id, outsider_id, reviewer_id = sample
    reviewer = login("wissen-checker@example.org", "knowledge-test-123")
    admin = login(*ADMIN)
    path = f"/wissen/raum/{space_id}/verwaltung"
    assert reviewer.get(path).status_code == 403
    with SessionLocal() as db:
        delegate = db.get(User, reviewer_id)
        delegate.permissions += ",knowledge_manage"
        db.add(KnowledgeGrant(resource_kind="space", resource_id=space_id,
                              principal_kind="user", principal_id=reviewer_id,
                              capability="manage", effect="allow"))
        db.commit()

    page = reviewer.get(path)
    assert page.status_code == 200
    assert "Wissensredaktion" in page.text
    assert "Fremder Bereich" not in page.text
    assert "Wissensraum Sachgebiet" in page.text
    assert reviewer.get(path + f"?person={outsider_id}").status_code == 403
    # A manager with global right and a live grant may explain exact-unit rights.
    preview = reviewer.get(path + f"?person={author_id}")
    assert preview.status_code == 200
    assert "Eigentümer des Wissensraums" in preview.text
    assert "Globale TAKT-Berechtigung fehlt" in preview.text

    csrf = csrf_of(page.text)
    url = f"/wissen/space/{space_id}/rechte"
    payload = dict(csrf=csrf, principal_kind="user",
                   principal_id=author_id, capability="edit", effect="deny")
    assert reviewer.post(url, data=payload).status_code == 303
    author = login("wissen-reader@example.org", "knowledge-test-123")
    assert author.get(f"/wissen/artikel/{article_id}").status_code == 200
    assert author.post(f"/wissen/artikel/{article_id}/save", data={
        "csrf": csrf_of(author.get(f"/wissen/artikel/{article_id}").text),
        "version": 1, "title": "Unzulässig", "body_md": "Sperre", "kind": "article"
    }).status_code == 403
    restricted = reviewer.get(path + f"?person={author_id}")
    assert "Explizite Sperre hat Vorrang" in restricted.text
    for forbidden in (
        {"capability": "publish"},
        {"capability": "manage"},
        {"capability": "ai"},
        {"principal_kind": "org", "principal_id": org_id},
        {"principal_id": outsider_id},
        {"include_children": "1"},
    ):
        assert reviewer.post(url, data={**payload, **forbidden}).status_code == 403

    # Even a valid delegate cannot use an article-specific ACL endpoint.
    assert reviewer.post(f"/wissen/article/{article_id}/rechte", data=payload).status_code == 403

    # Existing administrator capability and deny override remain in force.
    admin_token = csrf_of(admin.get(path).text)
    assert admin.post(url, data={**payload, "csrf": admin_token, "effect": "remove"}).status_code == 303
    assert author.get(f"/wissen/artikel/{article_id}").status_code == 200
    assert reviewer.get(path).status_code == 200
    with SessionLocal() as db:
        db.get(User, reviewer_id).permissions = "knowledge_read,knowledge_publish"
        db.commit()
    assert reviewer.get(path).status_code == 403


def test_review_inbox_filters_unrelated_users_and_honors_module_gate(sample):
    """Review dates and pending approvals never enumerate other organizations."""
    _, _, article_id, _, outsider_id, _ = sample
    author, reviewer = _publish_sample(sample)
    outsider = login("wissen-outsider@example.org", "knowledge-test-123")
    from datetime import date, timedelta
    with SessionLocal() as db:
        doc = db.get(KnowledgeArticle, article_id)
        doc.review_due_on = date.today() - timedelta(days=3)
        db.get(User, outsider_id).permissions = "knowledge_read,knowledge_publish"
        db.commit()
    url = "/wissen/pruefungen"
    result = reviewer.get(url)
    assert result.status_code == 200
    assert "Beschaffung Dienstmaterial" in result.text
    assert "Überfällig" in result.text
    assert "Beschaffung Dienstmaterial" not in outsider.get(url).text
    assert author.get(url).status_code == 200
    # An author cannot review their own document even with publish permissions.
    assert "Beschaffung Dienstmaterial" not in author.get(url).text
    settings(module_knowledge="0")
    assert reviewer.get(url).status_code == 404
    assert outsider.get(url).status_code == 404


def test_management_endpoints_do_not_accept_missing_csrf(sample):
    _, space_id, *_ = sample
    admin = login(*ADMIN)
    assert admin.post(f"/wissen/space/{space_id}/rechte", data={
        "principal_kind": "user", "principal_id": 1,
        "capability": "read", "effect": "allow",
    }).status_code == 400


def test_knowledge_markdown_tables_and_untrusted_html_are_safe():
    from app.knowledge import render_markdown
    rendered = str(render_markdown("| Feld | Wert |\n| --- | --- |\n| A | 42 |"))
    assert "<table>" in rendered and "<td>42</td>" in rendered
    malicious = str(render_markdown("<img src=x onerror=alert(1)>\n\n[unsafe](javascript:alert(1))"))
    assert "<img " not in malicious
    assert "<script>" not in malicious
    assert 'href="javascript:' not in malicious


def test_review_inbox_prioritizes_due_dates_over_recent_articles(sample):
    from datetime import timedelta
    from sqlalchemy import insert
    from app.knowledge import review_today

    _, space_id, article_id, _, _, reviewer_id = sample
    _, reviewer = _publish_sample(sample)
    today = review_today()
    with SessionLocal() as db:
        article = db.get(KnowledgeArticle, article_id)
        article.review_due_on = today - timedelta(days=1)
        db.execute(insert(KnowledgeArticle), [
            {"space_id": space_id, "owner_id": reviewer_id, "title": "Andere Fassung",
             "status": "published", "review_due_on": today + timedelta(days=90)}
            for _ in range(3001)
        ])
        db.commit()

    page = reviewer.get("/wissen/pruefungen")
    assert page.status_code == 200
    assert "Beschaffung Dienstmaterial" in page.text
    assert "Überfällig" in page.text
    assert "Andere Fassung" not in page.text


def test_review_confirmation_keeps_submitted_amendment_publishable(sample):
    from datetime import timedelta
    from app.knowledge import review_today

    _, _, article_id, *_ = sample
    author, reviewer = _publish_sample(sample)
    article = f"/wissen/artikel/{article_id}"
    proposal = article + "/entwurf"
    author_csrf = csrf_of(author.get(article).text)
    reviewer_csrf = csrf_of(reviewer.get(article).text)
    assert author.post(proposal + "/start", data={
        "csrf": author_csrf, "version": 3,
    }).status_code == 303
    assert author.post(proposal + "/save", data={
        "csrf": author_csrf, "version": 1, "title": "Neue Fassung", "body_md": "Neue Schritte",
    }).status_code == 303
    assert author.post(proposal + "/status", data={
        "csrf": author_csrf, "version": 2, "status": "review",
    }).status_code == 303
    payload = {"csrf": reviewer_csrf, "authority": "verified", "version": 3}
    assert reviewer.post(article + "/pruefung", data={
        **payload, "review_due_on": (review_today() - timedelta(days=1)).isoformat(),
    }).status_code == 422
    assert reviewer.post(article + "/pruefung", data={
        **payload, "review_due_on": review_today().isoformat(),
    }).status_code == 303
    assert "Heute fällig" in reviewer.get("/wissen/pruefungen").text
    assert "Neue Fassung" not in reviewer.get(article).text
    assert reviewer.post(proposal + "/status", data={
        "csrf": reviewer_csrf, "version": 3, "status": "published",
    }).status_code == 303
    assert "Neue Fassung" in reviewer.get(article).text


def test_source_references_enforce_current_dms_and_article_access(sample):
    import re
    from app.db import DmsAccess, DmsArea, DmsRecord

    _, _, article_id, _, outsider_id, reviewer_id = sample
    _, reviewer = _publish_sample(sample)
    settings(module_dms="1")
    with SessionLocal() as db:
        area = DmsArea(name="Vertraulicher Fachordner")
        db.add(area)
        db.flush()
        record = DmsRecord(area_id=area.id, title="Geschützter DMS-Titel", kind="manuell")
        db.add(record)
        db.add(DmsAccess(area_id=area.id, user_id=reviewer_id, level=1))
        db.add(DmsAccess(area_id=area.id, user_id=outsider_id, level=1))
        db.commit()
        area_id, record_id = area.id, record.id
    try:
        outsider = login("wissen-outsider@example.org", "knowledge-test-123")
        dms_page = reviewer.get(f"/dms/r/{record_id}")
        assert dms_page.status_code == 200
        contextual = re.search(r'href="(/wissen/quelle/ablage/[^"]+/wissen)"', dms_page.text)[1]
        reference = contextual.removesuffix("/wissen")
        assert reviewer.get(reference, follow_redirects=False).headers["location"] == f"/dms/r/{record_id}"
        with SessionLocal() as db:
            article = db.get(KnowledgeArticle, article_id)
            article.body_md = f'`{reference}`'
            db.commit()
        assert "Beschaffung Dienstmaterial" not in reviewer.get(contextual).text

        with SessionLocal() as db:
            article = db.get(KnowledgeArticle, article_id)
            article.body_md = f'[Manuell angegebener Titel]({reference} "Privater Hinweis")'
            db.commit()

        assert "Beschaffung Dienstmaterial" in reviewer.get(contextual).text
        assert "Beschaffung Dienstmaterial" not in outsider.get(contextual).text
        article_path = f"/wissen/artikel/{article_id}"
        html = reviewer.get(article_path).text
        assert f'href="{reference}"' in html and "Ablageeintrag öffnen" in html
        assert "Geschützter DMS-Titel" not in html
        assert "Privater Hinweis" not in html

        with SessionLocal() as db:
            access = db.scalar(select(DmsAccess).where(
                DmsAccess.area_id == area_id, DmsAccess.user_id == reviewer_id))
            db.delete(access)
            db.commit()

        html = reviewer.get(article_path).text
        assert "Quelle nicht verfügbar" in html
        assert "Manuell angegebener Titel" not in html
        assert f'href="{reference}"' not in html
        assert reviewer.get(contextual).status_code == 404
        assert reviewer.get(reference).status_code == 404

        with SessionLocal() as db:
            from datetime import timedelta
            db.get(DmsRecord, record_id).created_at += timedelta(seconds=1)
            db.add(DmsAccess(area_id=area_id, user_id=reviewer_id, level=1))
            db.commit()
        assert reviewer.get(f"/dms/r/{record_id}").status_code == 200
        assert reviewer.get(reference).status_code == 404
    finally:
        with SessionLocal() as db:
            for access in db.scalars(select(DmsAccess).where(DmsAccess.area_id == area_id)):
                db.delete(access)
            db.delete(db.get(DmsRecord, record_id))
            db.flush()
            db.delete(db.get(DmsArea, area_id))
            db.commit()


def test_room_approval_policy_snapshots_independent_reviewers(sample):
    _, space_id, article_id, _, _, reviewer_id = sample
    admin = login(*ADMIN)
    author = login("wissen-reader@example.org", "knowledge-test-123")
    reviewer = login("wissen-checker@example.org", "knowledge-test-123")
    management = f"/wissen/raum/{space_id}/verwaltung"
    policy = f"/wissen/raum/{space_id}/freigaben"
    path = f"/wissen/artikel/{article_id}"
    admin_csrf = csrf_of(admin.get(management).text)
    author_csrf = csrf_of(author.get(path).text)
    reviewer_csrf = csrf_of(reviewer.get(path).text)
    assert admin.post(policy, data={"required": 2}).status_code == 400
    assert author.post(policy, data={"csrf": author_csrf, "required": 2}).status_code == 403
    assert admin.post(policy, data={"csrf": admin_csrf, "required": 2}).status_code == 303
    assert author.post(path + "/status", data={
        "csrf": author_csrf, "status": "review", "version": 1,
    }).status_code == 303
    assert admin.post(policy, data={"csrf": admin_csrf, "required": 1}).status_code == 303
    decision = {"status": "published", "version": 2}
    assert author.post(path + "/status", data={**decision, "csrf": author_csrf}).status_code == 403
    assert reviewer.post(path + "/status", data={**decision, "csrf": reviewer_csrf}).status_code == 303
    assert "1 von 2 unabhängigen Freigaben" in reviewer.get(path).text
    assert reviewer.post(path + "/status", data={**decision, "csrf": reviewer_csrf}).status_code == 409
    assert "Beschaffung Dienstmaterial" not in reviewer.get("/wissen/pruefungen").text

    # A revoked approval does not count when a second reviewer votes.
    with SessionLocal() as db:
        db.get(User, reviewer_id).permissions = "knowledge_read"
        db.commit()
    assert admin.post(path + "/status", data={**decision, "csrf": admin_csrf}).status_code == 303
    assert "1 von 2 unabhängigen Freigaben" in admin.get(path).text
    with SessionLocal() as db:
        db.get(User, reviewer_id).permissions = "knowledge_read,knowledge_publish"
        db.commit()
    # Return and resubmission supersede both decisions and pick up the new rule.
    assert author.post(path + "/status", data={
        "csrf": author_csrf, "status": "draft", "version": 2,
    }).status_code == 303
    assert author.post(path + "/status", data={
        "csrf": author_csrf, "status": "review", "version": 3,
    }).status_code == 303
    assert reviewer.post(path + "/status", data={
        **decision, "csrf": reviewer_csrf, "version": 4,
    }).status_code == 303
    with SessionLocal() as db:
        assert db.get(KnowledgeArticle, article_id).status == "published"


def test_two_reviewers_publish_amendment_only_after_both_approve(sample):
    _, space_id, article_id, *_ = sample
    author, reviewer = _publish_sample(sample)
    admin = login(*ADMIN)
    admin_csrf = csrf_of(admin.get(f"/wissen/raum/{space_id}/verwaltung").text)
    assert admin.post(f"/wissen/raum/{space_id}/freigaben", data={
        "csrf": admin_csrf, "required": 2,
    }).status_code == 303
    article = f"/wissen/artikel/{article_id}"
    proposal = article + "/entwurf"
    author_csrf = csrf_of(author.get(article).text)
    assert author.post(proposal + "/start", data={"csrf": author_csrf, "version": 3}).status_code == 303
    assert author.post(proposal + "/save", data={
        "csrf": author_csrf, "version": 1, "title": "Überarbeitete Wissensfassung",
    }).status_code == 303
    assert author.post(proposal + "/status", data={
        "csrf": author_csrf, "version": 2, "status": "review",
    }).status_code == 303
    vote = {"version": 3, "status": "published"}
    reviewer_csrf = csrf_of(reviewer.get(proposal).text)
    assert reviewer.post(proposal + "/status", data={**vote, "csrf": reviewer_csrf}).status_code == 303
    assert "1 von 2 unabhängigen Freigaben" in reviewer.get(proposal).text
    assert "Überarbeitete Wissensfassung" not in reviewer.get(article).text
    assert admin.post(proposal + "/status", data={**vote, "csrf": admin_csrf}).status_code == 303
    assert "Überarbeitete Wissensfassung" in reviewer.get(article).text


def test_in_app_review_reminders_are_opt_in_and_follow_current_rights(sample):
    from app.knowledge import review_today

    _, space_id, article_id, _, _, reviewer_id = sample
    _, reviewer = _publish_sample(sample)
    settings(module_tasks="1")
    with SessionLocal() as db:
        db.get(KnowledgeArticle, article_id).review_due_on = review_today()
        db.commit()

    notice = "Wissensprüfungen sind fällig."
    preference = "/wissen/pruefungen/hinweise"
    assert notice not in reviewer.get("/tasks").text
    assert reviewer.post(preference, data={"enabled": "true"}).status_code == 400
    csrf = csrf_of(reviewer.get("/wissen/pruefungen").text)
    assert reviewer.post(preference, data={"csrf": csrf, "enabled": "true"}).status_code == 303
    assert notice in reviewer.get("/wissen").text
    task_view = reviewer.get("/tasks").text
    assert notice in task_view
    assert "Beschaffung Dienstmaterial" not in task_view

    with SessionLocal() as db:
        db.add(KnowledgeGrant(resource_kind="space", resource_id=space_id,
                              principal_kind="user", principal_id=reviewer_id,
                              capability="publish", effect="deny"))
        db.commit()
    assert notice not in reviewer.get("/tasks").text

    settings(module_knowledge="0")
    assert reviewer.post(preference, data={"csrf": csrf, "enabled": "false"}).status_code == 404
    assert notice not in reviewer.get("/tasks").text


def test_review_confirmation_rejects_current_amendment_contributor(sample):
    _, _, article_id, _, _, reviewer_id = sample
    _, reviewer = _publish_sample(sample)
    admin = login(*ADMIN)
    path = f"/wissen/artikel/{article_id}"
    with SessionLocal() as db:
        db.get(User, reviewer_id).permissions = "knowledge_read,knowledge_edit,knowledge_publish"
        db.commit()
    reviewer_csrf = csrf_of(reviewer.get(path).text)
    assert reviewer.post(path + "/entwurf/start", data={"csrf": reviewer_csrf, "version": 3}).status_code == 303
    assert reviewer.post(path + "/entwurf/status", data={
        "csrf": reviewer_csrf, "status": "review", "version": 1,
    }).status_code == 303
    admin_csrf = csrf_of(admin.get(path + "/entwurf").text)
    assert admin.post(path + "/entwurf/status", data={
        "csrf": admin_csrf, "status": "published", "version": 2,
    }).status_code == 303
    assert reviewer.post(path + "/pruefung", data={
        "csrf": reviewer_csrf, "version": 4, "authority": "verified",
    }).status_code == 403
    assert "Prüfung bestätigen und Termin speichern" not in reviewer.get(path).text
    assert admin.post(path + "/pruefung", data={
        "csrf": admin_csrf, "version": 4, "authority": "verified",
    }).status_code == 303


def test_article_rights_preview_reflects_restrictions_and_draft_read_gate(sample):
    from app import knowledge

    _, space_id, article_id, _, outsider_id, reviewer_id = sample
    admin = login(*ADMIN)
    reviewer = login("wissen-checker@example.org", "knowledge-test-123")
    path = f"/wissen/artikel/{article_id}/rechtevorschau"
    assert reviewer.get(path).status_code == 403
    assert admin.get(path + f"?person={reviewer_id}").status_code == 200
    assert "Aktive Organisationszuordnung" in admin.get(path + f"?person={reviewer_id}").text
    with SessionLocal() as db:
        article = db.get(KnowledgeArticle, article_id)
        article.scope = "restricted"
        db.get(User, outsider_id).permissions = "knowledge_read,knowledge_ai"
        for capability in ("read", "ai"):
            db.add(KnowledgeGrant(resource_kind="article", resource_id=article_id,
                                  principal_kind="user", principal_id=outsider_id,
                                  capability=capability, effect="allow"))
        db.commit()
        outsider = db.get(User, outsider_id)
        space = db.get(KnowledgeSpace, space_id)
        assert not knowledge.allowed(db, outsider, space, "ai", article)
    assert "Der Artikel erfordert eine eigene Freigabe" in admin.get(path + f"?person={reviewer_id}").text
    assert "Der unveröffentlichte Artikel erfordert zusätzlich ein Redaktionsrecht" in admin.get(path + f"?person={outsider_id}").text
    with SessionLocal() as db:
        grant = db.scalar(select(KnowledgeGrant).where(
            KnowledgeGrant.resource_kind == "article",
            KnowledgeGrant.resource_id == article_id, KnowledgeGrant.capability == "read"))
        grant.effect = "deny"
        db.commit()
    assert "Explizite Sperre hat Vorrang (am Artikel)" in admin.get(path + f"?person={outsider_id}").text
    settings(module_knowledge="0")
    assert admin.get(path).status_code == 404
