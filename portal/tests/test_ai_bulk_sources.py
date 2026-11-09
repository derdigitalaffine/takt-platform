"""Bulk AI source rules, fail-closed exceptions, live ACL and embedding states."""
import json

import pytest
from sqlalchemy import select

from app import ai_dms, ai_index_status, ai_knowledge, ai_source_policy, ai_vector, laws
from app.ai_models import AIKnowledge, AIKnowledgeVector, AIProvider
from app.db import DmsAccess, DmsArea, DmsRecord, LawText, SessionLocal, User
from app.security import hash_password
from conftest import csrf_of, login, settings


@pytest.fixture(autouse=True)
def _reset_bulk_settings():
    values = dict(module_ai="1", ai_knowledge_enabled="1", module_laws="1",
                  module_dms="1", ai_laws_include_all="0",
                  ai_laws_excluded_ids="[]", ai_dms_include_all="0",
                  ai_dms_excluded_ids="[]", ai_dms_excluded_areas="[]")
    settings(**values)
    yield
    settings(ai_laws_include_all="0", ai_laws_excluded_ids="[]",
             ai_dms_include_all="0", ai_dms_excluded_ids="[]",
             ai_dms_excluded_areas="[]", ai_vector_enabled="0")


def _client():
    client = login("admin@example.org", "admin-passwort-123")
    return client, csrf_of(client.get("/admin/ai").text)


def test_rule_lists_are_fail_closed():
    assert ai_source_policy.read_ids("[]") == set()
    for malformed in ("{}", "[1, true]", "[0]", "[-1]", '["1"]', "broken"):
        assert ai_source_policy.read_ids(malformed) is None


def test_all_published_laws_auto_included_with_per_source_exceptions():
    client, csrf = _client()
    with SessionLocal() as db:
        public = LawText(title="Bulk-Suchtest Gebührenordnung", slug="ai-bulk-law-public",
                         doc_type="satzung", published=True,
                         body_md="# Gebührenordnung\n\n### § 1 Bulk-Suchtest\n\nDie Bulk-Suchtestgebühr beträgt 21 Euro.")
        hidden = LawText(title="Bulk-Suchtest Entwurf", slug="ai-bulk-law-draft",
                         doc_type="satzung", published=False,
                         body_md="# Bulk-Suchtest\n\nGeheimhaltung der Nullversion.")
        internal = LawText(title="Bulk-Suchtest Intern", slug="ai-bulk-law-internal",
                           doc_type="satzung", published=True, internal=True,
                           body_md="# Bulk-Suchtest\n\nInterner Text nur mit Rechtsberechtigung.")
        db.add_all([public, hidden, internal])
        db.flush()
        for law in (public, hidden, internal):
            laws.store(db, law)
        public_id, hidden_id, internal_id = public.id, hidden.id, internal.id
        db.commit()
    assert client.post("/admin/ai/laws/mode", data={
        "csrf": csrf, "include_all": "1"}).status_code == 303
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        found = ai_knowledge.retrieve(db, user, "Bulk-Suchtest", limit=8)
        assert any(s["url"].startswith("/recht/ai-bulk-law-public") for s in found)
        assert not any("ai-bulk-law-draft" in s["url"] for s in found)
        no_laws = type("NoLaws", (), {"can": lambda self, key: key == "ai_knowledge"})()
        assert not any("ai-bulk-law-internal" in s["url"]
                       for s in ai_knowledge.retrieve(db, no_laws, "Bulk-Suchtest", limit=8))
        original = next(s for s in found if "ai-bulk-law-public" in s["url"])
        assert ai_knowledge.sources_accessible(db, user, [original])

    assert client.post(f"/admin/ai/laws/{public_id}/source", data={"csrf": csrf}).status_code == 303
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert not ai_knowledge.sources_accessible(db, user, [original])
        assert not any("ai-bulk-law-public" in s["url"]
                       for s in ai_knowledge.retrieve(db, user, "Bulk-Suchtest", limit=8))
    assert client.post(f"/admin/ai/laws/{public_id}/source",
                       data={"csrf": csrf, "allowed": "1"}).status_code == 303
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert ai_knowledge.sources_accessible(db, user, [original])

    # Revoke all mode: old manually approved sources stay separate.
    assert client.post("/admin/ai/laws/mode", data={"csrf": csrf}).status_code == 303
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert not any("ai-bulk-law-public" in s["url"]
                       for s in ai_knowledge.retrieve(db, user, "Bulk-Suchtest", limit=8))


