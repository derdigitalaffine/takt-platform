"""Regression coverage for the inline AI chat interface."""
from pathlib import Path
from sqlalchemy import select

from app.ai_models import AIProvider
from app.db import SessionLocal
from conftest import csrf_of, login, settings

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_chat_page_contains_inline_streaming_controls():
    settings(module_ai="1")
    with SessionLocal() as db:
        provider = db.scalar(select(AIProvider).where(AIProvider.name == "UI streaming test provider"))
        if provider is None:
            provider = AIProvider(
                name="UI streaming test provider",
                base_url="https://llm.example.org/api",
                model_id="ui-test-model",
            )
            db.add(provider)
        provider.active = True
        db.commit()
        provider_id = provider.id

    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/ki").text)
    created = client.post("/ki/new", data={"csrf": csrf, "provider_id": provider_id})
    assert created.status_code == 303
    page = client.get(created.headers["location"])
    assert page.status_code == 200
    html = page.text
    assert 'data-ai-messages' in html
    assert 'data-ai-scroll-area' in html
    assert 'data-ai-current-link' in html
    assert 'data-ai-chat-title' in html
    assert 'data-ai-chat-form' in html
    assert 'data-stream-action=' in html
    assert 'data-ai-stop' in html
    assert 'data-ai-jump' in html
    assert 'data-ai-has-messages="0"' in html
    assert 'data-ai-workspace' in html
    assert 'ai-chat-options' in html
    assert 'aria-label="Nachricht senden"' in html
    assert '/static/ai-chat.css' in html
    assert '/static/ai-chat.js' in html
    assert 'data-ai-live' not in html


def test_chat_client_keeps_safe_incremental_output_without_reload():
    js = (APP_DIR / "static" / "ai-chat.js").read_text(encoding="utf-8")
    css = (APP_DIR / "static" / "ai-chat.css").read_text(encoding="utf-8")
    assert "document.createTextNode(chunk)" in js
    assert "new FormData(form)" in js
    assert "new URL(source.url, window.location.origin)" in js
    # User must explicitly click the link. No automatic navigation in the agent.
    assert "window.location.assign(data.open_url)" not in js
    assert "parent.location.assign(data.open_url)" not in js
    assert "link.href = data.open_url" in js
    assert "link.target = '_top'" in js
    assert "data.open_url.includes" in js
    assert "eventData.kind === 'render'" in js
    assert "assistantBubble.content.innerHTML = eventData.value.html" in js
    assert "assistantBubble.content.innerHTML = doneData.html" in js
    assert "window.addEventListener('resize', resizeWorkspace)" in js
    assert "data-ai-workspace" in js
    assert "Only Markdown HTML generated" in js
    assert "ai-message--streaming" in js
    assert "data-ai-current-link" in js
    assert ".ai-chat-history" in css
    assert ".ai-chat-composer" in css
    assert "body:has([data-ai-workspace]) { overflow: hidden; }" in css
    assert "height: auto; min-height: 0;" in css
    assert ".ai-message-markdown" in css
    assert "@media (max-width: 767.98px)" in css
