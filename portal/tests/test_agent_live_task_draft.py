import json

from sqlalchemy import select

from app import ai_provider, agent_task_draft
from app.db import SessionLocal
from app.task_models import Task
from conftest import csrf_of, login
from test_agent_form_workflows import confirm
from test_agent_modules import ADMIN, isolated


def test_partial_task_opens_and_live_patch_keeps_native_review(monkeypatch):
    calls = []

    async def complete(_provider, messages, **kwargs):
        calls.append(json.loads(messages[-1]["content"]))
        return json.dumps(
            {
                "patch": {
                    "title": "IT",
                    "due_date": "2030-12-12",
                    "priority": "high",
                    "assignee_id": "9234",
                    "unknown": "ignored",
                }
            }
        )

    monkeypatch.setattr(ai_provider, "complete", complete)
    client = login(*ADMIN)
    csrf = csrf_of(client.get("/").text)
    response = client.post(
        "/agent/plan", data=dict(csrf=csrf, prompt="/takt Erstelle eine Aufgabe")
    )
    proposal = response.json()
    assert proposal["open_task_draft"] and calls == []
    page = client.get(proposal["open_url"])
    assert page.status_code == 200 and 'action="/agent/draft/review"' in page.text
    assert 'name="title" value=""' in page.text
    assert page.headers["cache-control"] == "no-store"
    pid = proposal["plan_id"]

    def refine(revision=0, **overrides):
        data = dict(
            csrf=csrf,
            plan_id=pid,
            revision=revision,
            prompt="Bitte den Titel ergänzen",
            title="",
            description="Mein manueller Text",
        )
        return client.post("/agent/draft/task", data={**data, **overrides})

    assert refine(csrf="bad").status_code == 400
    assert refine(prompt="vertrauliche Beschwerde").status_code == 422
    result = refine()
    assert result.status_code == 200, result.text
    assert result.json()["fields"] == {
        "title": "IT",
        "due_date": "2030-12-12",
        "priority": "high",
    }
    assert calls[0]["entwurf"]["description"] == "Mein manueller Text"
    assert refine().status_code == 409
    form_data = dict(csrf=csrf, agent_plan=pid, agent_step=0, task_revision=0)
    assert client.post("/agent/draft/review", data=form_data).status_code == 409
    form_data["task_revision"] = 1
    reviewed = client.post("/agent/draft/review", data=form_data)
    assert reviewed.status_code == 200, reviewed.text
    assert "Mein manueller Text" in reviewed.text and "2030-12-12" in reviewed.text
    with SessionLocal() as db:
        assert db.scalar(select(Task).where(Task.title == "IT")) is None
    assert confirm(client, reviewed).status_code == 303
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.title == "IT"))
        assert task.description == "Mein manueller Text" and task.priority == "high"


def test_fast_scope_leaves_existing_and_multiple_operations_in_general_planner():
    assert (
        agent_task_draft.match("Aufgabe: Inventur bis morgen") == "Inventur bis morgen"
    )
    assert (
        agent_task_draft.match("Erstelle eine Aufgabe und öffne den Kalender") is None
    )
    assert agent_task_draft.match("Bearbeite die Aufgabe Inventur") is None
