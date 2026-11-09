"""AI integration regressions: optional module, admin keys, chat isolation and local RAG."""
import asyncio
import json
from sqlalchemy import select

from app import ai_provider, laws
from app.ai_models import AIProvider, AIConversation, AIMessage, AIKnowledge, AILawSource
from app.db import LawText, SessionLocal, User
from app.security import decrypt, hash_password
from conftest import client, csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")


def _enable():
    settings(module_ai="1", module_laws="1", ai_knowledge_enabled="1")


def _user(email: str):
    with SessionLocal() as db:
        found = db.scalar(select(User).where(User.email == email))
        if found is None:
            found = User(email=email, name=email.split("@")[0],
                         password_hash=hash_password("passwort-123"),
                         permissions="ai_chat,ai_knowledge,ai_vision")
            db.add(found)
        found.permissions = "ai_chat,ai_knowledge,ai_vision"
        found.is_admin = False
        found.active = True
        found.must_change_password = False
        db.commit()
        return found.id


def _provider():
    with SessionLocal() as db:
        p = db.scalar(select(AIProvider).where(AIProvider.name == "AI Test Adapter"))
        if p is None:
            p = AIProvider(name="AI Test Adapter", base_url="https://llm.example.org/api",
                           model_id="example-model", active=True)
            db.add(p)
        p.active = True
        db.commit()
        return p.id


def test_ai_disabled_by_default_but_admin_settings_reachable():
    settings(module_ai="0")
    c = login(*ADMIN)
    assert c.get("/ki").status_code == 404
    assert c.get("/admin/ai").status_code == 200
    _enable()


def test_admin_provider_encrypts_credentials_without_rendering_them():
    _enable()
    c = login(*ADMIN)
    csrf = csrf_of(c.get("/admin/ai").text)
    result = c.post("/admin/ai/provider", data={
        "csrf": csrf, "name": "Encrypted test instance", "base_url": "https://llm.example.org/api",
        "model_id": "example-model", "text_key": "example-text-test-only",
        "image_key": "example-image-test-only", "active": "1",
    })
    assert result.status_code == 303
    with SessionLocal() as db:
        obj = db.scalar(select(AIProvider).where(AIProvider.name == "Encrypted test instance"))
        assert obj
        assert decrypt(obj.text_key_enc) == "example-text-test-only"
        assert decrypt(obj.image_key_enc) == "example-image-test-only"
        assert "example-text-test-only" not in obj.text_key_enc
    page = c.get("/admin/ai").text
    assert "example-text-test-only" not in page
    assert "example-image-test-only" not in page
    bad = c.post("/admin/ai/provider", data={
        "csrf": csrf, "name": "Invalid", "base_url": "http://localhost:11434",
        "model_id": "bad", "text_key": "example",
    })
    assert bad.status_code == 400


def test_user_chat_persistence_and_cross_account_isolation(monkeypatch):
    _enable()
    _provider()
    _user("ai-one@example.org")
    _user("ai-two@example.org")

    async def fake_complete(provider, messages, *, image=False, max_tokens=1024):
        assert provider.model_id == "example-model"
        assert messages[-1]["role"] == "user"
        return "Simulierte Antwort ohne Netzwerkzugang."

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    c = login("ai-one@example.org", "passwort-123")
    page = c.get("/ki")
    csrf = csrf_of(page.text)
    assert page.status_code == 200 and "KI-Chat" in page.text
    created = c.post("/ki/new", data={"csrf": csrf})
    assert created.status_code == 303
    url = created.headers["location"]
    assert url.startswith("/ki?chat=")
    chat_id = int(url.split("=")[1])
    sent = c.post(f"/ki/{chat_id}/message", data={
        "csrf": csrf, "message": "Wie geht es dir?",
    })
    assert sent.status_code == 303
    after = c.get(url).text
    assert "Simulierte Antwort ohne Netzwerkzugang." in after
    with SessionLocal() as db:
        items = list(db.scalars(select(AIMessage).where(AIMessage.conversation_id == chat_id)))
        assert [item.role for item in items] == ["user", "assistant"]
    other = login("ai-two@example.org", "passwort-123")
    assert other.get(url).status_code == 404
    assert other.get(f"/ki/{chat_id}/export").status_code == 404
    assert other.post(f"/ki/{chat_id}/delete", data={"csrf": csrf_of(other.get("/ki").text)}).status_code == 404
    exported = c.get(f"/ki/{chat_id}/export")
    assert exported.status_code == 200
    assert exported.json()["messages"][1]["content"] == "Simulierte Antwort ohne Netzwerkzugang."
    delete = c.post(f"/ki/{chat_id}/delete", data={"csrf": csrf})
    assert delete.status_code == 303
    assert c.get(url).status_code == 404


