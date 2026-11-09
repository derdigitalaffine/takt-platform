"""Internal Anliegen: routing, task linkage, confidentiality and opt-in AI tests."""
from sqlalchemy import select, delete
import pytest

from app import ai_provider
from app.anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent
from app.db import Organization, SessionLocal, User
from app.org_models import OrgMembership, OrgRoleGrant
from app.security import hash_password
from app.task_models import Task
from conftest import login, csrf_of, settings


@pytest.fixture(autouse=True)
def _isolate_anliegen_tests():
    """Reset feature switches, routing and native tasks after every Anliegen test."""
    from app import main
    from app.db import get_settings, set_setting, Organization
    from app.task_models import TaskActivity
    from app.ai_models import AIProvider
    from app.org_models import OrgMembership, OrgRoleGrant
    with SessionLocal() as db:
        settings_before = get_settings(db)
        original = {key: settings_before[key]
                    for key in ("module_anliegen", "module_tasks", "module_ai")}
        original_categories = {
            cat.id: (cat.title, cat.routing, cat.assignee_id, cat.enabled)
            for cat in db.scalars(select(AnliegenCategory))
        }
        existing_cases = set(db.scalars(select(Anliegen.id)))
        existing_orgs = set(db.scalars(select(Organization.id)))
    yield
    with SessionLocal() as db:
        new_cases = [row for row in db.scalars(select(Anliegen))
                     if row.id not in existing_cases]
        native_ids = [row.task_id for row in new_cases if row.task_id]
        for row in new_cases:
            db.execute(delete(AnliegenEvent).where(AnliegenEvent.anliegen_id == row.id))
            db.delete(row)
        db.flush()
        for tid in native_ids:
            db.execute(delete(TaskActivity).where(TaskActivity.task_id == tid))
            task = db.get(Task, tid)
            if task is not None:
                db.delete(task)
        db.execute(delete(AIProvider).where(AIProvider.name == "Anliegen AI Fake"))
        for category_id, values in original_categories.items():
            cat = db.get(AnliegenCategory, category_id)
            if cat:
                cat.title, cat.routing, cat.assignee_id, cat.enabled = values
        for org in list(db.scalars(select(Organization))):
            if org.id not in existing_orgs and org.name == "Anliegen Testorganisation":
                db.execute(delete(OrgRoleGrant).where(OrgRoleGrant.org_id == org.id))
                db.execute(delete(OrgMembership).where(OrgMembership.org_id == org.id))
                db.delete(org)
        for key, value in original.items():
            set_setting(db, key, value)
        db.commit()
    main._module_cache["at"] = 0.0

ADMIN = ("admin@example.org", "admin-passwort-123")


def _enabled():
    settings(module_anliegen="1", module_tasks="1", module_ai="1")


def _user(email: str, permissions="anliegen_submit"):
    with SessionLocal() as db:
        item = db.scalar(select(User).where(User.email == email))
        if item is None:
            item = User(email=email, name=email.split("@")[0],
                        password_hash=hash_password("test-anliegen-pass"),
                        permissions=permissions, active=True, is_admin=False,
                        must_change_password=False)
            db.add(item)
        item.permissions = permissions
        item.active, item.is_admin, item.must_change_password = True, False, False
        db.commit()
        return item.id


def _cat(key):
    with SessionLocal() as db:
        return db.scalar(select(AnliegenCategory).where(AnliegenCategory.key == key)).id


def _post_case(email, category_id, title="Papierbestellung", description="Wir benötigen neue Druckerpapierpakete."):
    c = login(email, "test-anliegen-pass")
    csrf = csrf_of(c.get("/anliegen/neu").text)
    r = c.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": category_id, "title": title,
        "description": description,
    })
    assert r.status_code == 303
    return c, int(r.headers["location"].split("/")[-1])


def test_module_is_off_by_default():
    settings(module_anliegen="0")
    c = login(*ADMIN)
    assert c.get("/anliegen").status_code == 404
    _enabled()
    assert c.get("/anliegen").status_code == 200
    assert "Interne Anliegen" in c.get("/admin/modules").text