def test_all_eligible_dms_records_and_nested_area_exceptions():
    client, csrf = _client()
    with SessionLocal() as db:
        root = DmsArea(name="KI Bulk Bereich", code="AI-BULK")
        db.add(root)
        db.flush()
        child = DmsArea(name="KI Bulk Unterbereich", code="AI-BULK.1", parent_id=root.id)
        user = User(email="ai-bulk-dms-reader@example.org", name="DMS reader",
                    password_hash=hash_password("password-local-123"),
                    permissions="ai_chat,ai_knowledge", active=True,
                    must_change_password=False)
        db.add_all([child, user])
        db.flush()
        record = DmsRecord(area_id=child.id, kind="manuell",
                           title="Dokument Bulk-Feuerschutzprüfung",
                           note="Bulk-Feuerschutzprüfung mindestens jährlich")
        citizen = DmsRecord(area_id=child.id, kind="antrag",
                            title="Bürgerantrag Bulk-Feuerschutzprüfung",
                            applicant="Vertraulich", note="Bulk-Feuerschutzprüfung geheim")
        db.add_all([record, citizen])
        db.add(DmsAccess(area_id=root.id, user_id=user.id, level=1))
        db.commit()
        root_id, child_id, record_id, reader_id, citizen_id = (
            root.id, child.id, record.id, user.id, citizen.id)
    assert client.post("/admin/ai/dms/settings", data={
        "csrf": csrf, "include_all": "1"}).status_code == 303
    with SessionLocal() as db:
        reader = db.get(User, reader_id)
        found = ai_dms.retrieve(db, reader, "Bulk-Feuerschutzprüfung")
        assert any(s["url"] == f"/dms/r/{record_id}" for s in found)
        assert not any(str(citizen_id) in s["url"] for s in found)
        original = next(s for s in found if s["url"].endswith(f"/{record_id}"))
        assert ai_knowledge.sources_accessible(db, reader, [original])
    assert client.post(f"/admin/ai/dms/{record_id}/source",
                       data={"csrf": csrf}).status_code == 303
    with SessionLocal() as db:
        reader = db.get(User, reader_id)
        assert not ai_knowledge.sources_accessible(db, reader, [original])
    assert client.post(f"/admin/ai/dms/{record_id}/source",
                       data={"csrf": csrf, "allowed": "1"}).status_code == 303
    assert client.post("/admin/ai/dms/settings", data={
        "csrf": csrf, "include_all": "1", "exclude_area": str(root_id)
    }).status_code == 303
    with SessionLocal() as db:
        reader = db.get(User, reader_id)
        assert ai_dms.retrieve(db, reader, "Bulk-Feuerschutzprüfung") == []
        assert not ai_knowledge.sources_accessible(db, reader, [original])
        assert ai_source_policy.area_excluded(db, child_id, {root_id})
    assert client.post("/admin/ai/dms/settings", data={
        "csrf": csrf, "include_all": "1", "exclude_area": "99999999"}).status_code == 400


def test_admin_embedding_progress_reports_ready_and_stale_without_contents():
    client, csrf = _client()
    with SessionLocal() as db:
        provider = AIProvider(name="KI Bulk Status Provider", base_url="https://example.org/v1",
                              model_id="chat-test", active=True)
        doc = AIKnowledge(title="Bulk Embedding Test", body_md="Ein lesbarer Wissenseintrag",
                          enabled=True)
        db.add_all([provider, doc])
        db.flush()
        pid, doc_id = provider.id, doc.id
        db.commit()
    settings(ai_vector_enabled="1", ai_vector_model_id="status-bulk-test",
             ai_vector_provider_id=str(pid))
    with SessionLocal() as db:
        doc = db.get(AIKnowledge, doc_id)
        passages = ai_vector.chunks(doc.body_md)
        for pos, chunk in enumerate(passages):
            db.add(AIKnowledgeVector(knowledge_id=doc_id, chunk_no=pos,
                                   model_id="status-bulk-test",
                                   source_hash=ai_vector.source_hash(doc.body_md),
                                   chunk_text=chunk, vector_json="[1.0, 0.0]"))
        db.commit()
        report = ai_index_status.status(db)
        assert report["documents"][str(doc_id)]["color"] == "success"
        assert report["active"]
        assert "Ein lesbarer Wissenseintrag" not in json.dumps(report)
        doc.body_md = "Der neue Stand ist noch nicht eingebettet"
        db.commit()
    response = client.get("/admin/ai/index/status")
    assert response.status_code == 200
    assert response.json()["documents"][str(doc_id)]["label"] == "Noch nicht indiziert"
    assert "Der neue Stand" not in response.text
    page = client.get("/admin/ai")
    assert page.status_code == 200
    assert 'name="include_all"' in page.text
    assert "Aktueller Embedding- und Indexstatus" in page.text
    assert 'data-ai-index-doc="' in page.text
    assert "Nur Textsuche" in json.dumps(response.json(), ensure_ascii=False)
