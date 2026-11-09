"""Regression coverage for global TAKT Agent PoC: ACLs and explicit confirmation."""
import json

import pytest
from sqlalchemy import delete, select

from app import agent, ai_provider, main, tasks as ts, anliegen as issues
from app.ai_models import AIProvider
from app.anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent
from app.db import SessionLocal, User, get_settings, set_setting
from app.security import hash_password
from app.task_models import Task, TaskActivity
from conftest import csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")


@pytest.fixture(autouse=True)
def _clean_agent_tests():
    with SessionLocal() as db:
        old = {k: get_settings(db)[k] for k in ("module_ai", "module_tasks", "module_anliegen")}
        previous_tasks = set(db.scalars(select(Task.id)))
        previous_issues = set(db.scalars(select(Anliegen.id)))
        previous_providers = set(db.scalars(select(AIProvider.id)))
    yield
    with SessionLocal() as db:
        new_issues = [r for r in db.scalars(select(Anliegen)) if r.id not in previous_issues]
        for row in new_issues:
            db.execute(delete(AnliegenEvent).where(AnliegenEvent.anliegen_id == row.id))
            db.delete(row)
        db.flush()
        new_task_ids = list(db.scalars(select(Task.id).where(Task.id.not_in(previous_tasks)))) if previous_tasks else list(db.scalars(select(Task.id)))
        if new_task_ids:
            db.execute(delete(TaskActivity).where(TaskActivity.task_id.in_(new_task_ids)))
            for tid in new_task_ids:
                row = db.get(Task, tid)
                if row:
                    db.delete(row)
        db.flush()
        for row in db.scalars(select(AIProvider)):
            if row.id not in previous_providers:
                db.delete(row)
        for key, val in old.items():
            set_setting(db, key, val)
        db.commit()
    main._module_cache["at"] = 0.0


def _enable():
    settings(module_ai="1", module_tasks="1", module_anliegen="1")
    with SessionLocal() as db:
        db.add(AIProvider(name="Agent PoC Fake", base_url="https://llm.example.org/api",
                          model_id="test-model", active=True))
        db.commit()


def _member(email):
    with SessionLocal() as db:
        row = db.scalar(select(User).where(User.email == email))
        if not row:
            row = User(email=email, name=email.split("@")[0],
                       password_hash=hash_password("agent-passwort-123"),
                       permissions="ai_chat,tasks,anliegen_submit", is_admin=False,
                       must_change_password=False, active=True)
            db.add(row)
        row.permissions = "ai_chat,tasks,anliegen_submit"
        row.is_admin = False
        row.active = True
        row.must_change_password = False
        db.commit()
        return row.id


def _fake(monkeypatch, *answers):
    replies = iter(answers)
    async def complete(_provider, _messages, *, image=False, max_tokens=1024):
        return json.dumps(next(replies), ensure_ascii=False)
    monkeypatch.setattr(ai_provider, "complete", complete)


def _plan(client, command):
    csrf = csrf_of(client.get("/").text)
    response = client.post("/agent/plan", data={"csrf": csrf, "prompt": command})
    return response, csrf


def test_agent_requires_ai_module_and_is_global():
    _enable()
    c = login(*ADMIN)
    assert 'data-takt-agent' in c.get("/").text
    assert 'data-takt-agent' in c.get("/tasks").text
    settings(module_ai="0")
    assert 'data-takt-agent' not in c.get("/").text
    assert c.post("/agent/plan", data={"csrf": csrf_of(c.get("/").text),
                   "prompt": "Zeige meine Aufgaben"}).status_code == 404


def test_create_task_is_only_committed_after_confirmation_and_cannot_replay(monkeypatch):
    _enable()
    _fake(monkeypatch, {"searches": []},
          {"message": "Eine neue Aufgabe wird vorbereitet.",
           "actions": [{"tool": "create_task", "title": "PoC Prüfung starten",
                        "description": "Abgleich mit dem Aufgabenbereich", "priority": "high"}]})
    c = login(*ADMIN)
    planned, csrf = _plan(c, "Lege die Aufgabe PoC Prüfung starten an")
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert len(body["proposals"]) == 1
    with SessionLocal() as db:
        assert db.scalar(select(Task).where(Task.title == "PoC Prüfung starten")) is None
    applied = c.post("/agent/execute", data={"csrf": csrf, "plan_id": body["plan_id"]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"][0]["url"].startswith("/aufgaben/")
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.title == "PoC Prüfung starten"))
        assert task is not None
        assert db.scalar(select(TaskActivity).where(TaskActivity.task_id == task.id, TaskActivity.kind == "created"))
    replay = c.post("/agent/execute", data={"csrf": csrf, "plan_id": body["plan_id"]})
    assert replay.status_code == 409