def test_category_routes_to_correct_person_and_creates_native_task():
    _enabled()
    sender = _user("anliegen-sender@example.org")
    assignee = _user("anliegen-supply@example.org")
    cat_id = _cat("office_supply")
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get("/anliegen/kategorien").text)
    updated = admin.post(f"/anliegen/kategorien/{cat_id}", data={
        "csrf": csrf, "title": "Büromaterial", "routing": "person",
        "assignee_id": assignee, "enabled": "1",
    })
    assert updated.status_code == 303
    c, cid = _post_case("anliegen-sender@example.org", cat_id)
    with SessionLocal() as db:
        row = db.get(Anliegen, cid)
        assert row.reporter_id == sender and row.assignee_id == assignee
        assert row.task_id
        native = db.get(Task, row.task_id)
        assert native.source_type == "anliegen"
        assert native.source_id == str(cid)
        assert native.assignee_id == assignee
        assert native.creator_id == sender
        assert native.source_key == f"anliegen:{cid}"
    assert f"ANL-{cid:06d}" in c.get(f"/anliegen/{cid}").text
    outsider = _user("anliegen-outsider@example.org")
    other = login("anliegen-outsider@example.org", "test-anliegen-pass")
    assert other.get(f"/anliegen/{cid}").status_code == 404


def test_confidential_complaint_goes_only_to_explicit_org_lead_without_native_task():
    _enabled()
    reporter_id = _user("anliegen-complainant@example.org")
    lead_id = _user("anliegen-supervisor@example.org")
    cat_id = _cat("complaint")
    with SessionLocal() as db:
        org = Organization(name="Anliegen Testorganisation", kind="fachbereich")
        db.add(org)
        db.flush()
        db.add(OrgMembership(user_id=reporter_id, org_id=org.id, is_primary=True))
        db.add(OrgRoleGrant(user_id=lead_id, org_id=org.id, role="lead", include_children=True))
        db.commit()
    reporter, cid = _post_case("anliegen-complainant@example.org", cat_id,
                             "Vertrauliche Beschwerde", "Ich benötige ein vertrauliches Gespräch.")
    with SessionLocal() as db:
        row = db.get(Anliegen, cid)
        assert row.confidential and row.assignee_id == lead_id
        assert row.task_id is None
        assert row.title == "Vertrauliches Anliegen" and row.description == ""
        assert row.title_enc and row.description_enc
        assert "Vertrauliche Beschwerde" not in row.title_enc
        assert row.display_title == "Vertrauliche Beschwerde"
        assert row.display_description == "Ich benötige ein vertrauliches Gespräch."
    lead = login("anliegen-supervisor@example.org", "test-anliegen-pass")
    assert lead.get(f"/anliegen/{cid}").status_code == 200
    manager_id = _user("anliegen-global-manager@example.org", "anliegen_submit,anliegen_manage,tasks_manage")
    manager = login("anliegen-global-manager@example.org", "test-anliegen-pass")
    assert manager.get(f"/anliegen/{cid}").status_code == 404
    # Category names are public choices; protect the specific case and its contents.
    overview = manager.get("/anliegen").text
    assert f"/anliegen/{cid}" not in overview
    assert "Ich benötige ein vertrauliches Gespräch." not in overview
    # Administrators must not gain automatic read access to complaint narratives.
    admin = login(*ADMIN)
    assert admin.get(f"/anliegen/{cid}").status_code == 404


def test_missing_supervisor_never_routes_to_arbitrary_admin():
    _enabled()
    _user("anliegen-no-lead@example.org")
    cat_id = _cat("complaint")
    _, cid = _post_case("anliegen-no-lead@example.org", cat_id,
                        "Leitung fehlt", "Ich benötige eine zuständige Kontaktperson.")
    with SessionLocal() as db:
        row = db.get(Anliegen, cid)
        assert row.status == "unassigned" and row.assignee_id is None and row.task_id is None
    assert login(*ADMIN).get(f"/anliegen/{cid}").status_code == 404


def test_category_assignment_to_other_user_requires_management_permission():
    _enabled()
    _user("anliegen-unauthorized@example.org")
    cat_id = _cat("defect")
    c, cid = _post_case("anliegen-unauthorized@example.org", cat_id,
                       "Heizung defekt", "Die Heizung im Raum arbeitet nicht.")
    csrf = csrf_of(c.get(f"/anliegen/{cid}").text)
    assert c.post(f"/anliegen/{cid}/assign", data={
        "csrf": csrf, "assignee_id": 1,
    }).status_code == 403
    with SessionLocal() as db:
        assert db.get(Anliegen, cid).task_id is None


