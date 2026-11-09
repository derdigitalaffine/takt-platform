"""Interne Anliegen: routing, confidential content, task integration and AI draft."""
from sqlalchemy import select
import pytest

from app import ai_provider
from app.concern_models import Concern, ConcernCategory
from app.db import Organization, SessionLocal, User
from app.org_models import OrgMembership, OrgRoleGrant
from app.security import hash_password
from app.task_models import Task
from conftest import login, settings, csrf_of


@pytest.fixture(autouse=True)
def _remove_test_concerns():
    """Keep tests deterministic: no new native tasks survive into other test modules."""
    with SessionLocal() as db:
        initial_concerns = set(db.scalars(select(Concern.id)))
        initial_tasks = set(db.scalars(select(Task.id)))
    yield
    with SessionLocal() as db:
        new_concerns = list(db.scalars(select(Concern).where(
            Concern.id.not_in(initial_concerns)))) if initial_concerns else list(db.scalars(select(Concern)))
        new_tasks = list(db.scalars(select(Task).where(
            Task.id.not_in(initial_tasks)))) if initial_tasks else list(db.scalars(select(Task)))
        # Release the concern->task foreign key before deleting its task.
        for item in new_concerns:
            db.delete(item)
        db.flush()
        for task in new_tasks:
            db.delete(task)
        db.commit()


def _staff(email: str, permissions: str = "") -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=email.split("@")[0],
                        password_hash=hash_password("intern-passwort-123"),
                        active=True, must_change_password=False,
                        permissions=permissions)
            db.add(user)
            db.flush()
        user.permissions = permissions
        user.active, user.is_admin, user.must_change_password = True, False, False
        uid = user.id
        db.commit()
        return uid


def _category(name, responsible_id=None, *, complaint=False):
    with SessionLocal() as db:
        item = ConcernCategory(
            title=name, kind="complaint" if complaint else "supplies",
            routing="lead" if complaint else "person",
            responsible_id=responsible_id,
            confidential=complaint, active=True, position=100,
        )
        db.add(item)
        db.commit()
        return item.id


def _enable():
    settings(module_tasks="1", module_concerns="1")


def test_module_disabled_and_default_categories_seeded():
    settings(module_concerns="0", module_tasks="1")
    c = login("admin@example.org", "admin-passwort-123")
    assert c.get("/anliegen").status_code == 404
    assert c.get("/admin/anliegen").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(ConcernCategory.id).where(
            ConcernCategory.kind == "complaint")) is not None


def test_manual_intake_creates_native_task_without_task_creation_permission():
    _enable()
    recipient = _staff("concerns-supplies@example.org")
    reporter = _staff("concerns-reporter@example.org")
    category_id = _category("Fachlicher Bürobedarf", recipient)
    c = login("concerns-reporter@example.org", "intern-passwort-123")
    page = c.get("/anliegen/neu")
    assert page.status_code == 200
    csrf = csrf_of(page.text)
    submit = c.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": category_id,
        "title": "Büromaterial bestellen",
        "description": "Wir benötigen zwei Pakete Recyclingpapier."
    })
    assert submit.status_code == 303
    ref_id = int(submit.headers["location"].split("/")[-1])
    with SessionLocal() as db:
        item = db.get(Concern, ref_id)
        assert item.reporter_id == reporter and item.assignee_id == recipient
        assert item.task_id
        task = db.get(Task, item.task_id)
        assert task.creator_id == reporter and task.assignee_id == recipient
        assert task.source_type == "concern" and "Recyclingpapier" in task.description
    assert "Büromaterial bestellen" in c.get(f"/anliegen/{ref_id}").text
    unrelated = _staff("concerns-other@example.org")
    other = login("concerns-other@example.org", "intern-passwort-123")
    assert other.get(f"/anliegen/{ref_id}").status_code == 404
    assigned = login("concerns-supplies@example.org", "intern-passwort-123")
    assert assigned.get(f"/anliegen/{ref_id}").status_code == 200


