"""Conversational agent routing, safe action mode, links and responsive chat UX."""
import json
from pathlib import Path

import pytest
from sqlalchemy import select, func

from app import ai_provider, agent_precision
from app.ai_models import AIProvider, AIMessage, AIConversation
from app.db import SessionLocal, get_settings, set_setting
from conftest import csrf_of, login, settings


@pytest.fixture(autouse=True)
def enabled_agent():
    keys = ("module_ai", "module_tasks", "module_anliegen", "ai_knowledge_enabled")
    with SessionLocal() as db:
        old = {key: get_settings(db)[key] for key in keys}
    settings(module_ai="1", module_tasks="1", module_anliegen="1", ai_knowledge_enabled="0")
    with SessionLocal() as db:
        provider = AIProvider(
            name="Intent UX test", base_url="https://llm.example.org/v1",
            model_id="fake-intent-model", active=True,
        )
        db.add(provider)
        db.commit()
        provider_id = provider.id
    yield provider_id
    with SessionLocal() as db:
        # Keep test-created conversations referentially safe until their own
        # cleanup, but remove unused provider credentials and settings.
        for key, val in old.items():
            set_setting(db, key, val)
        row = db.get(AIProvider, provider_id)
        if row and not db.scalar(select(AIConversation.id).where(
                AIConversation.provider_id == provider_id).limit(1)):
            db.delete(row)
        db.commit()


@pytest.mark.parametrize("question", [
    "was ist heilifenosmchel?", "was ist ?", "Was ist eine Aufgabe?",
    "Warum gibt es einen Kalender in TAKT?", "Wie funktioniert ein Formular?",
    "Erkläre mir bitte, was ein Prozess ist.",
])
def test_questions_never_enter_json_tool_planner(question):
    assert not agent_precision.needs_tools(question)


@pytest.mark.parametrize("request", [
    "Lege die Aufgabe Drucker prüfen an",
    "Erfasse eine vertrauliche Beschwerde wegen Mobbing",
    "Zeige meine offenen Aufgaben",
    "Öffne das Formularmodul",
    "Bitte die Schritte vorbereiten",
])
def test_explicit_operations_still_enter_tool_planner(request):
    assert agent_precision.needs_tools(request)


def test_plain_questions_accept_natural_model_answer_without_json(monkeypatch):
    calls = []

    async def respond(provider, messages, *, image=False, max_tokens=1024):
        calls.append(messages)
        return "Das Wort kenne ich nicht. Kannst du es genauer beschreiben?"

    monkeypatch.setattr(ai_provider, "complete", respond)
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/agent").text)
    with SessionLocal() as db:
        before = db.scalar(select(func.count(AIMessage.id)))
    for prompt in ("was ist heilifenosmchel?", "was ist ?"):
        response = client.post("/agent/plan", data={"csrf": csrf, "prompt": prompt})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["intent"] == "chat"
        assert "Das Wort kenne ich nicht" in payload["message"]
        assert payload["proposals"] == []
        assert payload["open_url"] == ""
        assert payload["plan_id"] == ""
        assert "html" in payload
    assert len(calls) == 2  # One provider call, no JSON planning stage.
    assert all(any("Sprich die Person immer mit du" in m["content"] for m in call
                   if m["role"] == "system") for call in calls)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AIMessage.id))) == before


def test_tool_planner_with_non_json_response_fails_friendly_and_never_mutates(monkeypatch):
    responses = iter(['Kein JSON für die Suche.',
                      'Sorry, ich habe keinen sicheren Vorschlag.'])

    async def respond(provider, messages, *, image=False, max_tokens=1024):
        return next(responses)

    monkeypatch.setattr(ai_provider, "complete", respond)
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/agent").text)
    result = client.post("/agent/plan", data={
        "csrf": csrf, "prompt": "Lege die Aufgabe Agentenmodus-Prüfung an",
    })
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["intent"] == "action"
    assert "noch nichts gespeichert" in payload["message"]
    assert not payload["proposals"] and not payload["plan_id"]


def test_module_navigation_is_only_a_safe_optional_link(monkeypatch):
    responses = iter([
        json.dumps({"searches": []}),
        json.dumps({"message": "Ich kann dich zu deinen Aufgaben führen.",
                    "actions": []}),
    ])

    async def respond(provider, messages, *, image=False, max_tokens=1024):
        return next(responses)

    monkeypatch.setattr(ai_provider, "complete", respond)
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/agent").text)
    result = client.post("/agent/plan", data={
        "csrf": csrf, "prompt": "Öffne meine Aufgaben",
    })
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["intent"] == "action"
    assert payload["open_url"] == "/aufgaben"
    assert payload["proposals"] == []
    assert agent_precision.navigation_link(None, "was sind Aufgaben?") == ""


def test_chat_window_has_typing_font_control_and_no_auto_navigation(enabled_agent):
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/agent").text)
    created = client.post("/agent/new", data={
        "csrf": csrf, "provider_id": enabled_agent,
    })
    assert created.status_code == 303, created.text
    page = client.get(created.headers["location"])
    assert page.status_code == 200
    assert "data-ai-font-size" in page.text
    assert "Du</div>" in page.text or 'name="use_agent"' in page.text
    assert "Bei Aufgaben in TAKT helfen" in page.text
    root = Path(__file__).resolve().parents[1] / "app" / "static"
    js = (root / "ai-chat.js").read_text(encoding="utf-8")
    css = (root / "ai-chat.css").read_text(encoding="utf-8")
    dock = (root / "agent.css").read_text(encoding="utf-8")
    assert "ai-typing-dots" in js and "ai-typing-dots" in css
    assert "takt-agent-font-size" in js
    assert "data-ai-font-size" in js
    assert "link.href = data.open_url" in js
    assert "link.target = '_top'" in js
    assert "window.location.assign(data.open_url)" not in js
    assert "parent.location.assign(data.open_url)" not in js
    assert "--ai-chat-text-size" in css and "--ai-chat-text-size" in dock