def test_ai_draft_requires_user_action_never_creates_a_case(monkeypatch):
    _enabled()
    _user("anliegen-ai-user@example.org", "anliegen_submit,ai_chat")
    from app.ai_models import AIProvider
    with SessionLocal() as db:
        profile = db.scalar(select(AIProvider).where(AIProvider.name == "Anliegen AI Fake"))
        if profile is None:
            profile = AIProvider(name="Anliegen AI Fake", base_url="https://llm.example.org/api",
                                 model_id="test-model", active=True)
            db.add(profile)
        profile.active = True
        db.commit()
    seen = {}
    async def fake_complete(provider, prompt, *, max_tokens=1024):
        seen["prompt"] = prompt
        return '{"title":"Stifte bestellen","description":"Es fehlen neue Kugelschreiber.","category":"office_supply"}'
    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    user = login("anliegen-ai-user@example.org", "test-anliegen-pass")
    csrf = csrf_of(user.get("/anliegen/neu").text)
    before = None
    with SessionLocal() as db:
        before = len(list(db.scalars(select(Anliegen).where(
            Anliegen.reporter_id == db.scalar(select(User.id).where(
                User.email == "anliegen-ai-user@example.org"))))))
    result = user.post("/anliegen/ki-entwurf", data={
        "csrf": csrf, "category_id": _cat("office_supply"),
        "text": "Kannst du bitte eine Meldung für fehlende Stifte schreiben?",
    })
    assert result.status_code == 200 and result.json()["title"] == "Stifte bestellen"
    assert seen["prompt"][-1]["role"] == "user"
    with SessionLocal() as db:
        after = len(list(db.scalars(select(Anliegen).where(
            Anliegen.reporter_id == db.scalar(select(User.id).where(
                User.email == "anliegen-ai-user@example.org"))))))
    assert after == before
    deny = user.post("/anliegen/ki-entwurf", data={
        "csrf": csrf, "category_id": _cat("complaint"),
        "text": "Ich möchte vertrauliche Details formulieren.",
    })
    assert deny.status_code == 403


def test_ordering_workflow_fast_actions_and_assignee_filters():
    _enabled()
    sender = _user("anliegen-order-sender@example.org")
    owner = _user("anliegen-order-manager@example.org")
    cat = _cat("office_furniture")
    admin = login(*ADMIN)
    token = csrf_of(admin.get("/anliegen/kategorien").text)
    change = admin.post(f"/anliegen/kategorien/{cat}", data={
        "csrf": token, "title": "Büromöbel", "routing": "person",
        "assignee_id": owner, "enabled": "1",
    })
    assert change.status_code == 303
    with SessionLocal() as db:
        assert db.get(AnliegenCategory, cat).assignee_id == owner
    preview_client = login("anliegen-order-sender@example.org", "test-anliegen-pass")
    preview = preview_client.get(f"/anliegen/empfaenger-vorschau?category_id={cat}")
    assert preview.status_code == 200
    assert preview.json()["ready"] is True
    assert "anliegen-order-manager" in preview.json()["recipient"]
    reporter, cid = _post_case(
        "anliegen-order-sender@example.org", cat, "Stuhl beschaffen",
        "Ein ergonomischer Bürostuhl wird benötigt.")
    recipient = login("anliegen-order-manager@example.org", "test-anliegen-pass")
    csrf = csrf_of(recipient.get(f"/anliegen/{cid}").text)
    assert f"Stuhl beschaffen" in recipient.get("/anliegen?view=mine").text
    assert "Stuhl beschaffen" in recipient.get("/anliegen?view=orders").text
    assert "Stuhl beschaffen" in recipient.get(
        f"/anliegen?view=orders&category_id={cat}&status=open&q=Stuhl").text
    ordered = recipient.post(f"/anliegen/{cid}/status", data={
        "csrf": csrf, "status": "ordered", "supplier": "Möbelpartner",
        "order_reference": "BEST-123", "expected_delivery": "2026-12-10",
        "back": "orders",
    })
    assert ordered.status_code == 303
    assert ordered.headers["location"] == "/anliegen?view=orders"
    with SessionLocal() as db:
        row = db.get(Anliegen, cid)
        assert row.status == "ordered"
        assert row.supplier == "Möbelpartner"
        assert row.order_reference == "BEST-123"
        assert row.expected_delivery_at.year == 2026
        assert db.get(Task, row.task_id).status == "in_progress"
    assert recipient.post(f"/anliegen/{cid}/status", data={
        "csrf": csrf, "status": "partially_delivered"}).status_code == 303
    assert recipient.post(f"/anliegen/{cid}/status", data={
        "csrf": csrf, "status": "delivered"}).status_code == 303
    assert recipient.post(f"/anliegen/{cid}/status", data={
        "csrf": csrf, "status": "done"}).status_code == 303
    with SessionLocal() as db:
        case = db.get(Anliegen, cid)
        assert case.status == "done" and case.delivered_at is not None
        assert db.get(Task, case.task_id).status == "done"
    assert "Interne Anliegen" in admin.get("/tasks").text
    assert 'href="/anliegen/neu"' in admin.get("/tasks").text


