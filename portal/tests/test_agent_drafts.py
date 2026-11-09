"""Native handoff and central chat: authority, edited preview and one-shot writes."""
import json
import re
import pytest
from sqlalchemy import select
from app import agent, ai_provider, main, tasks, anliegen
from app.ai_models import AIProvider, AIConversation, AIMessage, AgentAudit
from app.anliegen_models import AnliegenCategory, Anliegen
from app.db import SessionLocal, User, Form, DmsRecord
from app.task_models import Task
from conftest import login, csrf_of
from test_agent_modules import isolated, seed, fake, plan, new_event, ADMIN
from test_agent import _member


def final_tokens(html):
    return {key: re.search(r'name="' + key + r'" value="([^"]+)"', html).group(1) for key in ("csrf", "plan_id", "review_id")}


def test_edited_native_form_requires_final_confirmation_and_cannot_replay(monkeypatch):
    fake(monkeypatch, [], [dict(tool="create_task", title="Agent Entwurf", description="Beschreibung", priority="normal")])
    c = login(*ADMIN); response, csrf = plan(c)
    assert response.status_code == 200, response.text
    assert response.json()["open_url"].startswith("/aufgaben/neu?agent_plan=")
    pid = response.json()["plan_id"]
    detail = c.get("/agent/draft", params=dict(plan_id=pid))
    assert detail.status_code == 200 and detail.json()["fields"]["title"] == "Agent Entwurf"
    review = c.post("/agent/draft/review", data=dict(csrf=csrf, agent_plan=pid, agent_step=0,
                    title="Von Person korrigiert", description="Manuell ergänzte Angaben", priority="high"))
    assert review.status_code == 200, review.text
    assert "Von Person korrigiert" in review.text and "Manuell ergänzte Angaben" in review.text
    with SessionLocal() as db:
        assert db.scalar(select(Task).where(Task.title == "Von Person korrigiert")) is None
    assert c.post("/agent/execute", data=dict(csrf=csrf, plan_id=pid)).status_code == 409
    # The incompatible legacy confirmation consumes the original plan; regenerate it.
    fake(monkeypatch, [], [dict(tool="create_task", title="Agent Entwurf", description="Beschreibung", priority="normal")])
    response, csrf = plan(c); pid = response.json()["plan_id"]
    review = c.post("/agent/draft/review", data=dict(csrf=csrf, agent_plan=pid, agent_step=0,
                    title="Von Person korrigiert", description="Manuell ergänzte Angaben", priority="high"))
    tokens = final_tokens(review.text)
    saved = c.post("/agent/draft/save", data=tokens)
    assert saved.status_code == 303, saved.text
    assert c.post("/agent/draft/save", data=tokens).status_code == 409
    with SessionLocal() as db:
        row = db.scalar(select(Task).where(Task.title == "Von Person korrigiert"))
        assert row and row.priority == "high"
        assert db.scalar(select(AgentAudit).where(AgentAudit.target_id == row.id, AgentAudit.tool == "create_task"))


def test_every_existing_write_tool_has_authorized_native_handoff(monkeypatch):
    uid, cid, fid, rid, src, dest = seed()
    with SessionLocal() as db:
        actor = db.get(User, uid)
        task = tasks.create(db, actor, dict(title="Handoff Aufgabe", assignee_id=uid))
        cat = db.scalar(select(AnliegenCategory).where(AnliegenCategory.enabled.is_(True), AnliegenCategory.confidential.is_(False)))
        case = anliegen.create(db, actor, cat, "Handoff Anliegen", "Beschreibung für den Vorschlag")
        case.assignee_id = uid; case.status = "open"; db.commit()
        tid, aid, catid = task.id, case.id, cat.id
        findings = [dict(type=t, id=i) for t, i in (("task", tid), ("anliegen", aid), ("person", uid), ("calendar", cid), ("form", fid), ("dms", rid), ("dms_area", dest), ("anliegen_category", catid))]
        actions = [dict(tool="create_task", title="Neue Übergabe", description="Ausgefüllter Vorschlag"),
                   dict(tool="create_anliegen", category_id=catid, title="Neues Anliegen", description="Ausgefüllte Beschreibung"),
                   dict(tool="assign_task", id=tid, assignee_id=uid), dict(tool="set_task_priority", id=tid, priority="high"),
                   dict(tool="set_task_status", id=tid, status="in_progress"),
                   dict(tool="assign_anliegen", id=aid, assignee_id=uid), dict(tool="set_anliegen_status", id=aid, status="in_progress"),
                   new_event(cid), dict(tool="copy_form", id=fid), dict(tool="move_dms", id=rid, area_id=dest),
                   dict(tool="configure_anliegen_category", id=catid, title=cat.title, routing=cat.routing, assignee_id=uid, enabled=True)]
        from app import agent_drafts
        for raw in actions:
            action = agent.normalize_plan(json.dumps(dict(actions=[raw])), actor, findings, agent.categories_for(db, actor), db)["actions"][0]
            data = agent_drafts.view(db, actor, dict(actions=[action]), 0)
            assert data["tool"] == raw["tool"] and data["preview"]
            assert data["path"].startswith(("/aufgaben", "/anliegen", "/kalender", "/forms", "/dms"))


