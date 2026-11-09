"""Owner-scoped chat branches and per-chat model choice retain original history."""
import json

from sqlalchemy import select

from app import ai_provider, ai_knowledge
from app.ai_models import AIConversation, AIMessage, AIProvider, AIKnowledge
from app.db import SessionLocal, User
from app.security import hash_password
from conftest import csrf_of, login, settings


def _setup():
    settings(module_ai="1", ai_knowledge_enabled="1")
    with SessionLocal() as db:
        first = AIProvider(name="Branch Model A", base_url="https://llm.example.org/api",
                           model_id="model-a", active=True)
        next_one = AIProvider(name="Branch Model B", base_url="https://llm.example.org/api",
                              model_id="model-b", active=True)
        disabled = AIProvider(name="Disabled Branch Model", base_url="https://llm.example.org/api",
                              model_id="model-disabled", active=False)
        db.add_all([first, next_one, disabled])
        db.commit()
        return first.id, next_one.id, disabled.id


def _conversation(client, csrf, model_id):
    resp = client.post("/ki/new", data={"csrf": csrf, "provider_id": model_id})
    assert resp.status_code == 303
    return int(resp.headers["location"].split("=")[1])


def test_model_change_preserves_past_answers_and_only_affects_future(monkeypatch):
    first, second, disabled = _setup()
    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/ki").text)
    cid = _conversation(c, csrf, first)
    seen = []

    async def fake_complete(provider, messages, **kwargs):
        seen.append(provider.model_id)
        return "Antwort aus " + provider.model_id

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    c.post(f"/ki/{cid}/message", data={"csrf": csrf, "message": "Erste Frage"})
    changed = c.post(f"/ki/{cid}/model", data={"csrf": csrf, "provider_id": second})
    assert changed.status_code == 303
    refused = c.post(f"/ki/{cid}/model", data={"csrf": csrf, "provider_id": disabled})
    assert refused.status_code == 404
    c.post(f"/ki/{cid}/message", data={"csrf": csrf, "message": "Zweite Frage"})
    assert seen == ["model-a", "model-b"]
    page = c.get(f"/ki?chat={cid}").text
    assert 'action="/ki/' + str(cid) + '/model"' in page
    assert "Ab hier verzweigen" in page
    with SessionLocal() as db:
        chat = db.get(AIConversation, cid)
        assert chat.provider_id == second
        answers = list(db.scalars(select(AIMessage).where(
            AIMessage.conversation_id == cid, AIMessage.role == "assistant",
        ).order_by(AIMessage.id)))
        assert [answer.model_id for answer in answers] == ["model-a", "model-b"]


def test_fork_creates_private_independent_history_and_keeps_original():
    first, second, _ = _setup()
    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/ki").text)
    cid = _conversation(c, csrf, first)
    with SessionLocal() as db:
        first_user = AIMessage(conversation_id=cid, role="user", content="The initial question")
        first_reply = AIMessage(conversation_id=cid, role="assistant", content="The answer",
                                sources_json="[]", model_id="model-a")
        last_user = AIMessage(conversation_id=cid, role="user", content="A later question")
        db.add_all([first_user, first_reply, last_user])
        db.commit()
        reply_id, last_id = first_reply.id, last_user.id

    response = c.post(f"/ki/{cid}/fork", data={"csrf": csrf, "message_id": reply_id})
    assert response.status_code == 303
    fork_id = int(response.headers["location"].split("=")[1])
    assert fork_id != cid
    with SessionLocal() as db:
        original = db.get(AIConversation, cid)
        branch = db.get(AIConversation, fork_id)
        assert branch.owner_id == original.owner_id
        assert branch.provider_id == first
        assert [r.content for r in branch.messages] == ["The initial question", "The answer"]
        assert [r.content for r in original.messages] == [
            "The initial question", "The answer", "A later question",
        ]
        branch.messages[0].content = "Independently changed"
        db.commit()
    with SessionLocal() as db:
        assert db.get(AIConversation, cid).messages[0].content == "The initial question"
        assert db.get(AIConversation, fork_id).messages[0].content == "Independently changed"
    foreign = c.post(f"/ki/{fork_id}/fork", data={"csrf": csrf, "message_id": 999999999})
    assert foreign.status_code == 404


def test_cross_user_chat_model_and_fork_are_not_exposed():
    first, second, _ = _setup()
    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/ki").text)
    cid = _conversation(c, csrf, first)
    with SessionLocal() as db:
        message = AIMessage(conversation_id=cid, role="user", content="Private question")
        db.add(message)
        db.add(User(email="fork-other@example.org", name="Other person",
                    password_hash=hash_password("safe-pass-123"),
                    permissions="ai_chat", active=True, must_change_password=False))
        db.commit()
        mid = message.id
    other = login("fork-other@example.org", "safe-pass-123")
    csrf2 = csrf_of(other.get("/ki").text)
    assert other.post(f"/ki/{cid}/model", data={
        "csrf": csrf2, "provider_id": second,
    }).status_code == 404
    assert other.post(f"/ki/{cid}/fork", data={
        "csrf": csrf2, "message_id": mid,
    }).status_code == 404


def test_cannot_clone_old_answer_after_knowledge_revocation():
    first, _, _ = _setup()
    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/ki").text)
    cid = _conversation(c, csrf, first)
    with SessionLocal() as db:
        source = AIKnowledge(title="Branch test knowledge", body_md="Private consent",
                             enabled=True)
        db.add(source)
        db.flush()
        answer = AIMessage(conversation_id=cid, role="assistant", content="Contains knowledge",
                           sources_json=json.dumps([{
                               "title": source.title,
                               "url": f"/ki/wissen/{source.id}",
                               "revision": ai_knowledge.knowledge_revision(source),
                           }]), model_id="model-a")
        db.add(answer)
        db.commit()
        mid = answer.id
        source.enabled = False
        db.commit()
    denied = c.post(f"/ki/{cid}/fork", data={"csrf": csrf, "message_id": mid})
    assert denied.status_code == 409
    with SessionLocal() as db:
        assert len(list(db.scalars(select(AIConversation).where(
            AIConversation.owner_id == db.scalar(select(User.id).where(
                User.email == "admin@example.org"
            )),
        )))) >= 1  # Original remains after rejected fork.
