import json
import re

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import agent, agent_forms, forms as fm
from app.ai_models import AgentAudit
from app.db import Form, FormResponse, FormShare, SessionLocal, User, utcnow
from conftest import login
from test_agent_modules import ADMIN, _member, fake, isolated, plan


def create_form(owner, title, **kwargs):
    with SessionLocal() as db:
        row = Form(
            owner_id=owner,
            title=title,
            schema_json=json.dumps(fm.template_items()),
            **{"active": False, **kwargs},
        )
        db.add(row)
        db.commit()
        return row.id


def review(client, response, csrf, **changes):
    proposal = response.json()
    return client.post(
        "/agent/draft/review",
        data=dict(csrf=csrf, agent_plan=proposal["plan_id"], agent_step=0, **changes),
    )


def confirm(client, result):
    assert result.status_code == 200, result.text
    values = {
        key: re.search(rf'name="{key}" value="([^"]+)"', result.text)[1]
        for key in ("csrf", "plan_id", "review_id")
    }
    return client.post("/agent/draft/save", data=values)


def test_native_form_proposal_saves_edited_birthday_questions(monkeypatch):
    fields = [
        dict(type="short", title="Name", required=True),
        dict(type="short", subtype="number", title="Tag", min=1, max=31),
        dict(type="dropdown", title="Monat", options=["Januar", "Februar"]),
    ]
    messages = []
    fake(
        monkeypatch,
        [],
        [dict(tool="create_form", title="Geburtstage im Team", fields=fields)],
        messages,
    )
    client = login(*ADMIN)
    response, csrf = plan(
        client, "Formular für die Geburtstage der Belegschaft erstellen"
    )
    proposal = response.json()
    assert "Tag und Monat" in messages[1][0]["content"]
    assert proposal["open_url"].startswith("/forms/new?")
    page = client.get(proposal["open_url"])
    assert 'id="builder-form"' in page.text
    assert page.headers["cache-control"] == "no-store"
    assert client.get("/forms/new", params={"agent_plan": "invalid"}).status_code == 409
    items = client.get("/agent/draft", params={"plan_id": proposal["plan_id"]}).json()[
        "fields"
    ]["fields"]
    items[-1]["options"].append(dict(id="march", label="März"))
    items[-1]["required"] = True
    assert (
        review(client, response, "bad-csrf", items_json=json.dumps(items)).status_code
        == 400
    )
    result = review(client, response, csrf, items_json=json.dumps(items))
    assert "März" in result.text
    with SessionLocal() as db:
        assert (
            db.scalar(select(Form).where(Form.title == "Geburtstage im Team")) is None
        )
    assert confirm(client, result).status_code == 303
    with SessionLocal() as db:
        row = db.scalar(select(Form).where(Form.title == "Geburtstage im Team"))
        assert row.internal and not row.active and row.public_token is None
        assert fm.raw_schema(row) == items
        audit = db.scalar(
            select(AgentAudit).where(
                AgentAudit.tool == "create_form", AgentAudit.target_id == row.id
            )
        )
        assert audit.actor_id == row.owner_id


def test_edit_keeps_field_identity_and_requires_explicit_confirmation(monkeypatch):
    owner = _member("agent-form-edit-owner@example.org")
    form_id = create_form(owner, "Geschlossener Gerätefragebogen")
    with SessionLocal() as db:
        existing = fm.raw_schema(db.get(Form, form_id))
    fake(
        monkeypatch,
        [dict(tool="search_forms", query=f"#{form_id}")],
        [
            dict(
                tool="edit_form",
                id=form_id,
                fields=[dict(type="yesno", title="Gerät verfügbar")],
            )
        ],
    )
    client = login(*ADMIN)
    response, csrf = plan(
        client, "Ergänze das Formular um die Frage, ob ein Gerät verfügbar ist"
    )
    proposal = response.json()
    assert proposal["open_url"].startswith(f"/forms/{form_id}?")
    items = client.get("/agent/draft", params={"plan_id": proposal["plan_id"]}).json()[
        "fields"
    ]["fields"]
    items[-1]["title"] = "Ist das Gerät verfügbar?"
    reviewed = review(
        client, response, csrf, items_json=json.dumps(items), title="Gerätefragebogen"
    )
    assert "Ist das Gerät verfügbar?" in reviewed.text
    with SessionLocal() as db:
        assert fm.raw_schema(db.get(Form, form_id)) == existing
    assert confirm(client, reviewed).status_code == 303
    with SessionLocal() as db:
        row = db.get(Form, form_id)
        assert row.title == "Gerätefragebogen"
        assert fm.raw_schema(row)[:2] == existing
        assert [opt["label"] for opt in fm.raw_schema(row)[-1]["options"]] == [
            "Ja",
            "Nein",
        ]


@pytest.mark.parametrize("change", ["version", "publish", "answers"])
def test_form_edit_rechecks_state_after_review(monkeypatch, change):
    form_id = create_form(
        _member(f"agent-form-{change}@example.org"), "Geschlossener Fragebogen"
    )
    fake(
        monkeypatch,
        [dict(tool="search_forms", query=f"#{form_id}")],
        [dict(tool="edit_form", id=form_id, title="Geänderter Fragebogen")],
    )
    client = login(*ADMIN)
    response, csrf = plan(client, "Benenne das Formular um")
    reviewed = review(client, response, csrf)
    with SessionLocal() as db:
        row = db.get(Form, form_id)
        if change == "publish":
            row.published_at = utcnow()
        elif change == "answers":
            db.add(
                FormResponse(
                    form_id=form_id, answers_json='{"secret":"vertrauliche Antwort"}'
                )
            )
        else:
            row.updated_at = utcnow()
        db.commit()
    assert confirm(client, reviewed).status_code == 409
    with SessionLocal() as db:
        assert db.get(Form, form_id).title == "Geschlossener Fragebogen"


def test_form_search_uses_record_permissions_and_excludes_answers():
    owner = _member("agent-form-acl-owner@example.org")
    reader = _member("agent-form-acl-reader@example.org")
    form_id = create_form(owner, "Interner Fragebogen")
    application = create_form(owner, "Interner Antrag", kind="application")
    with SessionLocal() as db:
        user = db.get(User, reader)
        user.permissions = "forms,ai_chat"
        db.add(
            FormResponse(
                form_id=form_id, answers_json='{"secret":"vertrauliche Antwort"}'
            )
        )
        db.add(FormShare(form_id=form_id, user_id=reader, level=fm.VIEW))
        db.commit()
        found = agent.search(db, user, dict(tool="search_forms", query="Interner"))
        assert [(item["id"], item["editable"]) for item in found] == [(form_id, False)]
        assert "vertrauliche Antwort" not in json.dumps(found)
        with pytest.raises(HTTPException) as exc:
            agent_forms.normalize(
                user, dict(tool="edit_form", id=form_id, title="Abgewiesen"), db, found
            )
        assert exc.value.status_code == 403
        user = db.get(User, owner)
        user.permissions = "forms,ai_chat"
        found = agent.search(
            db, user, dict(tool="search_forms", query=f"#{application}")
        )
        assert found[0]["editable"] is False
        with pytest.raises(HTTPException) as exc:
            agent_forms.normalize(
                user,
                dict(tool="edit_form", id=application, title="Abgewiesen"),
                db,
                found,
            )
        assert exc.value.status_code == 409
