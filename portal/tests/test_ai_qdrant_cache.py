"""Qdrant is an opt-in ranking cache, never an ACL or source of plaintext."""
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app import ai_provider, ai_qdrant, ai_vector
from app.ai_models import AIKnowledge, AIKnowledgeVector, AIProvider
from app.db import SessionLocal, User
from conftest import settings


def _setup():
    settings(module_ai="1", ai_vector_enabled="1",
             ai_knowledge_enabled="1", ai_qdrant_enabled="1",
             ai_vector_provider_id="0", ai_vector_model_id="cache-test-model",
             ai_qdrant_revision="0", ai_qdrant_synced_revision="-1")
    with SessionLocal() as db:
        p = AIProvider(name="Qdrant Cache Test Provider", model_id="unused",
                       base_url="https://llm.example.org/api", active=True)
        db.add(p)
        db.flush()
        pid = p.id
        db.commit()
    settings(ai_vector_provider_id=str(pid))


def test_cache_only_receives_vectors_and_local_results_are_checked(monkeypatch):
    _setup()
    with SessionLocal() as db:
        doc = AIKnowledge(title="Interne Vorlage", body_md="Überprüfung alle drei Monate",
                          enabled=True)
        db.add(doc)
        db.flush()
        vec = AIKnowledgeVector(
            knowledge_id=doc.id, chunk_no=0, model_id="cache-test-model",
            source_hash=ai_vector.source_hash(doc.body_md),
            chunk_text=doc.body_md, vector_json="[0.8, 0.6]"
        )
        db.add(vec)
        db.commit()
        did, vid = doc.id, vec.id

    requests = []
    async def fake_request(method, path, payload=None, *, not_found_ok=False):
        requests.append((method, path, payload))
        if path.endswith("/points/query"):
            return {"status": "ok", "result": {"points": [
                {"id": vid, "score": 0.9},
                {"id": 999_999_999, "score": 0.95},
            ]}}
        return {"status": "ok", "result": {}}
    monkeypatch.setattr(ai_qdrant, "_request", fake_request)

    with SessionLocal() as db:
        assert asyncio.run(ai_qdrant.rebuild(db)) == 1
        assert ai_qdrant.active(db)
    synced = json.dumps(requests, ensure_ascii=False)
    assert "Überprüfung alle drei Monate" not in synced
    assert "Interne Vorlage" not in synced
    assert "api_key" not in synced
    assert '"vector": [0.8, 0.6]' in synced

    async def embed(_provider, texts, model_id):
        return [[0.8, 0.6] for _ in texts]
    monkeypatch.setattr(ai_provider, "embed", embed)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        assert asyncio.run(ai_vector.retrieve(db, user, "Überprüfung"))[0]["url"] == f"/ki/wissen/{did}"
        doc = db.get(AIKnowledge, did)
        doc.body_md = "Neue Fassung"
        ai_qdrant.invalidate(db)
        db.commit()
        assert not ai_qdrant.active(db)
        assert asyncio.run(ai_vector.retrieve(db, user, "Überprüfung")) == []


def test_off_and_qdrant_failure_fall_back_without_external_source(monkeypatch):
    _setup()
    async def down(*args, **kwargs):
        raise ai_qdrant.QdrantError("Cache unavailable")
    monkeypatch.setattr(ai_qdrant, "_request", down)
    with SessionLocal() as db:
        assert asyncio.run(ai_qdrant.query(db, "cache-test-model", [0.5, 0.5])) == []
    settings(ai_qdrant_enabled="0")
    with SessionLocal() as db:
        assert not ai_qdrant.active(db)
        assert asyncio.run(ai_qdrant.query(db, "cache-test-model", [0.5, 0.5])) == []


def test_qdrant_container_is_private_and_requires_explicit_profile():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'profiles: ["rag"]' in compose
    assert "rag_private:" in compose
    assert "internal: true" in compose
    assert "/qdrant/storage:size=" in compose
    assert "docker compose --profile rag up -d qdrant" in compose


def test_missing_volatile_collection_invalidates_synced_revision(monkeypatch):
    _setup()
    settings(ai_qdrant_revision="5", ai_qdrant_synced_revision="5")
    async def missing(method, path, payload=None, *, not_found_ok=False):
        assert method == "POST" and path.endswith("/points/query")
        assert not_found_ok
        return None
    monkeypatch.setattr(ai_qdrant, "_request", missing)
    with SessionLocal() as db:
        assert ai_qdrant.active(db)
        assert asyncio.run(ai_qdrant.query(db, "cache-test-model", [1.0, 0.0])) == []
        assert not ai_qdrant.active(db)
