import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import agent, agent_applications as adapter, forms as fm, workflow
from app.ai_models import AgentAudit
from app.db import (
    ApplicationTask,
    Form,
    FormResponse,
    FormShare,
    Process,
    ProcessVersion,
    SessionLocal,
    User,
)
from conftest import login
from test_agent_form_workflows import confirm, review
from test_agent_modules import ADMIN, _member, fake, isolated, plan


def create_case(owner_id, ref, *, kind="", four_eyes=False):
    with SessionLocal() as db:
        form = Form(
            title="Antrag auf Ausrüstung",
            owner_id=owner_id,
            kind="application",
            schema_json=json.dumps(fm.template_items()),
        )
        db.add(form)
        db.flush()
        row = FormResponse(
            form_id=form.id,
            ref_no=ref,
            status="received",
            assignee_id=owner_id,
            name="Interne Person",
            answers_json='{"secret":"vertrauliche Antwort"}',
        )
        db.add(row)
        db.flush()
        task = None
        if kind:
            process = Process(name="Bestehender Ablauf", owner_id=owner_id)
            db.add(process)
            db.flush()
            step = dict(
                id="review", name="Unterlagen prüfen", type=kind, four_eyes=four_eyes
            )
            if kind == "task":
                step.update(
                    checklist=["Unterlagen geprüft"],
                    fields=[
                        dict(
                            key="document",
                            label="Dokument",
                            type="text",
                            required=True,
                        )
                    ],
                )
            steps = (
                [dict(id="previous", name="Vorbereitung", type="task")]
                if four_eyes
                else []
            ) + [step]
            version = ProcessVersion(
                process_id=process.id,
                version=1,
                definition_json=json.dumps(dict(steps=steps, end_status="done")),
            )
            db.add(version)
            db.flush()
            row.process_version_id = version.id
            if four_eyes:
                db.add(
                    ApplicationTask(
                        response_id=row.id,
                        step_id="previous",
                        name="Vorbereitung",
                        kind="task",
                        state="done",
                        completed_by_id=owner_id,
                    )
                )
                db.flush()
            task = ApplicationTask(
                response_id=row.id,
                step_id="review",
                name=step["name"],
                kind=kind,
                state="open",
                assignee_id=owner_id,
            )
            db.add(task)
        db.commit()
        return row.id, form.id, task.id if task else None


def test_internal_note_opens_real_case_and_only_saves_after_review(monkeypatch):
    owner = _member("agent-app-owner@example.org")
    ref = "AUSR-2030-00001"
    case_id, form_id, _ = create_case(owner, ref)
    client = login("agent-app-owner@example.org", "agent-passwort-123")
    command = dict(
        tool="application_command", id=case_id, operation="note", text="Vorabprüfung"
    )
    searches = [dict(tool="search_applications", query=ref)]
    fake(monkeypatch, searches, [command])
    response, csrf = plan(client, f"Interne Notiz zum Antrag {ref}")
    data = response.json()
    assert data["open_url"].startswith(f"/forms/{form_id}/applications/{case_id}?")
    assert client.get(data["open_url"]).status_code == 200
    assert "vertrauliche Antwort" not in response.text
    assert (
        client.post(
            "/agent/execute", data=dict(csrf=csrf, plan_id=data["plan_id"])
        ).status_code
        == 409
    )
    fake(monkeypatch, searches, [command])
    response, csrf = plan(client, f"Interne Notiz zum Antrag {ref}")
    assert review(client, response, "bad-csrf", text="Änderung").status_code == 400
    reviewed = review(client, response, csrf, text="Geprüfte interne Notiz")
    assert "Geprüfte interne Notiz" in reviewed.text
    with SessionLocal() as db:
        assert db.get(FormResponse, case_id).events == []
    assert confirm(client, reviewed).status_code == 303
    assert confirm(client, reviewed).status_code == 409
    with SessionLocal() as db:
        row = db.get(FormResponse, case_id)
        assert [(event.kind, event.text, event.public) for event in row.events] == [
            ("note", "Geprüfte interne Notiz", False)
        ]
        audit = db.scalar(
            select(AgentAudit).where(
                AgentAudit.tool == command["tool"], AgentAudit.target_id == case_id
            )
        )
        assert audit.actor_id == owner


