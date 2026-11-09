"""Internal Anliegen: routing, task linkage, confidentiality and opt-in AI tests."""
from sqlalchemy import select

from app import ai_provider
from app.anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent
from app.db import Organization, SessionLocal, User
from app.org_models import OrgMembership, OrgRoleGrant
from app.security import hash_password
from app.task_models import Task
from conftest import login, csrf_of, settings

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
    lead = login("anliegen-supervisor@example.org", "test-anliegen-pass")
    assert lead.get(f"/anliegen/{cid}").status_code == 200
    manager_id = _user("anliegen-global-manager@example.org", "anliegen_submit,anliegen_manage,tasks_manage")
    manager = login("anliegen-global-manager@example.org", "test-anliegen-pass")
    assert manager.get(f"/anliegen/{cid}").status_code == 404
    assert "Vertrauliche Beschwerde" not in manager.get("/anliegen").text
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



def test_procurement_lifecycle_tracks_supplier_and_native_task():
    _enabled()
    _user("procurement-reporter@example.org")
    assignee = _user("procurement-recipient@example.org")
    cat_id = _cat("office_furniture")
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get("/anliegen/kategorien").text)
    assert admin.post(f"/anliegen/kategorien/{cat_id}", data={
        "csrf": csrf, "title": "Büromöbel", "routing": "person",
        "assignee_id": assignee, "procurement": "1", "enabled": "1",
    }).status_code == 303
    _, case_id = _post_case("procurement-reporter@example.org", cat_id,
                           "Drehstuhl bestellen", "Ein Drehstuhl mit verstellbarer Lehne wird benötigt.")
    receiver = login("procurement-recipient@example.org", "test-anliegen-pass")
    page = receiver.get("/anliegen?scope=orders&status=open")
    assert page.status_code == 200
    assert "Drehstuhl bestellen" in page.text
    assert "Beim Lieferanten bestellt" in page.text
    csrf = csrf_of(page.text)
    assert receiver.post(f"/anliegen/{case_id}/status", data={
        "csrf": csrf, "status": "ordered", "supplier_name": "Beispiel Lieferant",
        "order_reference": "BEST-0001", "return_to": "list",
    }).status_code == 303
    with SessionLocal() as db:
        case = db.get(Anliegen, case_id)
        task = db.get(Task, case.task_id)
        assert case.status == "ordered"
        assert case.supplier_name == "Beispiel Lieferant"
        assert case.order_reference == "BEST-0001"
        assert task.status == "in_progress"
    for state in ("partially_delivered", "delivered", "done"):
        result = receiver.post(f"/anliegen/{case_id}/status", data={
            "csrf": csrf, "status": state,
        })
        assert result.status_code == 303
    with SessionLocal() as db:
        case = db.get(Anliegen, case_id)
        assert case.status == "done" and db.get(Task, case.task_id).status == "done"
    assert "Beispiel Lieferant" in receiver.get(f"/anliegen/{case_id}").text


def test_saved_routing_rule_assigns_old_unassigned_and_supports_self_assignment():
    _enabled()
    sender_id = _user("routing-backlog@example.org")
    cat_id = _cat("office_supply")
    with SessionLocal() as db:
        cat = db.get(AnliegenCategory, cat_id)
        cat.assignee_id = None
        db.commit()
    sender, case_id = _post_case("routing-backlog@example.org", cat_id,
                                "Neues Papier", "Druckerpapier für das Büro fehlt.")
    with SessionLocal() as db:
        assert db.get(Anliegen, case_id).status == "unassigned"
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get("/anliegen/kategorien").text)
    changed = admin.post(f"/anliegen/kategorien/{cat_id}", data={
        "csrf": csrf, "title": "Büromaterial", "routing": "person",
        "assignee_id": sender_id, "procurement": "1", "enabled": "1",
    })
    assert changed.status_code == 303
    with SessionLocal() as db:
        case = db.get(Anliegen, case_id)
        assert case.assignee_id == sender_id and case.status == "open"
        assert case.task_id and db.get(Task, case.task_id).assignee_id == sender_id
    inbox = sender.get("/anliegen?scope=assigned")
    assert "Neues Papier" in inbox.text
    workplace = sender.get("/tasks?source=anliegen")
    assert workplace.status_code == 200
    assert "Neues Papier" in workplace.text


