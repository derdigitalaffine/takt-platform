"""SearXNG infrastructure opt-in, provider choice, output safety and setup reruns."""
import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from app import ai_web
from app.db import SessionLocal, get_settings, User
from conftest import csrf_of, login, settings


def test_searxng_requires_setup_and_ai_rights(monkeypatch):
    settings(module_ai="1", ai_web_enabled="1", ai_web_provider="searxng",
             ai_web_key_enc="")
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == "admin@example.org").one()
        monkeypatch.delenv("TAKT_SEARXNG_ENABLED", raising=False)
        assert not ai_web.available(db, admin)
        monkeypatch.setenv("TAKT_SEARXNG_ENABLED", "1")
        assert ai_web.available(db, admin)
        settings(ai_web_enabled="0")
        db.expire_all()
        assert not ai_web.available(db, admin)


def test_provider_choice_never_silently_falls_back(monkeypatch):
    monkeypatch.setenv("TAKT_SEARXNG_ENABLED", "1")
    assert ai_web.selected_provider({"ai_web_provider": "auto"}) == "searxng"
    assert ai_web.selected_provider({"ai_web_provider": "brave",
                                    "ai_web_key_enc": ""}) is None
    assert ai_web.selected_provider({"ai_web_provider": "searxng",
                                    "ai_web_key_enc": "secret"}) == "searxng"
    monkeypatch.delenv("TAKT_SEARXNG_ENABLED")
    assert ai_web.selected_provider({"ai_web_provider": "auto",
                                    "ai_web_key_enc": "encrypted"}) == "brave"
    assert ai_web.selected_provider({"ai_web_provider": "searxng",
                                    "ai_web_key_enc": "encrypted"}) is None


def test_searxng_returns_only_safe_unique_https_sources(monkeypatch):
    settings(module_ai="1", ai_web_enabled="1", ai_web_provider="searxng")
    monkeypatch.setenv("TAKT_SEARXNG_ENABLED", "1")
    captured = {}

    class Response:
        status_code = 200
        headers = {"content-type": "application/json; charset=utf-8"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_bytes(self):
            payload = {"results": [
                {"title": "Öffentlicher Bericht", "url": "https://example.org/bericht",
                 "content": "Ein Bericht"},
                {"title": "Doppelt", "url": "https://example.org/bericht",
                 "content": "Doppelt"},
                {"title": "Intern", "url": "http://searxng:8080/admin",
                 "content": "Vertraulich"},
                {"title": "Lokal", "url": "https://127.0.0.1/private",
                 "content": "Vertraulich"},
                {"title": "Zweite Quelle", "url": "https://example.net/weiter",
                 "content": "Weitere Information"},
            ]}
            yield json.dumps(payload).encode()

    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, *, params, headers):
            captured.update(method=method, url=url, params=params, headers=headers)
            return Response()

    monkeypatch.setattr(ai_web.httpx, "AsyncClient", Client)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == "admin@example.org").one()
        result = asyncio.run(ai_web.search(db, admin, "Wo ist der Bericht?"))
    assert [entry["title"] for entry in result] == [
        "Öffentlicher Bericht", "Zweite Quelle"
    ]
    assert all(entry["kind"] == "web" for entry in result)
    assert captured["url"] == "http://searxng:8080/search"
    assert captured["params"]["format"] == "json"
    assert captured["client"]["trust_env"] is False
    assert captured["client"]["follow_redirects"] is False
    assert "X-Subscription-Token" not in captured["headers"]


def test_ai_admin_accepts_keyless_searxng_only_when_enabled(monkeypatch):
    settings(module_ai="1", ai_web_enabled="0", ai_web_provider="auto",
             ai_web_key_enc="")
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/admin/ai").text)
    monkeypatch.delenv("TAKT_SEARXNG_ENABLED", raising=False)
    response = client.post("/admin/ai/web/settings", data={
        "csrf": csrf, "enabled": "1", "provider": "searxng"
    })
    assert response.status_code == 400
    monkeypatch.setenv("TAKT_SEARXNG_ENABLED", "1")
    response = client.post("/admin/ai/web/settings", data={
        "csrf": csrf, "enabled": "1", "provider": "searxng"
    })
    assert response.status_code == 303
    with SessionLocal() as db:
        cfg = get_settings(db)
        assert cfg["ai_web_provider"] == "searxng"
        assert cfg["ai_web_enabled"] == "1"
    assert "SearXNG" in client.get("/admin/ai").text


def test_setup_can_activate_and_deactivate_without_rotating_other_secrets(tmp_path):
    # Rerunning the *real* setup script on a minimal existing deployment.
    root = Path(__file__).resolve().parents[2]
    setup = root / "scripts" / "setup.sh"
    assert setup.exists()
    app = tmp_path / "app"
    (app / "scripts").mkdir(parents=True)
    target = app / "scripts" / "setup.sh"
    target.write_text(setup.read_text())
    env = app / ".env"
    env.write_text("PORTAL_SECRET_KEY=original-secret\n"
                   "PORTAL_ADMIN_PASSWORD=original-password\n"
                   "COMPOSE_PROFILES=rag\nSEARXNG_ENABLED=0\nSEARXNG_SECRET=\n")

    def run(flag):
        result = subprocess.run(["bash", str(target), flag], cwd=app,
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        return env.read_text()

    first = run("--enable-searxng")
    assert "COMPOSE_PROFILES=rag,searxng" in first
    assert "PORTAL_SECRET_KEY=original-secret" in first
    assert "PORTAL_ADMIN_PASSWORD=original-password" in first
    secret = [s for s in first.splitlines() if s.startswith("SEARXNG_SECRET=")][0]
    assert len(secret.split("=", 1)[1]) >= 32
    assert run("--enable-searxng") == first
    disabled = run("--disable-searxng")
    assert "COMPOSE_PROFILES=rag\n" in disabled
    assert "SEARXNG_ENABLED=0" in disabled
    assert secret in disabled
    assert run("--disable-searxng") == disabled
