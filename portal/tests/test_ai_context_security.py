"""Revoked knowledge must not leak through invisible chat history or SSE metadata."""
import json

from sqlalchemy import select

from app import ai_knowledge, ai_provider
from app.ai_models import AIConversation, AIKnowledge, AIMessage, AIProvider
from app.db import SessionLocal
from app.routes_ai import _model_history, _MAX_CONTEXT_CHARS
from conftest import csrf_of, login, settings


def _setup(stream=False):
    settings(module_ai="1", ai_knowledge_enabled="1")
    with SessionLocal() as db:
        provider = AIProvider(
            name="Context source safety test", model_id="fake-model",
            base_url="https://llm.example.org/api", active=True,
            stream_enabled=stream,
        )
        source = AIKnowledge(title="Confidential test source",
                             body_md="Never resend this source-backed answer.", enabled=True)
        db.add_all([provider, source])
        db.commit()
        return provider.id, source.id


def _conversation(client, provider_id, csrf):
    response = client.post("/ki/new", data={"csrf": csrf, "provider_id": provider_id})
    assert response.status_code == 303
    return int(response.headers["location"].split("=")[1])


def _seed_source_reply(chat_id, source_id):
    with SessionLocal() as db:
        source = db.get(AIKnowledge, source_id)
        db.add(AIMessage(conversation_id=chat_id, role="user", content="Previous request"))
        db.add(AIMessage(
            conversation_id=chat_id, role="assistant",
            content="Confidential model answer 45e6ac",
            sources_json=json.dumps([{
                "title": source.title,
                "url": f"/ki/wissen/{source.id}",
                "revision": ai_knowledge.knowledge_revision(source),
            }]),
            model_id="fake-model",
        ))
        db.commit()
        source.body_md = "Changed source: previous answer is no longer valid"
        db.commit()


def test_revoked_citation_hidden_from_plain_chat_and_next_model_context(monkeypatch):
    pid, source_id = _setup()
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/ki").text)
    chat_id = _conversation(client, pid, csrf)
    _seed_source_reply(chat_id, source_id)
    seen = {}

    async def fake_complete(provider, messages, **kwargs):
        seen["messages"] = messages
        return "Fresh answer"

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    page = client.get(f"/ki?chat={chat_id}")
    assert "Confidential model answer 45e6ac" not in page.text
    response = client.post(
        f"/ki/{chat_id}/message", data={"csrf": csrf, "message": "Please continue"},
    )
    assert response.status_code == 303
    payload = json.dumps(seen["messages"])
    assert "Confidential model answer 45e6ac" not in payload
    assert "Previous request" in payload
    assert "Please continue" in payload


def test_revoked_citation_never_enters_streamed_model_context(monkeypatch):
    pid, source_id = _setup(stream=True)
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/ki").text)
    chat_id = _conversation(client, pid, csrf)
    _seed_source_reply(chat_id, source_id)
    seen = {}

    async def fake_stream(provider, messages, **kwargs):
        seen["messages"] = messages
        yield "Streaming fresh answer"

    monkeypatch.setattr(ai_provider, "stream_completion", fake_stream)
    response = client.post(
        f"/ki/{chat_id}/message/updates",
        data={"csrf": csrf, "message": "Stream please"},
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    assert "Confidential model answer 45e6ac" not in json.dumps(seen["messages"])


def test_streamed_citations_include_revision_and_revoke_on_edits(monkeypatch):
    pid, source_id = _setup(stream=True)
    client = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(client.get("/ki").text)
    chat_id = _conversation(client, pid, csrf)

    async def fake_stream(provider, messages, **kwargs):
        yield "Answer supported by knowledge."

    monkeypatch.setattr(ai_provider, "stream_completion", fake_stream)
    resp = client.post(
        f"/ki/{chat_id}/message/updates",
        data={"csrf": csrf, "message": "Confidential test source",
              "use_knowledge": "1"},
    )
    assert resp.status_code == 200
    with SessionLocal() as db:
        latest = db.scalar(select(AIMessage).where(
            AIMessage.conversation_id == chat_id,
            AIMessage.role == "assistant",
        ).order_by(AIMessage.id.desc()))
        assert latest is not None
        citations = json.loads(latest.sources_json)
        citation = next(source for source in citations
                        if source["url"] == f"/ki/wissen/{source_id}")
        assert len(citation["revision"]) == 64
        db.get(AIKnowledge, source_id).body_md = "A different text"
        db.commit()
    assert "Answer supported by knowledge." not in client.get(f"/ki?chat={chat_id}").text


def test_long_context_is_bounded_and_not_silently_truncated():
    pid, source_id = _setup()
    with SessionLocal() as db:
        provider = db.get(AIProvider, pid)
        source = db.get(AIKnowledge, source_id)
        row1 = AIMessage(role="user", content="old" * 1000)
        row2 = AIMessage(role="assistant", content="x" * (_MAX_CONTEXT_CHARS + 1),
                         sources_json="[]")
        row3 = AIMessage(role="user", content="recent safe question")
        result = _model_history(db, type("Allowed", (), {"can": lambda self, p: True})(),
                                [row1, row2, row3])
        assert result == [{"role": "user", "content": "recent safe question"}]
        assert sum(len(item["content"]) for item in result) <= _MAX_CONTEXT_CHARS