def test_multi_step_handoff_rotates_nonce_and_saves_only_confirmed_step(monkeypatch):
    _, cid, fid, rid, src, dest = seed()
    fake(monkeypatch, [dict(tool=t, query="Agent") for t in ("search_forms", "search_dms", "search_dms_areas")],
         [dict(tool="copy_form", id=fid), dict(tool="move_dms", id=rid, area_id=dest)])
    c = login(*ADMIN); response, csrf = plan(c); old = response.json()["plan_id"]
    review = c.post("/agent/draft/review", data=dict(csrf=csrf, agent_plan=old, agent_step=0))
    assert review.status_code == 200, review.text
    result = c.post("/agent/draft/save", data=final_tokens(review.text))
    assert result.status_code == 303 and result.headers["location"].startswith(f"/dms/r/{rid}?")
    assert old not in result.headers["location"]
    assert c.get("/agent/draft", params=dict(plan_id=old)).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Form).where(Form.title == "Agent Formular (Kopie)"))
        assert db.get(DmsRecord, rid).area_id == src


def test_native_handoff_is_csrf_session_bound_and_revalidates_rights(monkeypatch):
    _, _, fid, _, _, _ = seed()
    fake(monkeypatch, [dict(tool="search_forms", query="Agent")], [dict(tool="copy_form", id=fid)])
    c = login(*ADMIN); response, csrf = plan(c); pid = response.json()["plan_id"]
    assert c.get("/agent/draft", params=dict(plan_id="ungültig")).status_code == 409
    other = login(*ADMIN)
    assert other.get("/agent/draft", params=dict(plan_id=pid)).status_code == 409
    assert c.post("/agent/draft/review", data=dict(agent_plan=pid)).status_code == 400
    review = c.post("/agent/draft/review", data=dict(csrf=csrf, agent_plan=pid, agent_step=0))
    with SessionLocal() as db:
        db.get(Form, fid).archived_at = __import__('datetime').datetime(2026, 11, 9); db.commit()
    assert c.post("/agent/draft/save", data=final_tokens(review.text)).status_code == 403


def test_central_chat_retains_conversation_and_filters_revoked_module_history(monkeypatch):
    uid = _member("central-agent@example.org")
    with SessionLocal() as db:
        db.get(User, uid).permissions = "ai_chat,tasks"; db.commit()
        row = tasks.create(db, db.get(User, uid), dict(title="Modulgeheimnis", assignee_id=uid)); db.commit(); tid = row.id
    c = login("central-agent@example.org", "agent-passwort-123")
    csrf = csrf_of(c.get("/agent").text)
    new = c.post("/agent/new", data=dict(csrf=csrf))
    cid = int(new.headers["location"].split("chat=")[1])
    fake(monkeypatch, [dict(tool="search_tasks", query="Modulgeheimnis")], [])
    first = c.post("/agent/plan", data=dict(csrf=csrf, chat_id=cid, prompt="Zeige meine Modulgeheimnis Aufgabe"))
    assert first.status_code == 200, first.text
    with SessionLocal() as db:
        rows = list(db.scalars(select(AIMessage).where(AIMessage.conversation_id == cid)))
        assert len(rows) == 2 and json.loads(rows[-1].sources_json)[0]["kind"] == "agent"
        rows[-1].content = "Antwort mit Modulgeheimnis"
        db.get(User, uid).permissions = "ai_chat"; db.commit()
    page = c.get(f"/agent?chat={cid}")
    assert "Antwort mit Modulgeheimnis" not in page.text
    captured = []
    fake(monkeypatch, [], [], captured)
    result = c.post("/agent/plan", data=dict(csrf=csrf, chat_id=cid, prompt="Welche Funktionen gibt es?"))
    assert result.status_code == 200, result.text
    assert "Antwort mit Modulgeheimnis" not in str(captured)
    assert 'name="use_agent"' in page.text
    with SessionLocal() as db:
        db.query(AIMessage).filter(AIMessage.conversation_id == cid).delete()
        db.delete(db.get(AIConversation, cid)); db.commit()