def test_checklist_requires_human_confirmation_and_uses_native_workflow(monkeypatch):
    admin = _member("agent-app-check@example.org")
    ref = "AUSR-2030-00002"
    case_id, _, task_id = create_case(admin, ref, kind="task")
    client = login("agent-app-check@example.org", "agent-passwort-123")
    fake(
        monkeypatch,
        [dict(tool="search_applications", query=ref)],
        [
            dict(
                tool="application_step",
                id=case_id,
                task_id=task_id,
                operation="done",
                checks=["Unterlagen geprüft"],
                values={"document": "erfunden"},
            )
        ],
    )
    response, csrf = plan(client, f"Arbeitsschritt beim Antrag {ref} erledigen")
    assert response.status_code == 200, response.text
    assert review(client, response, csrf).status_code == 422
    reviewed = review(
        client, response, csrf, check="Unterlagen geprüft", f_document="Bericht 7"
    )
    assert "Bericht 7" in reviewed.text and "erfunden" not in reviewed.text
    assert confirm(client, reviewed).status_code == 303
    with SessionLocal() as db:
        assert db.get(ApplicationTask, task_id).state == "done"
        row = db.get(FormResponse, case_id)
        assert row.fields["document"] == "Bericht 7"
        assert row.status == "done"


def test_scoped_results_and_four_eyes():
    owner = _member("agent-app-approval@example.org")
    outsider = _member("agent-app-outsider@example.org")
    case_id, form_id, task_id = create_case(
        owner, "AUSR-2030-00003", kind="approval", four_eyes=True
    )
    with SessionLocal() as db:
        owner_user, other = db.get(User, owner), db.get(User, outsider)
        spec = dict(tool="search_applications", query="AUSR-2030-00003")
        assert agent.search(db, other, spec) == []
        findings = agent.search(db, owner_user, spec)
        assert findings[0]["step"]["operations"] == []
        raw = dict(
            tool="application_step", id=case_id, task_id=task_id, operation="approved"
        )
        with pytest.raises(HTTPException) as denied:
            adapter.normalize(db, owner_user, raw, findings)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as cannot_bypass:
            adapter.normalize(
                db,
                owner_user,
                dict(
                    tool="application_command",
                    id=case_id,
                    operation="status",
                    status="approved",
                ),
                findings,
            )
        assert cannot_bypass.value.status_code == 409
        db.add(FormShare(form_id=form_id, user_id=outsider, level=fm.VIEW))
        db.commit()
        visible = agent.search(db, other, spec)[0]
        assert not visible["editable"] and "Interne Person" not in json.dumps(visible)


def test_concurrent_case_change_invalidates_review(monkeypatch):
    owner = _member("agent-app-stale@example.org")
    ref = "AUSR-2030-00004"
    case_id, _, _ = create_case(owner, ref)
    client = login(*ADMIN)
    fake(
        monkeypatch,
        [dict(tool="search_applications", query=ref)],
        [
            dict(
                tool="application_command",
                id=case_id,
                operation="due",
                due="2030-01-10",
            )
        ],
    )
    response, csrf = plan(client, f"Frist für Antrag {ref} setzen")
    reviewed = review(client, response, csrf, due="2030-01-12")
    with SessionLocal() as db:
        row = db.get(FormResponse, case_id)
        from app import applications

        applications.note(row, "Neuere Notiz", db.get(User, owner))
        db.commit()
    assert confirm(client, reviewed).status_code == 409
    with SessionLocal() as db:
        assert db.get(FormResponse, case_id).due_at is None
