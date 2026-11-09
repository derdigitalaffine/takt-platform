"""Explicit public web search: rights, safe citations and no silent egress."""
import json

from sqlalchemy import select

from app import ai_provider, ai_web
from app.ai_models import AIProvider, AIMessage
from app.db import SessionLocal, User
from app.security import decrypt
from conftest import csrf_of, login, settings


def test_search_url_filters_untrusted_results():
    assert ai_web.public_url("https://www.example.org/satzung?q=1")
    assert not ai_web.public_url("http://www.example.org/")
    assert not ai_web.public_url("javascript:alert(1)")
    assert not ai_web.public_url("https://127.0.0.1/admin")
    assert not ai_web.public_url("https://localhost/")
    assert not ai_web.public_url("https://foo.local/")
    assert not ai_web.public_url("https://evil.com\\@localhost/")


def _setup():
    settings(module_ai="1", ai_web_enabled="0")
    with SessionLocal() as db:
        p = AIProvider(name="Public Search Test Provider", model_id="test-chat",
                       base_url="https://llm.example.org/api", active=True)
        db.add(p)
        db.commit()
        return p.id


def test_search_disabled_without_optin_and_admin_key_is_encrypted(monkeypatch):
    pid = _setup()
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/admin/ai").text)
    created = client.post("/ki/new", data={"csrf": csrf, "provider_id": pid})
    cid = int(created.headers["location"].split("=")[1])
    assert 'name="use_web"' not in client.get(f"/ki?chat={cid}").text

    seen = {}
    async def fake_complete(provider, messages, **kwargs):
        seen["messages"] = messages
        return "Ohne Websuche."
    async def must_not_search(*args, **kwargs):
        raise AssertionError("No search without explicit checkbox")
    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    monkeypatch.setattr(ai_web, "search", must_not_search)
    response = client.post(f"/ki/{cid}/message", data={"csrf": csrf, "message": "Eine Frage"})
    assert response.status_code == 303
    assert "Ohne Websuche" in client.get(f"/ki?chat={cid}").text

    response = client.post("/admin/ai/web/settings", data={
        "csrf": csrf, "enabled": "1", "api_key": "web-test-secret-only"
    })
    assert response.status_code == 303
    with SessionLocal() as db:
        from app.db import get_settings
        cfg = get_settings(db)
        assert cfg["ai_web_enabled"] == "1"
        assert decrypt(cfg["ai_web_key_enc"]) == "web-test-secret-only"
        assert "web-test-secret-only" not in client.get("/admin/ai").text
    assert 'name="use_web"' in client.get(f"/ki?chat={cid}").text


def test_web_sources_cited_in_stream_and_revoked_on_disable(monkeypatch):
    pid = _setup()
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/admin/ai").text)
    client.post("/admin/ai/web/settings", data={
        "csrf": csrf, "enabled": "1", "api_key": "web-test-secret-only"
    })
    seen = {}

    async def search(_db, user, query, limit=4):
        seen["query"] = query
        return [{"title": "Öffentliche Quelle", "url": "https://example.org/news",
                 "kind": "web", "text": "Aktueller Bericht"}]

    async def complete(provider, messages, **kwargs):
        seen["messages"] = messages
        return "Laut [Quelle 1] liegt ein Bericht vor."

    monkeypatch.setattr(ai_web, "search", search)
    monkeypatch.setattr(ai_provider, "complete", complete)
    created = client.post("/ki/new", data={"csrf": csrf, "provider_id": pid})
    cid = int(created.headers["location"].split("=")[1])
    response = client.post(f"/ki/{cid}/message/updates", data={
        "csrf": csrf, "message": "Was ist aktuell?", "use_web": "1"
    })
    assert response.status_code == 200
    assert 'event: done' in response.text
    assert '"kind": "web"' in response.text
    assert seen["query"] == "Was ist aktuell?"
    assert "Aktueller Bericht" in json.dumps(seen["messages"], ensure_ascii=False)
    with SessionLocal() as db:
        row = db.scalar(select(AIMessage).where(
            AIMessage.conversation_id == cid, AIMessage.role == "assistant"))
        assert row
        assert '"kind": "web"' in row.sources_json
    assert "Öffentliche Quelle" in client.get(f"/ki?chat={cid}").text

    # Turning off web search revokes access to previously stored web-grounded answers.
    settings(ai_web_enabled="0")
    html = client.get(f"/ki?chat={cid}").text
    assert "Antwort aufgrund geänderter Wissensrechte ausgeblendet" in html
    assert "Laut [Quelle 1]" not in html


def test_web_search_requires_an_explicit_user_permission(monkeypatch):
    pid = _setup()
    admin = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(admin.get("/admin/ai").text)
    admin.post("/admin/ai/web/settings", data={
        "csrf": csrf, "enabled": "1", "api_key": "web-test-secret-only"
    })
    from app.security import hash_password
    with SessionLocal() as db:
        db.add(User(email="no-web-access@example.org", name="No web",
                    password_hash=hash_password("passwort-123"), permissions="ai_chat",
                    active=True, must_change_password=False))
        db.commit()
    client = login("no-web-access@example.org", "passwort-123")
    csrf2 = csrf_of(client.get("/ki").text)
    cid = int(client.post("/ki/new", data={"csrf": csrf2, "provider_id": pid})
              .headers["location"].split("=")[1])
    assert 'name="use_web"' not in client.get(f"/ki?chat={cid}").text
    resp = client.post(f"/ki/{cid}/message/updates", data={
        "csrf": csrf2, "message": "Test", "use_web": "1"
    })
    assert resp.status_code == 403
