"""Law paragraphs in semantic RAG: publication, revision, date, and live ACL."""
import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app import ai_index_status, ai_knowledge, ai_law_vector, ai_law_vector_jobs, ai_provider, laws
from app.ai_models import AILawIndexJob, AILawVector, AIProvider
from app.db import LawText, LawVersion, SessionLocal, User
from conftest import csrf_of, login, settings


@pytest.fixture(autouse=True)
def _config():
    settings(module_ai="1", module_laws="1", ai_knowledge_enabled="1",
             ai_laws_include_all="1", ai_laws_excluded_ids="[]",
             ai_vector_auto_index="1", ai_vector_enabled="0",
             ai_vector_provider_id="0", ai_vector_model_id="")
    yield
    settings(ai_laws_include_all="0", ai_laws_excluded_ids="[]",
             ai_vector_auto_index="0", ai_vector_enabled="0",
             ai_vector_provider_id="0", ai_vector_model_id="")


def _setup(slug, *, internal=False, published=True, body=None, dated=False):
    with SessionLocal() as db:
        provider = AIProvider(
            name="Law embedding tests " + slug,
            base_url="https://llm.example.org/v1", model_id="chat-test",
            active=True,
        )
        law = LawText(
            title="Ordnung über die Nutzung des Gemeindegeländes " + slug,
            slug=slug, doc_type="satzung", published=published,
            internal=internal, valid_from="2026-01-01" if dated else "2025-01-01",
            body_md=body or "# Hausordnung\n\n### § 1 Nutzung\n\n"
                 "Das nächtliche Verweilen auf dem kommunalen Gelände ist untersagt."
        )
        db.add_all([provider, law])
        db.flush()
        laws.store(db, law)
        db.commit()
        provider_id, law_id = provider.id, law.id
    settings(ai_vector_enabled="1",
             ai_vector_provider_id=str(provider_id),
             ai_vector_model_id="law-vector-" + slug)
    return provider_id, law_id


def _fake_embeddings(monkeypatch):
    calls = []
    async def embed(provider, texts, model_id):
        calls.append((model_id, list(texts)))
        return [[1.0, 0.0, 0.0] for _ in texts]
    monkeypatch.setattr(ai_provider, "embed", embed)
    return calls


def _admin(db):
    user = db.scalar(select(User).where(User.email == "admin@example.org"))
    assert user is not None
    return user


def test_paragraph_embeddings_answer_semantically_different_chat_question(monkeypatch):
    _pid, law_id = _setup("ai-semantic-law-nacht")
    calls = _fake_embeddings(monkeypatch)
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) > 0
    with SessionLocal() as db:
        user = _admin(db)
        law = db.get(LawText, law_id)
        question = "Darf ich dort nach Einbruch der Dunkelheit schlafen?"
        assert not any(hit["url"].startswith(f"/recht/{law.slug}")
                       for hit in ai_knowledge.retrieve(db, user, question))
        hits = asyncio.run(ai_law_vector.retrieve(db, user, question))
        assert hits
        assert any(hit["url"].startswith(f"/recht/{law.slug}/") for hit in hits)
        assert all(hit["kind"] == "Rechtstext" for hit in hits)
        assert ai_knowledge.sources_accessible(db, user, hits)
        report = ai_law_vector_jobs.progress(db)
        assert report["laws"][str(law_id)]["percent"] == 100
        assert report["total_chunks"] >= 1
        assert ai_index_status.status(db)["law_embedding"]["laws"][str(law_id)]["ready"] >= 1
    assert calls and any("nächtliche" in text for _, passages in calls for text in passages)


def test_public_historical_version_is_independently_embedded_and_date_filtered(monkeypatch):
    _pid, law_id = _setup("ai-semantic-historisch", dated=True)
    with SessionLocal() as db:
        old = LawVersion(
            law_id=law_id, title="Alte Gemeindeordnung", public=True,
            valid_from="2021-01-01", valid_until="2026-01-01",
            body_md="# Hausordnung\n\n### § 1 Aufenthalt\n\n"
                    "Die Übernachtung auf öffentlichen Grünflächen war erlaubt.",
        )
        private = LawVersion(
            law_id=law_id, title="Nicht öffentliche Änderung", public=False,
            valid_from="2024-01-01",
            body_md="# Entwurf\n\n### § 1\n\nNicht zur Veröffentlichung.")
        db.add_all([old, private])
        db.commit()
        version_id, private_id = old.id, private.id
    _fake_embeddings(monkeypatch)
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) >= 1
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) >= 1
    with SessionLocal() as db:
        user = _admin(db)
        versions = list(db.scalars(select(AILawVector).where(AILawVector.law_id == law_id)))
        assert {row.version_id for row in versions} == {0, version_id}
        assert private_id not in {row.version_id for row in versions}
        old_hits = asyncio.run(ai_law_vector.retrieve(
            db, user, "War das Nachtlager am 01.06.2021 zulässig?", limit=20))
        assert any(f"/fassung/{version_id}/" in x["url"] for x in old_hits)
        assert not any(f"/fassung/{private_id}/" in x["url"] for x in old_hits)
        current_hits = asyncio.run(ai_law_vector.retrieve(
            db, user, "Darf man hier heute nach Mitternacht schlafen?"))
        assert current_hits and all("/fassung/" not in x["url"] for x in current_hits)
        assert ai_knowledge.sources_accessible(db, user, old_hits)


