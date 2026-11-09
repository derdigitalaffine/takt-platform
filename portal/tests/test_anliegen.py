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
def _isolate_internal_request_tests():
    """No native tasks or feature flags may leak into unrelated test modules."""
    from app.db import get_settings, set_setting
    from app import main
    from app.anliegen_models import AnliegenEvent
    from app.ai_models import AIProvider
    with SessionLocal() as db:
        cfg = get_settings(db)
        original = {key: cfg[key] for key in ("module_anliegen", "module_tasks", "module_ai")}
        categories = {
            c.id: (c.title, c.routing, c.assignee_id, c.enabled)
            for c in db.scalars(select(AnliegenCategory))
        }
    yield
    with SessionLocal() as db:
        db.execute(delete(AnliegenEvent))
        db.execute(delete(Anliegen))
        db.execute(delete(Task).where(Task.source_type == "anliegen"))
        for cid, (title, routing, assignee_id, enabled) in categories.items():
            c = db.get(AnliegenCategory, cid)
            if c:
                c.title = title
                c.routing = routing
                c.assignee_id = assignee_id
                c.enabled = enabled
        db.execute(delete(AIProvider).where(AIProvider.name == "Anliegen AI Fake"))
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
        assert row.title == "Vertrauliches Anliegen"
        assert row.description == ""
        assert row.title_enc and row.description_enc
        assert row.display_title == "Vertrauliche Beschwerde"
        assert row.display_description == "Ich benötige ein vertrauliches Gespräch."
        assert "Vertrauliche Beschwerde" not in row.title_enc
        assert "vertrauliches Gespräch" not in row.description_enc
    detail_html = reporter.get(f"/anliegen/{cid}").text
    assert "Ich benötige ein vertrauliches Gespräch." in detail_html
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
