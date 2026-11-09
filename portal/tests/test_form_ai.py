"""KI-Formularassistent: sichere Entwürfe, TAKT-Schema, Freigaben und Schreibschutz."""
import json

import pytest
from sqlalchemy import select

from app import ai_provider, form_ai, forms as fm
from app.ai_models import AIProvider
from app.db import Form, SessionLocal, User
from app.security import encrypt, hash_password
from conftest import client, csrf_of, login, settings


ADMIN = ("admin@example.org", "admin-passwort-123")


def _create_form():
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == ADMIN[0]))
        form = Form(owner_id=admin.id, title="Bisheriger Titel", description="Bisherige Beschreibung",
                    schema_json=json.dumps(fm.clean_schema([
                        {"id": "existing", "type": "radio", "title": "Schaden vorhanden?",
                         "options": [{"id": "yes", "label": "Ja"}, {"id": "no", "label": "Nein"}]}
                    ])), active=False)
        db.add(form)
        db.commit()
        return form.id


def _create_provider():
    with SessionLocal() as db:
        provider = AIProvider(name="Form Assistant Test", base_url="https://llm.example.org/api",
                              model_id="test-model", text_key_enc=encrypt("test-key"), active=True)
        db.add(provider)
        db.commit()
        return provider.id


def _suggestion():
    return json.dumps({
        "title": "Schadensmeldung",
        "description": "Bitte schildern Sie den Vorfall.",
        "items": [
            {"id": "details", "type": "long", "title": "Beschreibung", "required": True,
             "show_if": {"mode": "all", "rules": [{"q": "existing", "op": "eq", "value": "Ja"}]}},
            {"id": "point", "type": "geo", "title": "Schadensort", "geometries": ["point"],
             "allow_gps": True},
        ],
        "notes": ["Vor der Veröffentlichung fachlich prüfen."],
    }, ensure_ascii=False)


def test_ai_schema_maps_ids_and_keeps_conditional_reference():
    raw = {"title": "Meldung", "description": "", "items": [
        {"id": "decision", "type": "radio", "title": "Meldung?", "options": ["Ja", "Nein"]},
        {"id": "explain", "type": "long", "title": "Erläuterung",
         "show_if": {"mode": "all", "rules": [{"q": "decision", "op": "eq", "value": "Ja"}]}},
    ]}
    out = form_ai.parse_result(json.dumps(raw), [], "replace", set())
    assert len(out["items"]) == 2
    a, b = out["items"]
    assert a["id"] != "decision" and b["id"] != "explain"
    assert b["show_if"]["rules"][0]["q"] == a["id"]
    assert a["options"][0]["label"] == "Ja"


def test_ai_schema_rejects_unsupported_fields_and_unknown_blocks():
    for item in ({"id": "x", "type": "script", "title": "Ausführen"},
                 {"id": "x", "type": "block", "block_id": 999}):
        with pytest.raises(ValueError):
            form_ai.parse_result(json.dumps({"items": [item]}), [], "replace", set())
    with pytest.raises(ValueError):
        form_ai.parse_result("Hier ist das Formular:", [], "replace", set())


def test_ai_schema_rejects_future_conditional_dependencies():
    with pytest.raises(ValueError):
        form_ai.parse_result(json.dumps({"items": [
            {"id": "later", "type": "short", "title": "Erster Wert",
             "show_if": {"rules": [{"q": "after", "op": "filled", "value": ""}]}},
            {"id": "after", "type": "short", "title": "Zweiter Wert"},
        ]}), [], "replace", set())


def test_ai_draft_endpoint_is_read_only_and_uses_takt_context(monkeypatch):
    settings(module_ai="1", module_forms="1")
    form_id, provider_id = _create_form(), _create_provider()
    captured = []

    async def fake_complete(provider, messages, *, image=False, max_tokens=1024):
        captured.append(messages)
        return _suggestion()

    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    c = login(*ADMIN)
    page = c.get(f"/forms/{form_id}")
    assert page.status_code == 200
    assert "KI-Formularassistent" in page.text
    assert "/static/form-ai-assistant.js" in page.text
    csrf = csrf_of(page.text)
    with SessionLocal() as db:
        before = db.get(Form, form_id).schema_json
    payload = {"csrf": csrf, "prompt": "Meldung mit Standort und einer Bedingung",
               "mode": "append", "provider_id": str(provider_id), "current_json": before,
               "form_title": "Bisheriger Titel", "form_description": "Bisherige Beschreibung"}
    response = c.post(f"/forms/{form_id}/ai-draft", data=payload)
    assert response.status_code == 200, response.text
    draft = response.json()
    assert len(draft["items"]) == 2
    assert draft["items"][0]["show_if"]["rules"][0]["q"] == "existing"
    assert draft["items"][1]["geometries"] == ["point"]
    assert draft["mode"] == "append"
    assert captured and "geo" in captured[0][0]["content"]
    assert "vorhandene_elemente" in captured[0][1]["content"]
    with SessionLocal() as db:
        assert db.get(Form, form_id).schema_json == before


def test_ai_draft_checks_csrf_and_editor_permission(monkeypatch):
    settings(module_ai="1", module_forms="1")
    form_id, provider_id = _create_form(), _create_provider()
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get(f"/forms/{form_id}").text)
    no_csrf = admin.post(f"/forms/{form_id}/ai-draft",
                         data={"prompt": "Neue Fragen", "provider_id": str(provider_id)})
    assert no_csrf.status_code == 400

    with SessionLocal() as db:
        new = User(email="form-ai-viewer@example.org", name="Viewer",
                   password_hash=hash_password("passwort-123"),
                   permissions="forms,ai_chat", active=True, must_change_password=False)
        db.add(new)
        db.commit()
    viewer = login("form-ai-viewer@example.org", "passwort-123")
    viewer_csrf = csrf_of(viewer.get("/forms").text)
    response = viewer.post(f"/forms/{form_id}/ai-draft",
                           data={"csrf": viewer_csrf, "prompt": "Neue Fragen",
                                 "provider_id": str(provider_id)})
    assert response.status_code == 404


def test_ai_draft_requires_enabled_ai_module():
    settings(module_ai="0", module_forms="1")
    form_id = _create_form()
    admin = login(*ADMIN)
    page = admin.get(f"/forms/{form_id}")
    assert "form-ai-assistant.js" not in page.text
    response = admin.post(f"/forms/{form_id}/ai-draft",
                          data={"csrf": csrf_of(page.text), "prompt": "Ein Formular"})
    assert response.status_code == 403
