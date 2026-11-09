"""Agent module workflows, using real services and confirmation endpoints."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete

from app import agent, ai_provider, main, calendars, forms as fm, anliegen as issues
from app.ai_models import AIProvider, AIDmsSource, AgentAudit
from app.calendar_models import Calendar, CalendarEvent, CalendarGrant, CalendarAudit
from app.db import (SessionLocal, User, Form, Process, DmsArea, DmsAccess, DmsRecord,
                    DmsLog, get_settings, set_setting, utcnow)
from app.anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent
from app.task_models import Task, TaskActivity
from conftest import csrf_of, login, settings
from test_agent import _member

ADMIN = ("admin@example.org", "admin-passwort-123")
MODULE_SETTINGS = ("module_ai", "module_tasks", "module_anliegen", "module_forms",
                   "module_calendars", "module_applications", "module_dms", "ai_knowledge_enabled")
# Delete only records created by these tests, in FK dependency order.
MODELS = (AgentAudit, CalendarAudit, CalendarGrant, CalendarEvent, Calendar, AIDmsSource,
          DmsLog, DmsRecord, DmsAccess, DmsArea, AnliegenEvent, Anliegen, TaskActivity,
          Task, AnliegenCategory, Form, Process, AIProvider)


@pytest.fixture(autouse=True)
def isolated():
    with SessionLocal() as db:
        before = {m: set(db.scalars(select(m.record_id if m is AIDmsSource else m.id))) for m in MODELS}
        old = {k: get_settings(db).get(k, "0") for k in MODULE_SETTINGS}
    settings(**{k: "1" for k in MODULE_SETTINGS})
    with SessionLocal() as db:
        db.add(AIProvider(name="Module fake", base_url="https://llm.example.org", model_id="test", active=True))
        db.commit()
    yield
    with SessionLocal() as db:
        for model in MODELS:
            col = model.record_id if model is AIDmsSource else model.id
            db.execute(delete(model).where(col.not_in(before[model])))
        for key, value in old.items():
            set_setting(db, key, value)
        db.commit()
    main._module_cache["at"] = 0


def fake(monkeypatch, searches, actions, captured=None):
    replies = iter([{"searches": searches}, {"message": "Vorschlag prüfen", "actions": actions}])
    async def complete(provider, messages, **kwargs):
        if captured is not None:
            captured.append(messages)
        return json.dumps(next(replies))
    monkeypatch.setattr(ai_provider, "complete", complete)


def plan(c, prompt="Bitte die Schritte vorbereiten"):
    csrf = csrf_of(c.get("/").text)
    return c.post("/agent/plan", data={"csrf": csrf, "prompt": prompt}), csrf


def execute(c, response, csrf):
    return c.post("/agent/execute", data={"csrf": csrf, "plan_id": response.json()["plan_id"]})


def seed(uid=None):
    with SessionLocal() as db:
        actor = db.get(User, uid) if uid else db.scalar(select(User).where(User.email == ADMIN[0]))
        cal = Calendar(owner_id=actor.id, title="Agent Kalender", source="free", visibility="private")
        form = Form(owner_id=actor.id, title="Agent Formular", internal=True, active=True,
                    schema_json='[{"id":"a","type":"short","title":"Vorname"}]')
        area = DmsArea(name="Agent Quelle")
        dest = DmsArea(name="Agent Ziel")
        process = Process(name="Agent Prozess", owner_id=actor.id)
        db.add_all([cal, form, area, dest, process]); db.flush()
        record = DmsRecord(area_id=area.id, kind="manuell", title="Agent Wissen", note="Freigegebene Notiz")
        db.add(record); db.flush()
        db.add(AIDmsSource(record_id=record.id))
        db.commit()
        return actor.id, cal.id, form.id, record.id, area.id, dest.id


def new_event(cid):
    return dict(tool="create_event", id=cid, title="Agent Besprechung", description="Tagesordnung abstimmen",
                location="Raum 1", start="2026-11-12T09:00:00+01:00", end="2026-11-12T10:00:00+01:00")


def test_confirmed_cross_module_plan_and_audits(monkeypatch):
    _, cid, fid, rid, _, aid = seed()
    fake(monkeypatch, [dict(tool=t, query="Agent") for t in
         ("search_calendars", "search_forms", "search_dms", "search_dms_areas", "search_processes")],
         [new_event(cid), dict(tool="copy_form", id=fid), dict(tool="move_dms", id=rid, area_id=aid)])
    c = login(*ADMIN)
    response, csrf = plan(c)
    assert response.status_code == 200, response.text
    preview = "\n".join(response.json()["proposals"])
    assert "Tagesordnung abstimmen" in preview and "Raum 1" in preview and "+01:00" in preview
    assert "Agent Quelle" in preview and "Agent Ziel" in preview
    assert any(r["type"] == "process" for r in response.json()["results"])
    with SessionLocal() as db:
        assert db.scalar(select(CalendarEvent).where(CalendarEvent.calendar_id == cid)) is None
        assert db.scalar(select(Form).where(Form.title == "Agent Formular (Kopie)")) is None
        assert db.get(DmsRecord, rid).area_id != aid
    result = execute(c, response, csrf)
    assert result.status_code == 200, result.text
    assert len(result.json()["applied"]) == 3
    with SessionLocal() as db:
        event = db.scalar(select(CalendarEvent).where(CalendarEvent.calendar_id == cid))
        assert event.title == "Agent Besprechung"
        assert db.scalar(select(CalendarAudit).where(CalendarAudit.calendar_id == cid, CalendarAudit.action == "create"))
        clone = db.scalar(select(Form).where(Form.title == "Agent Formular (Kopie)"))
        assert clone and clone.internal and not clone.active and not clone.public_token
        assert not clone.responses and not clone.invites
        assert db.get(DmsRecord, rid).area_id == aid
        assert db.scalar(select(DmsLog).where(DmsLog.action == "verschoben"))
        assert set(db.scalars(select(AgentAudit.tool))) >= {"create_event", "copy_form", "move_dms"}
    assert execute(c, response, csrf).status_code == 409


def test_live_acl_and_dms_opt_in(monkeypatch):
    owner = _member("agent-module-owner@example.org")
    other = _member("agent-module-other@example.org")
    _, cid, fid, rid, src, dest = seed(owner)
    with SessionLocal() as db:
        u = db.get(User, other)
        u.permissions = "ai_chat,forms,ai_knowledge"
        db.add(DmsAccess(area_id=src, user_id=other, level=1))
        db.commit()
        for tool in ("search_calendars", "search_events", "search_forms"):
            assert agent.search(db, u, dict(tool=tool, query="Agent")) == []
        assert agent.search(db, u, dict(tool="search_dms", query="Agent"))[0]["id"] == rid
        assert agent.search(db, u, dict(tool="search_dms_areas", query="Agent")) == []
        with pytest.raises(HTTPException):
            agent.modules.normalize(db, u, dict(tool="move_dms", id=rid, area_id=dest),
                                    [dict(type="dms", id=rid), dict(type="dms_area", id=dest)])
        db.delete(db.get(AIDmsSource, rid)); db.commit()
        assert agent.search(db, u, dict(tool="search_dms", query="Agent")) == []
        with pytest.raises(HTTPException):
            agent.modules.normalize(db, u, new_event(cid), [dict(type="calendar", id=cid)])
        with pytest.raises(HTTPException):
            agent.modules.normalize(db, u, dict(tool="copy_form", id=fid), [dict(type="form", id=fid)])


@pytest.mark.parametrize("change", ["version", "permission", "module", "approval", "destination"])
def test_revalidation_rolls_back_entire_plan(monkeypatch, change):
    uid = _member("agent-module-writer@example.org")
    _, cid, fid, rid, src, dest = seed(uid)
    with SessionLocal() as db:
        u = db.get(User, uid); u.permissions = "ai_chat,forms,ai_knowledge"
        db.add_all([DmsAccess(area_id=src, user_id=uid, level=2), DmsAccess(area_id=dest, user_id=uid, level=2)])
        db.commit()
    fake(monkeypatch, [dict(tool=t, query="Agent") for t in
         ("search_calendars", "search_dms", "search_dms_areas")],
         [new_event(cid), dict(tool="move_dms", id=rid, area_id=dest)])
    c = login("agent-module-writer@example.org", "agent-passwort-123")
    response, csrf = plan(c)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        if change == "version":
            db.get(DmsRecord, rid).updated_at = utcnow()
        elif change == "permission":
            db.execute(delete(DmsAccess).where(DmsAccess.area_id == dest))
        elif change == "module":
            set_setting(db, "module_dms", "0")
        elif change == "approval":
            db.delete(db.get(AIDmsSource, rid))
        else:
            db.get(DmsArea, dest).name = "Geändert"
        db.commit()
    main._module_cache["at"] = 0
    result = execute(c, response, csrf)
    assert result.status_code in (403, 409), result.text
    with SessionLocal() as db:
        assert db.scalar(select(CalendarEvent).where(CalendarEvent.calendar_id == cid)) is None
        assert db.scalar(select(CalendarAudit).where(CalendarAudit.calendar_id == cid)) is None
        assert db.get(DmsRecord, rid).area_id == src
        assert db.scalar(select(AgentAudit).where(AgentAudit.actor_id == uid)) is None


@pytest.mark.parametrize("field,value", [("start", "2026-11-12T09:00:00"),
    ("end", "2026-11-11T10:00:00+01:00"), ("start", "bogus"), ("title", ""), ("location", "x" * 501)])
def test_invalid_events_and_unverified_ids(field, value):
    _, cid, _, _, _, _ = seed()
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        raw = new_event(cid); raw[field] = value
        with pytest.raises(ValueError):
            agent.normalize_plan(json.dumps(dict(actions=[raw])), actor, [dict(type="calendar", id=cid)], [], db)
        with pytest.raises(ValueError):
            agent.normalize_plan(json.dumps(dict(actions=[new_event(cid)])), actor, [], [], db)


def test_calendar_only_account_context_reset_and_failed_replacement(monkeypatch):
    uid = _member("agent-calendar-only@example.org")
    _, cid, _, _, _, _ = seed(uid)
    settings(module_tasks="0", module_anliegen="0")
    with SessionLocal() as db:
        db.get(User, uid).permissions = "ai_chat"; db.commit()
    c = login("agent-calendar-only@example.org", "agent-passwort-123")
    assert 'data-takt-agent' in c.get("/").text
    fake(monkeypatch, [dict(tool="search_calendars", query="Agent")], [new_event(cid)])
    initial, csrf = plan(c, "Plane eine Besprechung im Agent Kalender")
    assert initial.status_code == 200, initial.text
    captured = []
    fake(monkeypatch, [], [], captured)
    follow, _ = plan(c, "Welche Angaben fehlen noch?")
    assert follow.status_code == 200
    assert "Plane eine Besprechung" in str(captured[0])
    assert execute(c, initial, csrf).status_code == 409
    assert c.post("/agent/reset", data={}).status_code == 400
    assert c.post("/agent/reset", data={"csrf": csrf}).status_code == 200
    fake(monkeypatch, [], [], captured := [])
    plan(c, "Neuer unabhängiger Auftrag")
    assert "Welche Angaben fehlen" not in str(captured)
    fake(monkeypatch, [dict(tool="search_calendars", query="Agent")], [new_event(cid)])
    initial, csrf = plan(c)
    assert initial.status_code == 200
    rejected, _ = plan(c, " ")
    assert rejected.status_code == 422
    assert execute(c, initial, csrf).status_code == 409


def test_order_fields_use_existing_status_rules_and_full_preview(monkeypatch):
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        cat = db.scalar(select(AnliegenCategory).where(AnliegenCategory.key.in_(issues.ORDER_KEYS)))
        row = issues.create(db, actor, cat, "Agent Bestellung", "Zwei Bürostühle für Besprechungsraum")
        row.assignee_id = actor.id; row.status = "open"
        db.commit(); rid = row.id
    fake(monkeypatch, [dict(tool="search_anliegen", query="Agent Bestellung")],
         [dict(tool="set_anliegen_status", id=rid, status="ordered", supplier="Büro GmbH",
               order_reference="BEST-42", expected_delivery="2026-11-20")])
    c = login(*ADMIN); response, csrf = plan(c)
    assert response.status_code == 200, response.text
    assert "BEST-42" in response.json()["proposals"][0]
    result = execute(c, response, csrf)
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        row = db.get(Anliegen, rid)
        assert row.status == "ordered" and row.supplier == "Büro GmbH"
        assert row.order_reference == "BEST-42" and row.expected_delivery_at.date().isoformat() == "2026-11-20"
        assert row.ordered_at is not None


def test_dms_citizen_records_never_reach_planner():
    _, _, _, rid, src, _ = seed()
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        row = db.get(DmsRecord, rid)
        row.applicant_email = "private@example.org"
        row.text = "Agent private form answers"
        db.commit()
        assert agent.search(db, actor, dict(tool="search_dms", query="Agent")) == []
        row.applicant_email = ""; row.kind = "antrag"; db.commit()
        assert agent.search(db, actor, dict(tool="search_dms", query="Agent")) == []


def test_event_acl_hides_organizational_event():
    from app.db import Organization
    owner = _member("agent-cal-event-owner@example.org")
    other = _member("agent-cal-event-reader@example.org")
    _, cid, _, _, _, _ = seed(owner)
    with SessionLocal() as db:
        actor = db.get(User, other)
        actor.permissions = "ai_chat"
        unit = db.scalar(select(Organization))
        assert unit is not None
        db.add(CalendarGrant(calendar_id=cid, user_id=other, can_write=False))
        db.add(CalendarEvent(calendar_id=cid, uid="agent-event", title="Agent protected event",
                             org_id=unit.id, starts_at="2026-11-12T09:00:00+01:00", ends_at="2026-11-12T10:00:00+01:00"))
        db.commit()
        assert agent.search(db, actor, dict(tool="search_calendars", query="Agent"))
        assert agent.search(db, actor, dict(tool="search_events", query="Agent protected")) == []


def test_stale_form_and_other_session_cannot_confirm(monkeypatch):
    _, _, fid, _, _, _ = seed()
    c = login(*ADMIN)
    fake(monkeypatch, [dict(tool="search_forms", query="Agent")], [dict(tool="copy_form", id=fid)])
    response, csrf = plan(c)
    assert response.status_code == 200
    other_session = login(*ADMIN)
    other_csrf = csrf_of(other_session.get("/").text)
    assert execute(other_session, response, other_csrf).status_code == 409
    assert c.post("/agent/execute", data={"plan_id": response.json()["plan_id"]}).status_code == 400
    assert c.post("/agent/cancel", data={"plan_id": response.json()["plan_id"]}).status_code == 400
    with SessionLocal() as db:
        db.get(Form, fid).updated_at = utcnow(); db.commit()
    assert execute(c, response, csrf).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Form).where(Form.title == "Agent Formular (Kopie)")) is None


def test_conflicting_actions_and_source_calendars_rejected():
    _, cid, _, _, _, _ = seed()
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        raw = new_event(cid)
        with pytest.raises(ValueError):
            agent.normalize_plan(json.dumps(dict(actions=[raw, raw])), actor, [dict(type="calendar", id=cid)], [], db)
        db.get(Calendar, cid).source = "tasks"; db.commit()
        with pytest.raises(HTTPException):
            agent.modules.normalize(db, actor, raw, [dict(type="calendar", id=cid)])
