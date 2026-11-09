"""Manual DMS knowledge must retain all existing document ACLs."""
from sqlalchemy import select

from app import ai_dms, ai_knowledge
from app.ai_models import AIDmsSource
from app.db import DmsAccess, DmsArea, DmsRecord, SessionLocal, User
from app.security import hash_password
from conftest import csrf_of, login, settings


def _setup(tag: str):
    settings(module_ai="1", module_dms="1", ai_knowledge_enabled="1")
    with SessionLocal() as db:
        area = DmsArea(name="Testbereich zur DMS-KI-Freigabe " + tag, code="AI-ACL-" + tag)
        other = DmsArea(name="Anderer vertraulicher Bereich " + tag, code="AI-HIDDEN-" + tag)
        reader = User(email=f"dms-ai-reader-{tag}@example.org", name="DMS reader",
                      password_hash=hash_password("passwort-123"),
                      permissions="ai_chat,ai_knowledge", active=True,
                      must_change_password=False)
        hidden = User(email=f"dms-ai-outsider-{tag}@example.org", name="DMS outsider",
                      password_hash=hash_password("passwort-123"),
                      permissions="ai_chat,ai_knowledge", active=True,
                      must_change_password=False)
        db.add_all([area, other, reader, hidden])
        db.flush()
        doc = DmsRecord(area_id=area.id, kind="manuell",
                        title="Brandschutzplan Testobjekt",
                        note="Schlüsselwort Feuerschutz: Prüfung alle zwölf Monate")
        citizen = DmsRecord(area_id=area.id, kind="antrag",
                            title="Persönlicher Antrag",
                            note="Geheime Bürgerdaten")
        db.add_all([doc, citizen])
        db.flush()
        db.add(DmsAccess(area_id=area.id, user_id=reader.id, level=1))
        db.commit()
        return doc.id, citizen.id, reader.id, hidden.id, other.id


def test_only_opted_in_manual_notes_and_acl_protected(monkeypatch):
    doc_id, citizen_id, reader_id, hidden_id, other_area_id = _setup('acl')
    with SessionLocal() as db:
        reader = db.get(User, reader_id)
        hidden = db.get(User, hidden_id)
        assert ai_dms.retrieve(db, reader, "Feuerschutz") == []
        db.add(AIDmsSource(record_id=doc_id))
        db.commit()
        found = ai_dms.retrieve(db, reader, "Feuerschutz")
        assert found and found[0]["url"] == f"/dms/r/{doc_id}"
        assert found[0]["kind"] == "dms"
        assert "Prüfung alle zwölf Monate" in found[0]["text"]
        assert ai_dms.retrieve(db, hidden, "Feuerschutz") == []
        assert ai_knowledge.sources_accessible(
            db, reader, [{"kind": "dms", "url": f"/dms/r/{doc_id}", "title": "Test"}])
        assert not ai_knowledge.sources_accessible(
            db, hidden, [{"kind": "dms", "url": f"/dms/r/{doc_id}", "title": "Test"}])
        assert not ai_dms.eligible(db.get(DmsRecord, citizen_id))
        db.get(DmsRecord, doc_id).area_id = other_area_id
        db.commit()
        assert ai_dms.retrieve(db, reader, "Feuerschutz") == []
        assert not ai_knowledge.sources_accessible(
            db, reader, [{"kind": "dms", "url": f"/dms/r/{doc_id}", "title": "Test"}])


def test_admin_approval_and_prohibition_for_citizen_application():
    doc_id, citizen_id, *_ = _setup('admin')
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/admin/ai").text)
    page = client.get("/admin/ai")
    assert page.status_code == 200
    assert "Brandschutzplan Testobjekt" in page.text
    bad = client.post(f"/admin/ai/dms/{citizen_id}/source",
                      data={"csrf": csrf, "allowed": "1"})
    assert bad.status_code == 400
    approved = client.post(f"/admin/ai/dms/{doc_id}/source",
                           data={"csrf": csrf, "allowed": "1"})
    assert approved.status_code == 303
    with SessionLocal() as db:
        assert db.get(AIDmsSource, doc_id) is not None
    revoked = client.post(f"/admin/ai/dms/{doc_id}/source",
                          data={"csrf": csrf})
    assert revoked.status_code == 303
    with SessionLocal() as db:
        assert db.get(AIDmsSource, doc_id) is None