def test_admin_can_explicitly_migrate_open_orders_to_new_recipient():
    _enabled()
    old_owner = _user("anliegen-old-owner@example.org")
    new_owner = _user("anliegen-new-owner@example.org")
    _user("anliegen-reporter-migrate@example.org")
    cat = _cat("office_supply")
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get("/anliegen/kategorien").text)
    first = admin.post(f"/anliegen/kategorien/{cat}", data={
        "csrf": csrf, "title": "Büromaterial", "routing": "person",
        "assignee_id": old_owner, "enabled": "1",
    })
    assert first.status_code == 303
    _, cid = _post_case("anliegen-reporter-migrate@example.org", cat)
    change = admin.post(f"/anliegen/kategorien/{cat}", data={
        "csrf": csrf, "title": "Büromaterial", "routing": "person",
        "assignee_id": new_owner, "enabled": "1", "apply_open": "1",
    })
    assert change.status_code == 303
    with SessionLocal() as db:
        case = db.get(Anliegen, cid)
        assert case.assignee_id == new_owner
        assert db.get(Task, case.task_id).assignee_id == new_owner
    assigned = login("anliegen-new-owner@example.org", "test-anliegen-pass")
    assert assigned.get(f"/anliegen/{cid}").status_code == 200
    old = login("anliegen-old-owner@example.org", "test-anliegen-pass")
    assert old.get(f"/anliegen/{cid}").status_code == 404


def test_platform_feedback_category_and_non_order_status_restrictions():
    _enabled()
    _user("anliegen-software@example.org")
    cat = _cat("platform_feedback")
    sender, cid = _post_case(
        "anliegen-software@example.org", cat,
        "TAKT Suche verbessern", "Die Suche in der TAKT-Plattform soll schneller werden.")
    assert "TAKT verbessern" in sender.get("/anliegen/neu").text
    csrf = csrf_of(sender.get(f"/anliegen/{cid}").text)
    response = sender.post(f"/anliegen/{cid}/status", data={
        "csrf": csrf, "status": "ordered"})
    assert response.status_code in (403, 422)



def test_description_first_form_keeps_original_and_persists_user_reviewed_text():
    """The prominent raw description stays untouched until the user confirms."""
    _enabled()
    _user("anliegen-review-editor@example.org")
    category = _cat("platform_feedback")
    c = login("anliegen-review-editor@example.org", "test-anliegen-pass")
    page = c.get("/anliegen/neu")
    assert page.status_code == 200
    assert 'id="anliegen-description"' in page.text
    assert 'id="anliegen-review"' in page.text  # manual path works even without ai_chat
    assert 'name="description_final"' in page.text
    assert 'id="anliegen-recipient-preview"' in page.text
    assert '/static/anliegen-intake.css' in page.text
    csrf = csrf_of(page.text)
    created = c.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": category,
        "title": "TAKT-Filter optimieren",
        "description": "Rohtext des Meldenden bleibt unangetastet.",
        "description_final": "In der TAKT-Aufgabenliste soll die Filterauswahl beim Zurücknavigieren erhalten bleiben.",
    })
    assert created.status_code == 303
    case_id = int(created.headers["location"].split("/")[-1])
    with SessionLocal() as db:
        case = db.get(Anliegen, case_id)
        assert case.description.startswith("In der TAKT-Aufgabenliste")
        assert "Rohtext" not in case.description


def test_description_first_javascript_does_not_submit_ai_result():
    from pathlib import Path
    asset = (Path(__file__).resolve().parents[1] / "app" / "static" / "anliegen.js").read_text()
    assert "new AbortController()" in asset
    assert "finalBody.value = draft.description" in asset
    assert "previewRecipient()" in asset
    assert "form.submit(" not in asset
    assert "No automatic submission" in asset or "no auto" in asset or "original" in asset.lower()


def test_intake_starts_with_one_prompt_and_manual_editor_is_disclosed():
    _enabled()
    _user("anliegen-intake-ux@example.org", "anliegen_submit,ai_chat")
    c = login("anliegen-intake-ux@example.org", "test-anliegen-pass")
    page = c.get("/anliegen/neu")
    assert page.status_code == 200
    html = page.text
    assert 'id="anliegen-description"' in html
    assert 'id="anliegen-ai"' in html
    assert 'id="anliegen-review"' in html
    assert "Ohne KI erfassen" in html
    assert 'name="description_final"' in html
    assert "Mit KI Vorschlag erstellen" in html
    assert 'data-confidential="1"' in html
    assert "/static/anliegen-intake.css" in html


