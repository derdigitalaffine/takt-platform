"""AI answers retain provenance: newly stamped internal citations expire on source edits."""
import json

from sqlalchemy import select

from app import ai_knowledge, laws
from app.ai_models import AIKnowledge, AILawSource
from app.db import LawText, SessionLocal, User
from app.routes_ai import _source_meta
from conftest import settings


def _admin(db):
    user = db.scalar(select(User).where(User.email == "admin@example.org"))
    assert user and user.can("ai_knowledge")
    return user


def test_curated_knowledge_citation_rejected_after_content_or_title_change():
    settings(module_ai="1", ai_knowledge_enabled="1")
    with SessionLocal() as db:
        user = _admin(db)
        doc = AIKnowledge(title="Einmalige Quellenmarkierung RAG",
                          body_md="Gittersteuersatz beträgt 19 Euro.", enabled=True)
        db.add(doc)
        db.commit()
        source = next(s for s in ai_knowledge.retrieve(db, user, "Gittersteuersatz", limit=8)
                      if s["url"] == f"/ki/wissen/{doc.id}")
        assert len(source["revision"]) == 64
        citation = json.loads(_source_meta([source]))
        assert citation[0]["revision"] == source["revision"]
        assert ai_knowledge.sources_accessible(db, user, citation)
        doc.title = "Geänderter Titel"
        db.commit()
        assert not ai_knowledge.sources_accessible(db, user, citation)
        doc.title = "Einmalige Quellenmarkierung RAG"
        doc.body_md = "Gittersteuersatz beträgt jetzt 27 Euro."
        db.commit()
        assert not ai_knowledge.sources_accessible(db, user, citation)


def test_current_law_citation_revoked_on_new_text_fassung():
    settings(module_ai="1", ai_knowledge_enabled="1", module_laws="1")
    with SessionLocal() as db:
        user = _admin(db)
        law = LawText(title="Gittersteggebühr Spezialordnung",
                      slug="ai-rag-gittersteg-versionsquelle",
                      doc_type="satzung", published=True,
                      valid_from="2025-01-01",
                      body_md="# Gittersteggebühr Spezialordnung\n\n### § 1 Gittersteggebühr\n\n"
                              "Die Gittersteggebühr beträgt 13 Euro.")
        db.add(law)
        db.flush()
        laws.store(db, law)
        db.add(AILawSource(law_id=law.id))
        db.commit()
        source = next(s for s in ai_knowledge.retrieve(db, user, "Gittersteggebühr", limit=8)
                      if s["url"].startswith(f"/recht/{law.slug}"))
        assert ai_knowledge.sources_accessible(db, user, json.loads(_source_meta([source])))
        law.body_md += "\n\nDie geänderte Gebühr beträgt 17 Euro."
        laws.store(db, law)
        db.commit()
        assert not ai_knowledge.sources_accessible(
            db, user, json.loads(_source_meta([source])))
