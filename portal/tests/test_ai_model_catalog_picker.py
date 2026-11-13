"""Live model catalog picker: show all server-returned models, keep manual fallback."""
import asyncio

import pytest

from app import ai_provider
from app.ai_models import AIProvider
from app.db import SessionLocal
from conftest import csrf_of, login, settings


def _provider():
    with SessionLocal() as db:
        provider = AIProvider(
            name="Model catalog hotfix test", base_url="https://llm.example.org/v1",
            model_id="original-model", active=True,
        )
        db.add(provider)
        db.commit()
        return provider.id


def test_all_reported_models_can_be_selected_as_default(monkeypatch):
    settings(module_ai="1")
    pid = _provider()
    reported = [{"id": f"server-model-{number:03d}", "owned_by": "fixture"}
                for number in range(325)]

    async def fake_request(provider, operation, token, *, payload=None):
        assert provider.id == pid and operation == "models" and payload is None
        return {"data": reported}

    monkeypatch.setattr(ai_provider, "_request", fake_request)
    admin = login("admin@example.org", "admin-passwort-123")
    page = admin.get(f"/admin/ai?edit={pid}")
    assert page.status_code == 200
    assert 'data-ai-default-model-picker' in page.text
    assert f'data-provider-id="{pid}"' in page.text
    assert '/static/ai-model-catalog.js' in page.text
    assert 'id="vector-model"' in page.text
    assert 'id="ai-embedding-test-model"' in page.text

    catalog = admin.get(f"/admin/ai/provider/{pid}/models")
    assert catalog.status_code == 200
    assert catalog.headers["cache-control"] == "private, no-store"
    entries = catalog.json()["models"]
    assert len(entries) == 325
    assert entries[0]["id"] == "server-model-000"
    assert entries[-1]["id"] == "server-model-324"
    assert entries[-1]["features"]["vision"] == "unknown"
    # The last model beyond the previous 200-item cutoff is a valid default.
    token = csrf_of(page.text)
    result = admin.post("/admin/ai/provider", data={
        "csrf": token, "provider_id": str(pid),
        "name": "Model catalog hotfix test",
        "base_url": "https://llm.example.org/v1",
        "model_id": "server-model-324", "active": "1",
    })
    assert result.status_code == 303
    with SessionLocal() as db:
        assert db.get(AIProvider, pid).model_id == "server-model-324"


def test_catalog_does_not_silently_truncate_above_safety_limit(monkeypatch):
    pid = _provider()

    async def too_many(provider, operation, token, *, payload=None):
        return {"data": [{"id": "x"} for _ in range(5001)]}

    monkeypatch.setattr(ai_provider, "_request", too_many)
    with SessionLocal() as db:
        with pytest.raises(ai_provider.AIProviderError, match="5.000"):
            asyncio.run(ai_provider.list_model_details(db.get(AIProvider, pid)))


def test_manual_model_id_stays_valid_when_server_has_no_catalog():
    pid = _provider()
    admin = login("admin@example.org", "admin-passwort-123")
    page = admin.get(f"/admin/ai?edit={pid}")
    csrf = csrf_of(page.text)
    response = admin.post("/admin/ai/provider", data={
        "csrf": csrf, "provider_id": str(pid),
        "name": "Model catalog hotfix test",
        "base_url": "https://llm.example.org/v1",
        "model_id": "manually-configured-alias", "active": "1",
    })
    assert response.status_code == 303
    with SessionLocal() as db:
        assert db.get(AIProvider, pid).model_id == "manually-configured-alias"