def test_category_routing_uses_live_admin_rights_and_affected_record_snapshot():
    from app import agent_anliegen
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        cat = AnliegenCategory(key="draft_routing_test", title="Routing Test", enabled=True, routing="person")
        db.add(cat); db.commit()
        raw = dict(tool="configure_anliegen_category", id=cat.id, title="Routing angepasst", routing="person",
                   assignee_id=actor.id, enabled=True, apply_open=False)
        findings = [dict(type="anliegen_category", id=cat.id), dict(type="person", id=actor.id)]
        action = agent.modules.normalize(db, actor, raw, findings)
        row = anliegen.create(db, actor, cat, "Routing Datensatz", "Meldung nach Erstellung der Vorschau"); db.commit()
        with pytest.raises(__import__('fastapi').HTTPException) as exc:
            agent.modules.execute(db, actor, action)
        assert exc.value.status_code == 409
        fresh = agent.modules.normalize(db, actor, raw, findings)
        other_id = _member("draft-routing-nonadmin@example.org")
        other = db.get(User, other_id)
        with pytest.raises(__import__('fastapi').HTTPException) as exc:
            agent.modules.execute(db, other, fresh)
        assert exc.value.status_code == 403
        result = agent.execute(db, actor, [fresh])
        assert result[0]["url"] == "/anliegen/kategorien"
        assert db.get(AnliegenCategory, cat.id).assignee_id == actor.id
        assert db.get(Anliegen, row.id).assignee_id == actor.id
        assert db.get(Anliegen, row.id).task_id


def test_derived_agent_answer_keeps_module_source_revision(monkeypatch):
    uid = _member("derived-agent@example.org")
    with SessionLocal() as db:
        user = db.get(User, uid)
        task = tasks.create(db, user, dict(title="Abgeleitete Information", assignee_id=uid)); db.commit()
    c = login("derived-agent@example.org", "agent-passwort-123")
    csrf = csrf_of(c.get("/agent").text)
    created = c.post("/agent/new", data=dict(csrf=csrf))
    cid = int(created.headers["location"].split("chat=")[1])
    try:
        fake(monkeypatch, [dict(tool="search_tasks", query="Abgeleitete Information")], [])
        assert c.post("/agent/plan", data=dict(csrf=csrf, chat_id=cid, prompt="Zeige die Aufgabe Abgeleitete Information")).status_code == 200
        fake(monkeypatch, [], [])
        assert c.post("/agent/plan", data=dict(csrf=csrf, chat_id=cid, prompt="Fasse die vorherige Antwort zusammen")).status_code == 200
        with SessionLocal() as db:
            answers = list(db.scalars(select(AIMessage).where(AIMessage.conversation_id == cid, AIMessage.role == "assistant").order_by(AIMessage.id)))
            assert len(answers) == 2
            assert json.loads(answers[-1].sources_json)[0]["record_version"]
            answers[-1].content = "Geschützte abgeleitete Antwort"
            db.get(User, uid).permissions = "ai_chat"; db.commit()
        assert "Geschützte abgeleitete Antwort" not in c.get(f"/agent?chat={cid}").text
    finally:
        with SessionLocal() as db:
            db.query(AIMessage).filter(AIMessage.conversation_id == cid).delete()
            db.delete(db.get(AIConversation, cid)); db.commit()