def test_search_is_scoped_to_visible_tasks(monkeypatch):
    _enable()
    a = _member("agent-owner-one@example.org")
    b = _member("agent-owner-two@example.org")
    with SessionLocal() as db:
        for uid, name in ((a, "Private Aufgabe A"), (b, "Private Aufgabe B")):
            user = db.get(User, uid)
            ts.create(db, user, {"title": name, "description": "Nur sichtbar für berechtigte Personen",
                                 "assignee_id": str(uid)})
        db.commit()
    _fake(monkeypatch, {"searches": [{"tool": "search_tasks", "query": "Private Aufgabe", "scope": "all"}]},
          {"message": "Ich habe die sichtbaren Aufgaben gesucht.", "actions": []})
    c = login("agent-owner-one@example.org", "agent-passwort-123")
    response, _ = _plan(c, "Suche alle privaten Aufgaben")
    assert response.status_code == 200, response.text
    found = response.json()["results"]
    assert [r["title"] for r in found] == ["Private Aufgabe A"]
    assert response.json()["plan_id"] == ""


def test_agent_rejects_unverified_ids_and_skips_confidential_cases(monkeypatch):
    _enable()
    c = login(*ADMIN)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == ADMIN[0]))
        cat = db.scalar(select(AnliegenCategory).where(AnliegenCategory.key == "complaint"))
        private = issues.create(db, user, cat, "Nicht an Agent weitergeben",
                                "Diese vertrauliche Beschwerde bleibt privat.")
        private_id = private.id
        db.commit()
    _fake(monkeypatch, {"searches": [{"tool": "search_anliegen", "query": "", "scope": "all"}]},
          {"message": "Keine vertraulichen Ergebnisse.", "actions": []})
    result, _ = _plan(c, "Suche alle meine Anliegen")
    assert result.status_code == 200, result.text
    assert all(x["id"] != private_id for x in result.json()["results"] if x["type"] == "anliegen")
    _fake(monkeypatch, {"searches": []},
          {"message": "Gefälschte ID", "actions": [{"tool": "set_task_status", "id": 987654321,
                                                  "status": "done"}]})
    result2, _ = _plan(c, "Setze eine erfundene Aufgabe auf erledigt")
    assert result2.status_code == 422


def test_stale_task_plan_does_not_change_data(monkeypatch):
    _enable()
    c = login(*ADMIN)
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        row = ts.create(db, actor, {"title": "Agent Versionsprüfung",
                                    "description": "Vorher unverändert", "assignee_id": str(actor.id)})
        db.commit()
        task_id = row.id
    _fake(monkeypatch, {"searches": [{"tool": "search_tasks", "query": "Agent Versionsprüfung"}]},
          {"message": "Statuswechsel vorbereitet", "actions": [
              {"tool": "set_task_status", "id": task_id, "status": "in_progress"}]})
    planned, csrf = _plan(c, "Setze die Aufgabe Agent Versionsprüfung auf in Bearbeitung")
    assert planned.status_code == 200, planned.text
    with SessionLocal() as db:
        row = db.get(Task, task_id)
        row.title = "Inzwischen geändert"
        db.commit()
    applied = c.post("/agent/execute", data={"csrf": csrf,
                     "plan_id": planned.json()["plan_id"]})
    assert applied.status_code == 409
    with SessionLocal() as db:
        assert db.get(Task, task_id).status == "open"


def test_confidential_request_never_reaches_provider(monkeypatch):
    _enable()
    async def forbidden(*args, **kwargs):
        raise AssertionError("Confidential text must not reach the LLM")
    monkeypatch.setattr(ai_provider, "complete", forbidden)
    c = login(*ADMIN)
    response, _ = _plan(c, "Erfasse eine vertrauliche Beschwerde wegen Mobbing")
    assert response.status_code == 200
    assert response.json()["open_url"].startswith("/anliegen/neu?agent_private=")
    page = c.get(response.json()["open_url"])
    assert page.status_code == 200 and "Mobbing" in page.text
    assert "nicht an einen KI-Provider" in page.text
    assert 'id="anliegen-ai"' not in page.text


def test_agent_csrf_and_non_ai_permissions(monkeypatch):
    _enable()
    _member("agent-forbidden@example.org")
    c = login("agent-forbidden@example.org", "agent-passwort-123")
    assert c.post("/agent/plan", data={"prompt": "Bitte Aufgaben anzeigen"}).status_code == 400
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "agent-forbidden@example.org"))
        user.permissions = "tasks,anliegen_submit"
        db.commit()
    token = csrf_of(c.get("/").text)
    assert c.post("/agent/plan", data={"csrf": token, "prompt": "Bitte Aufgaben anzeigen"}).status_code == 403