def test_complaint_routes_to_direct_org_lead_with_neutral_task():
    _enable()
    reporter_id = _staff("concerns-complaint-reporter@example.org")
    leader_id = _staff("concerns-complaint-lead@example.org")
    _staff("concerns-complaint-unrelated@example.org", "tasks_manage")
    with SessionLocal() as db:
        org = Organization(name="Fachbereich Anliegen Test", kind="fachbereich", active=True)
        db.add(org)
        db.flush()
        org_id = org.id
        db.add(OrgMembership(user_id=reporter_id, org_id=org_id, is_primary=True))
        db.add(OrgRoleGrant(org_id=org_id, user_id=leader_id, role="lead"))
        db.commit()
    category_id = _category("Vorgesetztenbeschwerde Test", complaint=True)
    c = login("concerns-complaint-reporter@example.org", "intern-passwort-123")
    csrf = csrf_of(c.get("/anliegen/neu").text)
    res = c.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": category_id,
        "title": "Vertrauliches Führungsanliegen",
        "description": "Der vertrauliche Sachverhalt betrifft personelle Abläufe."
    })
    assert res.status_code == 303
    item_id = int(res.headers["location"].split("/")[-1])
    with SessionLocal() as db:
        item = db.get(Concern, item_id)
        task = db.get(Task, item.task_id)
        assert item.confidential and item.assignee_id == leader_id
        assert task.creator_id == leader_id
        assert "personelle Abläufe" not in task.title + task.description
        assert "concerns-complaint-reporter@example.org" not in task.title + task.description
        assert "/anliegen/" in task.description
    unrelated = login("concerns-complaint-unrelated@example.org", "intern-passwort-123")
    assert unrelated.get(f"/anliegen/{item_id}").status_code == 404
    leader = login("concerns-complaint-lead@example.org", "intern-passwort-123")
    assert "personelle Abläufe" in leader.get(f"/anliegen/{item_id}").text


def test_complaint_without_defined_supervisor_remains_unsubmitted():
    _enable()
    _staff("concerns-no-lead@example.org")
    category_id = _category("Beschwerde ohne Teamleitung", complaint=True)
    c = login("concerns-no-lead@example.org", "intern-passwort-123")
    csrf = csrf_of(c.get("/anliegen/neu").text)
    res = c.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": category_id,
        "title": "Bitte prüfen",
        "description": "Es gibt einen Sachverhalt ohne definierte Zuständigkeit.",
    })
    assert res.status_code == 422
    assert "primäre Organisationseinheit" in res.text or "vorgesetzte Person" in res.text


def test_ai_draft_needs_explicit_consent_and_never_creates_task(monkeypatch):
    _enable()
    settings(module_ai="1")
    _staff("concerns-ai@example.org", "ai_chat")
    from app.ai_models import AIProvider
    with SessionLocal() as db:
        provider = AIProvider(name="concerns-test", base_url="https://llm.example.org/api",
                              model_id="test-model", active=True)
        db.add(provider)
        cat = db.scalar(select(ConcernCategory).where(ConcernCategory.kind == "supplies"))
        db.commit()
        cat_id = cat.id
    async def fake_complete(provider, messages, **kwargs):
        assert 'keine Aufgaben erstellen' in messages[0]["content"]
        return '{"title":"Papier nachbestellen","description":"Es fehlen zwei Pakete Papier im Büro.","category_id":' + str(cat_id) + '}'
    monkeypatch.setattr(ai_provider, "complete", fake_complete)
    c = login("concerns-ai@example.org", "intern-passwort-123")
    csrf = csrf_of(c.get("/anliegen/neu").text)
    count = lambda db: len(list(db.scalars(select(Concern))))
    with SessionLocal() as db:
        before = count(db)
    refused = c.post("/anliegen/ki-entwurf", data={
        "csrf": csrf, "description": "Im Büro fehlen zwei Pakete Papier."
    })
    assert refused.status_code == 422
    proposed = c.post("/anliegen/ki-entwurf", data={
        "csrf": csrf, "consent": "1",
        "description": "Im Büro fehlen zwei Pakete Papier.",
    })
    assert proposed.status_code == 200
    assert "Papier nachbestellen" in proposed.text
    with SessionLocal() as db:
        assert count(db) == before
