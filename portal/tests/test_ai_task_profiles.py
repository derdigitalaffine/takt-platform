"""Task-based model profiles and safe server catalog: no real LLM calls."""
import asyncio

import pytest
from sqlalchemy import select

from app import ai_provider, ai_task_routing
from app.ai_models import AIProvider, AITaskProfile
from app.db import SessionLocal, User
from app.security import hash_password
from conftest import csrf_of, login, settings


ADMIN = ("admin@example.org", "admin-passwort-123")


def _make_provider(name):
    with SessionLocal() as db:
        p = AIProvider(name=name, base_url="https://llm.example.org/v1",
                       model_id="default-model", active=True,
                       text_key_enc="", image_key_enc="")
        db.add(p)
        db.commit()
        return p.id


def test_task_profile_admin_save_resolve_reset_and_fail_closed():
    settings(module_ai="1")
    pid = _make_provider("task routing smoke")
    c = login(*ADMIN)
    csrf = csrf_of(c.get("/admin/ai").text)
    with SessionLocal() as db:
        # Unassigned tasks keep the existing default selection.
        legacy = db.get(AIProvider, pid)
        assert ai_task_routing.select_provider(db, "form_draft", fallback=legacy).id == pid
    saved = c.post("/admin/ai/task-profile", data={
        "csrf": csrf, "task": "form_draft", "provider_id": pid,
        "model_id": "custom-structured-model",
    })
    assert saved.status_code == 303, saved.text
    try:
        with SessionLocal() as db:
            profile = db.get(AITaskProfile, "form_draft")
            assert profile.provider_id == pid
            resolved = ai_task_routing.select_provider(db, "form_draft")
            assert resolved.model_id == "custom-structured-model"
            assert resolved.base_url == "https://llm.example.org/v1"
            assert resolved.text_key_enc == ""
            assert db.get(AIProvider, pid).model_id == "default-model"
        assert "custom-structured-model" in c.get("/admin/ai").text
        assert c.post("/admin/ai/task-profile", data={
            "csrf": csrf, "task": "../not-registered",
            "provider_id": pid, "model_id": "abc",
        }).status_code == 400
        assert c.post("/admin/ai/task-profile", data={
            "csrf": "invalid", "task": "form_draft",
            "provider_id": pid, "model_id": "evil",
        }).status_code == 400
        with SessionLocal() as db:
            db.get(AIProvider, pid).active = False
            db.commit()
            with pytest.raises(ai_provider.AIProviderError):
                ai_task_routing.select_provider(db, "form_draft")
            db.get(AIProvider, pid).active = True
            db.commit()
        # A referenced provider must not be deleted without removing task route.
        deleted = c.post(f"/admin/ai/provider/{pid}/delete", data={"csrf": csrf})
        assert deleted.status_code == 303
        with SessionLocal() as db:
            assert db.get(AIProvider, pid) is not None
    finally:
        with SessionLocal() as db:
            profile = db.get(AITaskProfile, "form_draft")
            if profile:
                db.delete(profile)
            db.commit()
    reset = c.post("/admin/ai/task-profile", data={
        "csrf": csrf, "task": "form_draft", "provider_id": 0,
    })
    assert reset.status_code == 303


def test_catalog_uses_reported_capabilities_only_and_is_admin_only(monkeypatch):
    settings(module_ai="1")
    pid = _make_provider("catalog parser smoke")

    async def fake_request(_provider, operation, _key, *, payload=None):
        assert operation == "models" and payload is None
        return {"data": [
            {"id": "vision-agent", "context_length": 32768,
             "capabilities": {"vision": True, "tools": False}},
            {"id": "unknown-model"},
            {"id": "unknown-model"},
            {"id": "", "supports_streaming": True},
            {"bogus": "ignored"},
        ]}

    monkeypatch.setattr(ai_provider, "_request", fake_request)
    c = login(*ADMIN)
    response = c.get(f"/admin/ai/provider/{pid}/models")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "private, no-store"
    records = response.json()["models"]
    assert len(records) == 2
    assert records[0]["features"]["vision"] == "reported"
    assert records[0]["features"]["tools"] == "unsupported"
    assert records[0]["features"]["json"] == "unknown"
    assert records[0]["context_tokens"] == 32768
    assert records[1]["features"]["vision"] == "unknown"
    html = c.get("/admin/ai").text
    assert 'data-ai-task-form' in html
    assert '/static/ai-task-profiles.js' in html
    assert 'Ortsrecht · Texttreue' in html
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == "task-route-reader@example.org"))
        if existing is None:
            db.add(User(email="task-route-reader@example.org", name="Reader",
                        password_hash=hash_password("reader-passwort"),
                        must_change_password=False, is_admin=False, active=True))
            db.commit()
    reader = login("task-route-reader@example.org", "reader-passwort")
    assert reader.get(f"/admin/ai/provider/{pid}/models").status_code == 403
    assert reader.get("/admin/ai").status_code == 403


def test_catalog_rejects_malformed_list(monkeypatch):
    pid = _make_provider("malformed catalog smoke")
    with SessionLocal() as db:
        provider = db.get(AIProvider, pid)

        async def wrong(*args, **kwargs):
            return {"data": "not-a-list"}

        monkeypatch.setattr(ai_provider, "_request", wrong)
        with pytest.raises(ai_provider.AIProviderError):
            asyncio.run(ai_provider.list_model_details(provider))
