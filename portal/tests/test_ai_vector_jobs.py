"""Durable, opt-in semantic indexing and revocation regression tests."""
import asyncio
from sqlalchemy import select

from app import ai_provider, ai_vector, ai_vector_jobs
from app.ai_models import AIIndexJob, AIKnowledge, AIKnowledgeVector, AIProvider
from app.db import SessionLocal, utcnow
from conftest import settings


def _setup():
    settings(module_ai="1", ai_knowledge_enabled="1", ai_vector_enabled="1",
             ai_vector_auto_index="1", ai_vector_provider_id="0",
             ai_vector_model_id="queue-test-model")
    with SessionLocal() as db:
        p = AIProvider(name="Index Queue Test", base_url="https://llm.example.org/api",
                       model_id="unused-chat", active=True)
        db.add(p)
        db.commit()
        pid = p.id
    settings(ai_vector_provider_id=str(pid))


def test_automatic_index_changes_and_revocation(monkeypatch):
    _setup()
    calls = []
    async def fake_embed(provider, texts, model_id):
        assert model_id == "queue-test-model"
        calls.append(list(texts))
        return [[0.6, 0.8] for _ in texts]
    monkeypatch.setattr(ai_provider, "embed", fake_embed)
    with SessionLocal() as db:
        doc = AIKnowledge(title="Nur freigegebenes Wissen", body_md="Text A in TAKT",
                          enabled=True)
        db.add(doc)
        db.commit()
        doc_id = doc.id
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 1
    assert len(calls) == 1
    with SessionLocal() as db:
        vectors = list(db.scalars(select(AIKnowledgeVector).where(
            AIKnowledgeVector.knowledge_id == doc_id)))
        assert vectors and vectors[0].source_hash == ai_vector.source_hash("Text A in TAKT")
        job = db.scalar(select(AIIndexJob).where(AIIndexJob.knowledge_id == doc_id))
        assert job.status == "done"
        db.get(AIKnowledge, doc_id).body_md = "Text B (aktualisiert)"
        db.commit()
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 1
    with SessionLocal() as db:
        rows = list(db.scalars(select(AIKnowledgeVector).where(
            AIKnowledgeVector.knowledge_id == doc_id)))
        assert rows and all(row.source_hash == ai_vector.source_hash("Text B (aktualisiert)") for row in rows)
        db.get(AIKnowledge, doc_id).enabled = False
        db.commit()
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 0
    with SessionLocal() as db:
        assert db.scalar(select(AIKnowledgeVector).where(AIKnowledgeVector.knowledge_id == doc_id)) is None
        assert db.scalar(select(AIIndexJob).where(AIIndexJob.knowledge_id == doc_id)) is None


def test_index_failure_is_retryable_without_flood(monkeypatch):
    _setup()
    async def failing(*args, **kwargs):
        raise ai_provider.AIProviderError("Secret model failure text must not be persisted")
    monkeypatch.setattr(ai_provider, "embed", failing)
    with SessionLocal() as db:
        doc = AIKnowledge(title="Quelltext", body_md="Indizierung muss wiederholt werden",
                          enabled=True)
        db.add(doc)
        db.commit()
        doc_id = doc.id
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 0
    with SessionLocal() as db:
        job = db.scalar(select(AIIndexJob).where(AIIndexJob.knowledge_id == doc_id))
        assert job.status == "failed" and job.attempts == 1
        assert job.next_attempt_at > utcnow()
        assert "Secret" not in str(job.__dict__)
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 0  # backoff blocks repeated failures
    async def repaired(provider, texts, model_id):
        return [[1.0, 0.0] for _ in texts]
    monkeypatch.setattr(ai_provider, "embed", repaired)
    with SessionLocal() as db:
        job = db.scalar(select(AIIndexJob).where(AIIndexJob.knowledge_id == doc_id))
        job.next_attempt_at = utcnow()
        db.commit()
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 1


def test_auto_index_off_produces_no_provider_traffic(monkeypatch):
    _setup()
    settings(ai_vector_auto_index="0")
    async def forbidden(*args, **kwargs):
        raise AssertionError("No provider requests while disabled")
    monkeypatch.setattr(ai_provider, "embed", forbidden)
    with SessionLocal() as db:
        db.add(AIKnowledge(title="Off", body_md="Do not index this", enabled=True))
        db.commit()
    assert asyncio.run(ai_vector_jobs.tick(doc_id=doc_id)) == 0