def test_reassignment_only_on_explicit_admin_action():
    _enabled()
    first = _user("routing-first@example.org")
    second = _user("routing-second@example.org")
    _user("routing-reporter@example.org")
    cat_id = _cat("defect")
    admin = login(*ADMIN)
    csrf = csrf_of(admin.get("/anliegen/kategorien").text)
    def save(assignee):
        return admin.post(f"/anliegen/kategorien/{cat_id}", data={
            "csrf": csrf, "title": "Mangel melden", "routing": "person",
            "assignee_id": assignee, "enabled": "1",
        })
    assert save(first).status_code == 303
    _, case_id = _post_case("routing-reporter@example.org", cat_id,
                           "Defekte Bürolampe", "Die Lampe lässt sich nicht mehr einschalten.")
    assert save(second).status_code == 303
    with SessionLocal() as db:
        assert db.get(Anliegen, case_id).assignee_id == first
    changed = admin.post(f"/anliegen/kategorien/{cat_id}/neuverteilen",
                         data={"csrf": csrf, "mode": "all_open"})
    assert changed.status_code == 303
    with SessionLocal() as db:
        case = db.get(Anliegen, case_id)
        assert case.assignee_id == second
        assert db.get(Task, case.task_id).assignee_id == second
        assert list(db.scalars(select(AnliegenEvent).where(
            AnliegenEvent.anliegen_id == case_id, AnliegenEvent.kind == "assignment")))


def test_platform_feedback_and_reviewed_text_are_saved_separately():
    _enabled()
    _user("anliegen-software@example.org")
    cat_id = _cat("platform_feedback")
    person = login("anliegen-software@example.org", "test-anliegen-pass")
    csrf = csrf_of(person.get("/anliegen/neu").text)
    result = person.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": cat_id, "title": "TAKT: Suchfilter verbessern",
        "description": "Mein ursprünglicher Bericht als einfacher Rohtext.",
        "description_final": "Im TAKT-Aufgabenbereich sollte der gewählte Filter erhalten bleiben.",
    })
    assert result.status_code == 303
    case_id = int(result.headers["location"].split("/")[-1])
    with SessionLocal() as db:
        case = db.get(Anliegen, case_id)
        assert case.category.key == "platform_feedback"
        assert case.description.startswith("Im TAKT-Aufgabenbereich")
        assert "ursprünglicher Bericht" not in case.description
    assert "TAKT &amp; Software verbessern" in person.get("/anliegen/neu").text


def test_non_procurement_category_rejects_supplier_order_status():
    _enabled()
    _user("anliegen-defect-reporter@example.org")
    assignee = _user("anliegen-defect-manager@example.org")
    cat_id = _cat("defect")
    with SessionLocal() as db:
        cat = db.get(AnliegenCategory, cat_id)
        cat.assignee_id = assignee
        cat.procurement = False
        db.commit()
    _, case_id = _post_case("anliegen-defect-reporter@example.org", cat_id,
                           "Meldung Heizung", "Die Heizung im Büro funktioniert nicht.")
    assigned = login("anliegen-defect-manager@example.org", "test-anliegen-pass")
    csrf = csrf_of(assigned.get(f"/anliegen/{case_id}").text)
    result = assigned.post(f"/anliegen/{case_id}/status",
                           data={"csrf": csrf, "status": "ordered"})
    assert result.status_code == 422
    with SessionLocal() as db:
        assert db.get(Anliegen, case_id).status == "open"
