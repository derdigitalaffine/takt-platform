"""Semantic RAG is opt-in, source-checked and never replaces lexical retrieval."""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import ai_provider, ai_vector
from app.ai_models import AIKnowledge, AIKnowledgeVector, AIProvider
from app.db import SessionLocal, User
from conftest import settings


def _setup():
    settings(module_ai="1", ai_knowledge_enabled="1", ai_vector_enabled="1",
             ai_vector_provider_id="0", ai_vector_model_id="semantic-test")
    with SessionLocal() as db:
        provider = AIProvider(name="Vector Testprovider", model_id="chat-test",
                              base_url="https://llm.example.org/api", active=True)
        db.add(provider)
        db.flush()
        pid = provider.id
        db.commit()
    settings(ai_vector_provider_id=str(pid))
    return pid


def test_embeddings_validate_dimensions_and_index(monkeypatch):
    async def valid(_p, operation, _key, *, payload):
        assert operation == "embeddings"
        assert payload["input"] == ["eins", "zwei"]
        return {"data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]}
    monkeypatch.setattr(ai_provider, "_request", valid)
    p = SimpleNamespace(text_key_enc="fake")
    vectors = asyncio.run(ai_provider.embed(p, ["eins", "zwei"], "semantic-test"))
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]

    async def invalid(_p, operation, _key, *, payload):
        return {"data": [{"index": 0, "embedding": [float("nan"), 1.0]}]}
    monkeypatch.setattr(ai_provider, "_request", invalid)
    with pytest.raises(ai_provider.AIProviderError):
        asyncio.run(ai_provider.embed(p, ["eins"], "semantic-test"))


def test_vector_index_invalidates_changed_and_revoked_sources(monkeypatch):
    _setup()
    async def fake_embed(provider, texts, model_id):
        assert model_id == "semantic-test"
        assert all(len(text) <= 4000 for text in texts)
        return [[1.0, 0.0] for text in texts]
    monkeypatch.setattr(ai_provider, "embed", fake_embed)
    with SessionLocal() as db:
        doc = AIKnowledge(title="Gebührenordnung", body_md="Nutzung kostet genau 23 Euro.",
                          enabled=True)
        db.add(doc)
        db.flush()
        did = doc.id
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert user and user.can("ai_knowledge")
        count = asyncio.run(ai_vector.reindex_document(db, did))
        assert count == 1
        result = asyncio.run(ai_vector.retrieve(db, user, "Nutzungsgebühr"))
        assert any(item["url"] == f"/ki/wissen/{did}" for item in result)

        # Source edit invalidates the old cache immediately, even before reindex.
        doc.body_md = "Andere Fassung."
        db.commit()
        assert asyncio.run(ai_vector.retrieve(db, user, "Nutzungsgebühr")) == []
        # Revocation remains effective even if old vectors still exist.
        doc.enabled = False
        db.commit()
        assert asyncio.run(ai_vector.retrieve(db, user, "Nutzungsgebühr")) == []
        with pytest.raises(ai_provider.AIProviderError):
            asyncio.run(ai_vector.reindex_document(db, did))
        assert db.scalar(select(AIKnowledgeVector).where(
            AIKnowledgeVector.knowledge_id == did)) is not None

    settings(ai_vector_enabled="0")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert asyncio.run(ai_vector.retrieve(db, user, "Test")) == []


def test_semantic_retrieval_never_calls_provider_without_knowledge_permission(monkeypatch):
    _setup()
    async def forbidden(*args, **kwargs):
        pytest.fail("Embedding provider must not receive unauthorized queries")
    monkeypatch.setattr(ai_provider, "embed", forbidden)
    user = SimpleNamespace(can=lambda action: False)
    with SessionLocal() as db:
        assert asyncio.run(ai_vector.retrieve(db, user, "streng vertraulich")) == []


def test_semantic_failure_degrades_to_lexical_retrieval(monkeypatch):
    _setup()
    async def down(*args, **kwargs):
        raise ai_provider.AIProviderError("Dienst ist nicht erreichbar.")
    monkeypatch.setattr(ai_provider, "embed", down)
    with SessionLocal() as db:
        doc = AIKnowledge(title="Vertrauensquelle", body_md="Lokal vorhandener Quelltext",
                          enabled=True)
        db.add(doc)
        db.flush()
        db.add(AIKnowledgeVector(knowledge_id=doc.id, chunk_no=0, model_id="semantic-test",
                 source_hash=ai_vector.source_hash(doc.body_md), chunk_text=doc.body_md,
                 vector_json="[1, 0]"))
        db.commit()
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert asyncio.run(ai_vector.retrieve(db, user, "Frage")) == []