def test_manual_without_ai_saves_only_reviewed_content():
    _enabled()
    _user("anliegen-manual-only@example.org", "anliegen_submit")
    settings(module_ai="0")
    c = login("anliegen-manual-only@example.org", "test-anliegen-pass")
    page = c.get("/anliegen/neu")
    assert page.status_code == 200
    assert 'id="anliegen-review"' in page.text and 'open' in page.text
    assert 'id="anliegen-ai"' not in page.text
    csrf = csrf_of(page.text)
    response = c.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": _cat("platform_feedback"),
        "title": "TAKT-Suche optimieren",
        "description": "",
        "description_final": "Bei der Suche im TAKT-Portal soll die Filterauswahl erhalten bleiben.",
    })
    assert response.status_code == 303
    case_id = int(response.headers["location"].rsplit("/", 1)[1])
    with SessionLocal() as db:
        row = db.get(Anliegen, case_id)
        assert row.category.key == "platform_feedback"
        assert row.description == "Bei der Suche im TAKT-Portal soll die Filterauswahl erhalten bleiben."


def test_reported_and_assigned_are_separate_and_orders_belong_to_recipient():
    _enabled()
    _user("anliegen-reporter-tabs@example.org")
    recipient_id = _user("anliegen-owner-tabs@example.org")
    cat_id = _cat("office_supply")
    with SessionLocal() as db:
        cat = db.get(AnliegenCategory, cat_id)
        cat.assignee_id = recipient_id
        cat.routing = "person"
        cat.enabled = True
        db.commit()
    reporter, case_id = _post_case("anliegen-reporter-tabs@example.org", cat_id,
                                   "Papier für die Außenstelle", "Für die Außenstelle werden Papierpakete benötigt.")
    assignee = login("anliegen-owner-tabs@example.org", "test-anliegen-pass")
    mine = reporter.get("/anliegen")
    assert mine.status_code == 200
    assert "Von mir eingereichte Anliegen" in mine.text
    assert "Papier für die Außenstelle" in mine.text
    assert "Status ansehen" in mine.text
    assert "Papier für die Außenstelle" not in reporter.get("/anliegen?view=mine").text
    assigned = assignee.get("/anliegen?view=mine")
    assert assigned.status_code == 200
    assert "Mir zugewiesene Anliegen" in assigned.text
    assert "Papier für die Außenstelle" in assigned.text
    assert "Papier für die Außenstelle" in assignee.get("/anliegen?view=orders").text
    assert "Papier für die Außenstelle" not in assignee.get("/anliegen?view=reported").text
    assert "Papier für die Außenstelle" not in reporter.get("/anliegen?view=orders").text
    assert assignee.get(f"/anliegen/{case_id}").status_code == 200


def test_recipient_with_only_object_access_can_open_and_process():
    _enabled()
    _user("anliegen-sender-object@example.org")
    recipient_id = _user("anliegen-processor-object@example.org", "")
    cat_id = _cat("defect")
    with SessionLocal() as db:
        cat = db.get(AnliegenCategory, cat_id)
        cat.assignee_id = recipient_id
        cat.routing = "person"
        cat.enabled = True
        db.commit()
    _, cid = _post_case("anliegen-sender-object@example.org", cat_id,
                       "Störung im Büro", "Die Beleuchtung im Büro funktioniert nicht mehr.")
    assignee = login("anliegen-processor-object@example.org", "test-anliegen-pass")
    view = assignee.get("/anliegen?view=mine")
    assert view.status_code == 200
    assert "Störung im Büro" in view.text
    detail = assignee.get(f"/anliegen/{cid}")
    assert detail.status_code == 200
    assert assignee.get("/anliegen/neu").status_code == 403
    csrf = csrf_of(detail.text)
    changed = assignee.post(f"/anliegen/{cid}/status", data={
        "csrf": csrf, "status": "in_progress",
    })
    assert changed.status_code == 303
    with SessionLocal() as db:
        assert db.get(Anliegen, cid).status == "in_progress"


def test_intake_javascript_does_not_auto_submit_and_rejects_stale_drafts():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "app" / "static" / "anliegen.js").read_text()
    assert "new AbortController()" in script
    assert "description_final" not in script or "finalBody" in script
    assert "input !== prompt.value.trim()" in script
    assert "editVersion !== initialVersion" in script
    assert "details.open = true" in script
    assert "form.submit(" not in script
