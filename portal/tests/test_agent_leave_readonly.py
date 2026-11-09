"""Scoped read-only agent integration with personal TAKT leave workflows."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete

from app import agent, agent_intent, agent_modules, ai_provider, main
from app.ai_models import AIProvider
from app.db import Organization, SessionLocal, User, get_settings, set_setting
from app.leave_admin import removed_ids
from app.leave_models import LeaveRequest, LeaveAdminRemoval
from app.org_models import OrgMembership
from app.security import hash_password
from conftest import csrf_of, login, settings


@pytest.fixture
def leave_people():
    keys = ("module_ai", "module_calendars")
    with SessionLocal() as db:
        old = {key: get_settings(db)[key] for key in keys}
    settings(module_ai="1", module_calendars="1")
    with SessionLocal() as db:
        org = db.scalar(select(Organization).order_by(Organization.id).limit(1))
        assert org is not None
        own = User(
            email="agent-leave-owner@example.org", name="Synthetic Leave Owner",
            password_hash=hash_password("test-leave-pass123"),
            permissions="ai_chat", is_admin=False, active=True,
            must_change_password=False,
        )
        other = User(
            email="agent-leave-other@example.org", name="Synthetic Other Employee",
            password_hash=hash_password("test-leave-pass123"),
            permissions="ai_chat", is_admin=False, active=True,
            must_change_password=False,
        )
        db.add_all([own, other])
        db.flush()
        db.add_all([
            OrgMembership(user_id=own.id, org_id=org.id, is_primary=True),
            OrgMembership(user_id=other.id, org_id=org.id, is_primary=True),
        ])
        db.flush()
        own_leave = LeaveRequest(
            person_id=own.id, org_id=org.id,
            starts_on="2026-12-14", ends_on="2026-12-18", status="requested",
        )
        other_leave = LeaveRequest(
            person_id=other.id, org_id=org.id,
            starts_on="2026-12-21", ends_on="2026-12-23", status="planned",
        )
        provider = AIProvider(
            name="Agent leave provider", model_id="test-leave-model",
            base_url="https://llm.example.org/v1", active=True,
        )
        db.add_all([own_leave, other_leave, provider])
        db.commit()
        ids = dict(own=own.id, other=other.id, own_leave=own_leave.id,
                   other_leave=other_leave.id, provider=provider.id)
    yield ids
    with SessionLocal() as db:
        for row in db.scalars(select(LeaveAdminRemoval).where(
                LeaveAdminRemoval.request_id.in_([ids["own_leave"], ids["other_leave"]]))):
            db.delete(row)
        db.flush()
        for lid in [ids["own_leave"], ids["other_leave"]]:
            row = db.get(LeaveRequest, lid)
            if row:
                db.delete(row)
        db.flush()
        db.execute(delete(OrgMembership).where(
            OrgMembership.user_id.in_([ids["own"], ids["other"]])))
        for uid in [ids["own"], ids["other"]]:
            row = db.get(User, uid)
            if row:
                db.delete(row)
        provider = db.get(AIProvider, ids["provider"])
        if provider:
            db.delete(provider)
        for key, val in old.items():
            set_setting(db, key, val)
        db.commit()
    main._module_cache["at"] = 0.0


def test_only_own_leave_is_visible_and_metadata_is_minimal(leave_people):
    ids = leave_people
    with SessionLocal() as db:
        own = db.get(User, ids["own"])
        other = db.get(User, ids["other"])
        specs = {"tool": "search_my_leave", "query": "", "scope": "all"}
        found = agent.search(db, own, specs)
        assert [record["id"] for record in found] == [ids["own_leave"]]
        assert found[0]["type"] == "leave"
        assert found[0]["status"] == "requested"
        assert found[0]["url"] == f"/urlaub/vorgang/{ids['own_leave']}"
        assert not any(key in found[0] for key in (
            "reason", "description", "approval_path", "private_note", "person_name"))
        assert [record["id"] for record in agent.search(db, other, specs)] == [
            ids["other_leave"]]
        assert not any(record["id"] == ids["other_leave"] for record in found)
        assert "search_my_leave" not in agent.WRITE_TOOLS
        assert "search_my_leave" in agent.READ_TOOLS


def test_source_access_and_revisions_are_rechecked(leave_people):
    ids = leave_people
    with SessionLocal() as db:
        owner = db.get(User, ids["own"])
        colleague = db.get(User, ids["other"])
        source = {
            "kind": "agent", "record_type": "leave", "record_id": ids["own_leave"],
            "record_version": agent.reference_revision(db, "leave", ids["own_leave"]),
        }
        assert agent.reference_accessible(db, owner, source)
        assert not agent.reference_accessible(db, colleague, source)
        row = db.get(LeaveRequest, ids["own_leave"])
        row.status = "binding"
        row.version += 1
        db.commit()
        assert not agent.reference_accessible(db, owner, source)
        source["record_version"] = agent.reference_revision(db, "leave", ids["own_leave"])
        assert agent.reference_accessible(db, owner, source)
        db.add(LeaveAdminRemoval(
            request_id=ids["own_leave"], person_id=owner.id,
            actor_id=owner.id, reason="Synthetic test removal",
            snapshot_json="{}",
        ))
        db.commit()
        assert not agent.reference_accessible(db, owner, source)
        assert agent.search(db, owner, {"tool": "search_my_leave", "query": ""}) == []


def test_module_disable_blocks_own_leave(leave_people):
    ids = leave_people
    with SessionLocal() as db:
        owner = db.get(User, ids["own"])
        source = {"kind": "agent", "record_type": "leave",
                  "record_id": ids["own_leave"]}
        assert agent.reference_accessible(db, owner, source)
        settings(module_calendars="0")
        assert not agent.reference_accessible(db, owner, source)
        with pytest.raises(HTTPException) as error:
            agent.search(db, owner, {"tool": "search_my_leave", "query": ""})
        assert error.value.status_code == 403


def test_agent_intent_navigation_and_schema_respect_acl(leave_people):
    ids = leave_people
    with SessionLocal() as db:
        user = db.get(User, ids["own"])
        assert agent_intent.classify("Öffne meinen Urlaub") == "navigate"
        assert agent_intent.navigation("Öffne meinen Urlaub", user) == {
            "url": "/urlaub/mein-urlaub", "label": "Mein Urlaub"}
        assert agent_intent.classify("Zeige meine Urlaubsanträge") == "operate"
        assert "search_my_leave" in json.dumps(
            agent.search_instructions(user, focus={"leave"}), ensure_ascii=False)
        assert "search_tasks" not in json.dumps(
            agent.search_instructions(user, focus={"leave"}), ensure_ascii=False)


def test_agent_plan_searches_only_own_leave_without_mutations(leave_people, monkeypatch):
    ids = leave_people
    calls = []

    async def fake_complete(provider, messages, *, image=False, max_tokens=1024):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps({"searches": [{"tool": "search_my_leave", "query": ""}]})
        return json.dumps({"message": "Hier sind deine Urlaubsanträge.", "actions": []})

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    client = login("agent-leave-owner@example.org", "test-leave-pass123")
    csrf = csrf_of(client.get("/agent").text)
    response = client.post("/agent/plan", data={
        "csrf": csrf, "prompt": "Zeige meine Urlaubsanträge",
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "operate"
    assert payload["proposals"] == []
    assert payload["plan_id"] == ""
    assert [r["id"] for r in payload["results"]] == [ids["own_leave"]]
    assert all(r["id"] != ids["other_leave"] for r in payload["results"])