def test_only_opted_in_published_laws_enter_chat_context(monkeypatch):
    _enable()
    _provider()
    _user("ai-law-reader@example.org")
    with SessionLocal() as db:
        law = db.scalar(select(LawText).where(LawText.slug == "ai-test-gebuehrensatzung"))
        if law:
            db.delete(law)
            db.commit()
        law = LawText(title="Test Gebührensatzung", slug="ai-test-gebuehrensatzung", doc_type="satzung",
                      published=True, valid_from="2024-01-01", body_md=(
                          "# Test Gebührensatzung\n\n### § 3 Nutzungsgebühr\n\n"
                          "Für die Nutzung des Test-Grillplatzes beträgt die Gebühr 15 Euro."
                      ))
        db.add(law)
        db.flush()
        laws.store(db, law)
        db.add(AILawSource(law_id=law.id))
        db.commit()
    received = {}

    async def fake_complete(_provider, messages, **kwargs):
        received["messages"] = messages
        return "Die Regelung steht in [Quelle 1]."

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    c = login("ai-law-reader@example.org", "passwort-123")
    csrf = csrf_of(c.get("/ki").text)
    created = c.post("/ki/new", data={"csrf": csrf})
    chat_id = int(created.headers["location"].split("=")[1])
    sent = c.post(f"/ki/{chat_id}/message", data={
        "csrf": csrf, "message": "Was sagt die Test Gebührensatzung zur Nutzungsgebühr?",
        "use_knowledge": "1",
    })
    assert sent.status_code == 303
    prompt = json.dumps(received["messages"], ensure_ascii=False)
    assert "§ 3" in prompt and "15 Euro" in prompt
    assert "/recht/ai-test-gebuehrensatzung" in c.get(f"/ki?chat={chat_id}").text


def test_no_knowledge_permission_leaks_into_context(monkeypatch):
    _enable()
    pid = _provider()
    uid = _user("ai-no-knowledge@example.org")
    with SessionLocal() as db:
        db.get(User, uid).permissions = "ai_chat"
        db.add(AIKnowledge(title="Vertraulicher Testeintrag",
                           body_md="Nur für Wissensberechtigte: DEKOR-123", enabled=True))
        db.commit()
    seen = {}

    async def fake_complete(_p, messages, **kwargs):
        seen["messages"] = messages
        return "Fertig."

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    c = login("ai-no-knowledge@example.org", "passwort-123")
    csrf = csrf_of(c.get("/ki").text)
    url = c.post("/ki/new", data={"csrf": csrf, "provider_id": pid}).headers["location"]
    chat_id = int(url.split("=")[1])
    c.post(f"/ki/{chat_id}/message", data={
        "csrf": csrf, "message": "DEKOR-123", "use_knowledge": "1",
    })
    assert "Vertraulicher Testeintrag" not in json.dumps(seen["messages"])
    assert "DEKOR-123" in json.dumps(seen["messages"])  # user's own question remains


def test_openai_adapter_path_preserves_api_prefix():
    assert ai_provider.endpoint("https://llm.example.org/api", "chat/completions") == (
        "https://llm.example.org/api/chat/completions"
    )
    assert ai_provider.endpoint("https://llm.example.org/api/", "models") == (
        "https://llm.example.org/api/models"
    )


def test_image_upload_rejects_unknown_payload():
    from fastapi import HTTPException
    from app.routes_ai import _image_data
    import pytest
    with pytest.raises(HTTPException):
        _image_data(b"not an image")


def test_openai_adapter_non_streaming_parses_response(monkeypatch):
    from types import SimpleNamespace
    provider = SimpleNamespace(model_id="example-model", text_key_enc="dummy",
                               image_key_enc="other-dummy")

    async def fake_request(p, operation, key_enc, *, payload=None):
        assert p is provider
        assert operation == "chat/completions"
        assert key_enc == "dummy"
        assert payload["stream"] is False and payload["model"] == "example-model"
        return {"choices": [{"message": {"content": "VERBUNDEN"}}]}

    monkeypatch.setattr(ai_provider, "_request", fake_request)
    result = asyncio.run(ai_provider.complete(provider, [{"role": "user", "content": "Test"}]))
    assert result == "VERBUNDEN"


def test_chat_retention_deletes_expired_data():
    from datetime import timedelta
    from app import ai_lifecycle
    from app.db import utcnow

    _enable()
    uid = _user("ai-old-chat@example.org")
    with SessionLocal() as db:
        old = AIConversation(owner_id=uid, title="Zu alt", updated_at=utcnow() - timedelta(days=400))
        db.add(old)
        db.flush()
        cid = old.id
        db.add(AIMessage(conversation_id=cid, role="user", content="Testdaten"))
        db.commit()
    settings(ai_retention_days="30")
    assert ai_lifecycle.purge_expired() >= 1
    with SessionLocal() as db:
        assert db.get(AIConversation, cid) is None
        assert db.scalar(select(AIMessage.id).where(AIMessage.conversation_id == cid)) is None


def test_image_part_format_is_compatible():
    import io
    from PIL import Image
    from app.routes_ai import _image_data
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 0, 0)).save(stream, format="PNG")
    uri = _image_data(stream.getvalue())
    assert uri.startswith("data:image/png;base64,")
