"""Admin UI progress and live provider diagnostics without leaking test content."""
from pathlib import Path

from sqlalchemy import func, select

from app import ai_provider, ai_index_status, ai_vector
from app.ai_models import AIProvider, AIKnowledge, AIKnowledgeVector, AIMessage
from app.db import SessionLocal
from conftest import csrf_of, login, settings


def _provider():
    with SessionLocal() as db:
        provider = AIProvider(
            name="Diagnostics synthetic provider", model_id="test-llm",
            base_url="https://llm.example.org/v1", active=True,
        )
        db.add(provider)
        db.commit()
        return provider.id


def test_admin_frontend_loads_polling_script_and_progress_in_body():
    client = login("admin@example.org", "admin-passwort-123")
    response = client.get("/admin/ai")
    assert response.status_code == 200
    html = response.text
    assert "<title>KI-Verwaltung · " in html
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]
    assert "<script" not in title
    assert '<script src="/static/ai-admin-knowledge.js" defer></script>' in html
    assert 'data-ai-index-progressbar' in html
    assert 'data-ai-index-percent' in html
    assert 'data-ai-index-doc-progress' in html or "Noch keine eigenen Einträge" in html
    assert 'data-ai-diagnostic="llm"' in html
    assert 'data-ai-diagnostic="embedding"' in html
    status = client.get("/admin/ai/index/status")
    assert status.status_code == 200
    assert status.headers["content-type"].startswith("application/json")
    for key in ("chunks_ready", "chunks_total", "percent", "jobs", "documents"):
        assert key in status.json()
    assert 0 <= status.json()["percent"] <= 100


def test_live_llm_test_runs_real_provider_adapter_without_chat_persistence(monkeypatch):
    pid = _provider()
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/admin/ai").text)
    seen = {}

    async def fake_complete(provider, messages, **kwargs):
        seen["provider"] = provider.id
        seen["messages"] = messages
        seen["tokens"] = kwargs.get("max_tokens")
        return "Verbindungstest erfolgreich. <script>inert</script>"

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    with SessionLocal() as db:
        before = db.scalar(select(func.count(AIMessage.id)))
    response = client.post("/admin/ai/diagnostics/llm", data={
        "csrf": csrf, "provider_id": pid,
        "prompt": "Antworte auf diese synthetische Testfrage.",
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["model"] == "test-llm"
    assert payload["provider"] == "Diagnostics synthetic provider"
    assert payload["reply"] == "Verbindungstest erfolgreich. <script>inert</script>"
    assert payload["duration_ms"] >= 0
    assert seen["provider"] == pid
    assert seen["messages"][-1]["content"] == "Antworte auf diese synthetische Testfrage."
    assert seen["tokens"] == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AIMessage.id))) == before
    assert client.post("/admin/ai/diagnostics/llm", data={
        "csrf": csrf, "provider_id": pid, "prompt": " ",
    }).status_code == 400
    js = (Path(__file__).resolve().parents[1] / "app" / "static" /
          "ai-admin-knowledge.js").read_text()
    assert "result.textContent" in js
    assert "result.innerHTML" not in js


def test_embedding_diagnostic_uses_synthetic_phrase_without_indexing(monkeypatch):
    pid = _provider()
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/admin/ai").text)
    seen = {}

    async def fake_embed(provider, texts, model_id):
        seen.update({"provider": provider.id, "texts": texts, "model": model_id})
        return [[0.5, 0.6, 0.7, 0.8]]

    monkeypatch.setattr(ai_provider, "embed", fake_embed)
    with SessionLocal() as db:
        before = db.scalar(select(func.count(AIKnowledgeVector.id)))
    response = client.post("/admin/ai/diagnostics/embedding", data={
        "csrf": csrf, "provider_id": pid, "model_id": "test-embedding-model",
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["model"] == "test-embedding-model"
    assert payload["dimensions"] == 4
    assert payload["duration_ms"] >= 0
    assert seen["provider"] == pid
    assert seen["texts"] == ["TAKT Embedding-Verbindungstest mit synthetischen Daten."]
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AIKnowledgeVector.id))) == before
    assert client.post("/admin/ai/diagnostics/embedding", data={
        "csrf": csrf, "provider_id": pid, "model_id": "",
    }).status_code == 400


def test_live_progress_counts_current_chunks_and_invalidates_old_versions():
    pid = _provider()
    with SessionLocal() as db:
        doc = AIKnowledge(title="Fortschritts-Testeintrag",
                          body_md="a" * 1500, enabled=True)
        db.add(doc)
        db.commit()
        doc_id = doc.id
    settings(ai_knowledge_enabled="1", ai_vector_enabled="1",
             ai_vector_model_id="synthetic-progress-model",
             ai_vector_provider_id=str(pid))
    with SessionLocal() as db:
        doc = db.get(AIKnowledge, doc_id)
        segments = ai_vector.chunks(doc.body_md)
        assert len(segments) == 2
        db.add(AIKnowledgeVector(
            knowledge_id=doc_id, chunk_no=0, model_id="synthetic-progress-model",
            source_hash=ai_vector.source_hash(doc.body_md),
            chunk_text=segments[0], vector_json="[0.1, 0.2]",
        ))
        db.commit()
        row = ai_index_status.status(db)["documents"][str(doc_id)]
        assert row["chunks_total"] == 2
        assert row["chunks_ready"] == 1
        assert row["percent"] == 50
        doc.body_md = "Eine neue, noch nicht indizierte Fassung."
        db.commit()
        row = ai_index_status.status(db)["documents"][str(doc_id)]
        assert row["chunks_ready"] == 0
        assert row["percent"] == 0
    settings(ai_vector_enabled="0", ai_vector_provider_id="0", ai_vector_model_id="")