def test_revoked_law_is_denied_immediately_and_index_purged(monkeypatch):
    _pid, law_id = _setup("ai-semantic-widerruf")
    _fake_embeddings(monkeypatch)
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) > 0
    with SessionLocal() as db:
        user = _admin(db)
        original = asyncio.run(ai_law_vector.retrieve(
            db, user, "Kann man nachts dort bleiben?"))
        assert any(f"/recht/ai-semantic-widerruf/" in x["url"] for x in original)
    settings(ai_laws_excluded_ids=json.dumps([law_id]))
    with SessionLocal() as db:
        user = _admin(db)
        assert not any(f"/recht/ai-semantic-widerruf/" in x["url"]
                       for x in asyncio.run(ai_law_vector.retrieve(
                           db, user, "Kann man nachts dort bleiben?")))
        assert not ai_knowledge.sources_accessible(db, user, original)
        ai_law_vector_jobs.reconcile(db)
        assert not db.scalar(select(AILawVector.id).where(AILawVector.law_id == law_id))
        assert not db.scalar(select(AILawIndexJob.id).where(AILawIndexJob.law_id == law_id))


def test_unpublished_law_and_unpublished_version_are_not_embedded(monkeypatch):
    _pid, law_id = _setup("ai-semantic-geheim", published=False)
    calls = _fake_embeddings(monkeypatch)
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) == 0
    with SessionLocal() as db:
        assert not db.scalar(select(AILawVector.id).where(AILawVector.law_id == law_id))
    assert not calls


def test_content_change_invalidates_old_vectors_and_progress(monkeypatch):
    _pid, law_id = _setup("ai-semantic-aenderung")
    _fake_embeddings(monkeypatch)
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) > 0
    with SessionLocal() as db:
        user = _admin(db)
        old = asyncio.run(ai_law_vector.retrieve(db, user, "Darf man spät schlafen?"))
        law = db.get(LawText, law_id)
        law.body_md += "\n\nDie geänderte Bestimmung untersagt alle Lagerfeuer."
        laws.store(db, law)
        db.commit()
        assert not any("/ai-semantic-aenderung/" in hit["url"]
                       for hit in asyncio.run(ai_law_vector.retrieve(
                           db, user, "Darf man spät schlafen?")))
        ai_law_vector_jobs.reconcile(db)
        assert not db.scalar(select(AILawVector.id).where(AILawVector.law_id == law_id))
        assert ai_law_vector_jobs.progress(db)["laws"][str(law_id)]["percent"] == 0
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) > 0


def test_chat_both_paths_include_semantic_law_and_progress_UI(monkeypatch):
    provider_id, law_id = _setup("ai-semantic-chat-direkt")
    _fake_embeddings(monkeypatch)
    assert asyncio.run(ai_law_vector_jobs.tick(law_id=law_id)) > 0
    captured = []

    async def fake_complete(provider, messages, **kwargs):
        captured.append(messages)
        return "Antwort anhand der angegebenen Rechtsquelle."
    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    client = login("admin@example.org", "admin-passwort-123")
    page = client.get("/ki")
    assert 'name="use_knowledge" id="ai-use-knowledge" value="1" checked' in page.text
    csrf = csrf_of(page.text)
    new = client.post("/ki/new", data={"csrf": csrf, "provider_id": provider_id})
    assert new.status_code == 303
    chat_id = int(new.headers["location"].split("=")[1])
    for suffix in ("/message", "/message/updates"):
        response = client.post(f"/ki/{chat_id}{suffix}", data={
            "csrf": csrf,
            "message": "Kann man nach Sonnenuntergang dort übernachten?",
            "use_knowledge": "1",
        })
        assert response.status_code in (200, 303)
        assert f"/recht/ai-semantic-chat-direkt/" in json.dumps(captured[-1])
    admin = client.get("/admin/ai")
    assert admin.status_code == 200
    assert 'data-ai-law-index-progressbar' in admin.text
    assert 'data-ai-law-index-percent' in admin.text
    assert 'data-ai-law-source-progress="' in admin.text
    status = client.get("/admin/ai/index/status")
    assert status.status_code == 200
    assert status.json()["law_embedding"]["laws"][str(law_id)]["percent"] == 100
    assert "nächtliche" not in json.dumps(status.json())
    js = (Path(__file__).resolve().parents[1] / "app" /
          "static" / "ai-admin-knowledge.js").read_text()
    assert "data-ai-law-index-progressbar" in js
    assert "data-ai-law-source-progress" in js
