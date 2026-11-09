"""End-to-end rule administration, launch and authorization for internal processes."""
import json
import re
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app import anliegen as cases
from app import anliegen_process_config as config
from app import anliegen_processes as policies
from app.anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent
from app.anliegen_process_models import (
    AnliegenProcessRule, AnliegenProcessRun, AnliegenProcessTask, AnliegenProcessAudit,
    AnliegenProcessRuleEvent,
)
from app.db import (Organization, Process, ProcessVersion, SessionLocal, Setting,
                    User, get_settings, set_setting)
from app.org_models import OrgMembership, OrgRoleGrant
from app.security import hash_password
from app.task_models import Task, TaskActivity
from conftest import csrf_of, login, settings


PASSWORD = "process-tests-Secret-123"
ADMIN = ("admin@example.org", "admin-passwort-123")


def _unique(label):
    return f"anliegen-process-{label}-{uuid4().hex[:10]}@example.org"


@pytest.fixture
def bundle():
    from app import main
    with SessionLocal() as db:
        state = get_settings(db)
        flags = {k: (db.get(Setting, k).value if db.get(Setting, k) else None)
                 for k in ("module_anliegen", "module_tasks",
                           "anliegen_process_integration_enabled")}
        set_setting(db, "module_anliegen", "1")
        set_setting(db, "module_tasks", "0")
        flag = db.get(Setting, "anliegen_process_integration_enabled")
        if flag:
            flag.value = "0"
        org = Organization(name=f"Anliegen Prozess Test {uuid4().hex}", kind="fachbereich", active=True)
        db.add(org)
        db.flush()
        def user(label, permissions):
            row = User(email=_unique(label), name=f"Test {label}",
                       password_hash=hash_password(PASSWORD),
                       permissions=permissions, active=True, is_admin=False,
                       must_change_password=False)
            db.add(row)
            db.flush()
            return row
        author = user("author", "anliegen_process_configure,processes")
        approver = user("approver", "anliegen_process_approve")
        reporter = user("reporter", "anliegen_submit,anliegen_process_start")
        handler = user("handler", "anliegen_process_start,anliegen_process_work,anliegen_submit")
        stranger = user("stranger", "anliegen_submit,anliegen_process_start")
        db.add_all([
            OrgMembership(user_id=reporter.id, org_id=org.id, is_primary=True),
            OrgRoleGrant(org_id=org.id, user_id=author.id, role="planner"),
            OrgRoleGrant(org_id=org.id, user_id=approver.id, role="approver"),
        ])
        cat = AnliegenCategory(
            key=f"test_proc_{uuid4().hex}", title="Beschaffung Testprojekt",
            description="Nur Integrationstest", tags="hardware",
            routing="person", assignee_id=handler.id,
            enabled=True, confidential=False, position=2000)
        proc = Process(name="Monitorfreigabe Test", owner_id=author.id,
                       draft_json="{}")
        db.add_all([cat, proc])
        db.flush()
        version = ProcessVersion(
            process_id=proc.id, version=1,
            definition_json=json.dumps({"steps": [
                {"id": "review", "name": "Beschaffung prüfen", "type": "task",
                 "assign": {"mode": "case"}, "status": "",
                 "checklist": ["Bedarf geprüft"],
                 "fields": [{"key": "cost", "label": "Kosten", "type": "number",
                             "required": True, "options": []}]},
                {"id": "finish", "name": "Freigabe", "type": "approval", "status": "",
                 "assign": {"mode": "case"}, "four_eyes": False, "on_reject": "end"},
            ]}))
        db.add(version)
        db.commit()
        data = dict(org_id=org.id, cat_id=cat.id, process_id=proc.id,
                    version_id=version.id, author_id=author.id,
                    approver_id=approver.id, reporter_id=reporter.id,
                    handler_id=handler.id, stranger_id=stranger.id,
                    author_email=author.email, approver_email=approver.email,
                    reporter_email=reporter.email, handler_email=handler.email,
                    stranger_email=stranger.email, flags=flags)
    main._module_cache["at"] = 0.0
    yield data
    with SessionLocal() as db:
        cases_rows = list(db.scalars(select(Anliegen).where(
            Anliegen.category_id == data["cat_id"])))
        case_ids = [c.id for c in cases_rows]
        case_task_ids = [c.task_id for c in cases_rows if c.task_id]
        run_ids = list(db.scalars(select(AnliegenProcessRun.id).where(
            AnliegenProcessRun.anliegen_id.in_(case_ids)))) if case_ids else []
        rule_ids = list(db.scalars(select(AnliegenProcessRule.id).where(
            AnliegenProcessRule.category_id == data["cat_id"])))
        if run_ids:
            db.execute(delete(AnliegenProcessTask).where(
                AnliegenProcessTask.run_id.in_(run_ids)))
            db.execute(delete(AnliegenProcessAudit).where(
                AnliegenProcessAudit.run_id.in_(run_ids)))
            db.execute(delete(AnliegenProcessRun).where(
                AnliegenProcessRun.id.in_(run_ids)))
        if rule_ids:
            db.execute(delete(AnliegenProcessRuleEvent).where(
                AnliegenProcessRuleEvent.rule_id.in_(rule_ids)))
            db.execute(delete(AnliegenProcessRule).where(
                AnliegenProcessRule.id.in_(rule_ids)))
        if case_ids:
            db.execute(delete(AnliegenEvent).where(
                AnliegenEvent.anliegen_id.in_(case_ids)))
            db.execute(delete(Anliegen).where(Anliegen.id.in_(case_ids)))
        if case_task_ids:
            db.execute(delete(TaskActivity).where(TaskActivity.task_id.in_(case_task_ids)))
            db.execute(delete(Task).where(Task.id.in_(case_task_ids)))
        db.execute(delete(ProcessVersion).where(
            ProcessVersion.process_id == data["process_id"]))
        db.execute(delete(Process).where(Process.id == data["process_id"]))
        db.execute(delete(AnliegenCategory).where(AnliegenCategory.id == data["cat_id"]))
        db.execute(delete(OrgRoleGrant).where(OrgRoleGrant.org_id == data["org_id"]))
        db.execute(delete(OrgMembership).where(OrgMembership.org_id == data["org_id"]))
        db.execute(delete(Organization).where(Organization.id == data["org_id"]))
        db.execute(delete(User).where(User.id.in_((
            data["author_id"], data["approver_id"], data["reporter_id"],
            data["handler_id"], data["stranger_id"]))))
        for key, val in data["flags"].items():
            item = db.get(Setting, key)
            if val is None:
                if item is not None:
                    db.delete(item)
            else:
                if item is None:
                    db.add(Setting(key=key, value=val))
                else:
                    item.value = val
        db.commit()
    main._module_cache["at"] = 0.0


def _client(data, role):
    return login(data[f"{role}_email"], PASSWORD)


def _csrf(client, path):
    page = client.get(path)
    assert page.status_code == 200, (page.status_code, path, page.text[:250])
    return csrf_of(page.text)


def _flag_enabled():
    with SessionLocal() as db:
        flag = db.get(Setting, "anliegen_process_integration_enabled")
        if flag is None:
            db.add(Setting(key="anliegen_process_integration_enabled", value="1"))
        else:
            flag.value = "1"
        db.commit()


def _policy(*modes, approval=True):
    return dict(start_modes=list(modes), approval_required=approval,
                completion="manual", agent_autonomy="off", field_mapping=[],
                dependencies=[])


def _rule(db, data, actor_id, *, modes=("submit", "handler"), approval=True,
          state="active"):
    actor = db.get(User, actor_id)
    rule = config.create_draft(db, actor, data["cat_id"],
                               data["process_id"], data["org_id"],
                               _policy(*modes, approval=approval))
    if state in ("review", "active"):
        config.submit_review(db, rule, actor, expected=rule.state_version)
    if state == "active":
        reviewer = db.get(User, data["approver_id"])
        config.approve(db, rule, reviewer, expected=rule.state_version)
    db.flush()
    return rule


def _new_case(client, data, *, rule_id=0, token=None):
    page = client.get("/anliegen/neu")
    assert page.status_code == 200
    csrf = csrf_of(page.text)
    submitted = client.post("/anliegen/neu", data={
        "csrf": csrf, "category_id": data["cat_id"],
        "title": "Zwei neue Monitore", "description_final": "Zwei neue Monitore für den Bereich",
        "process_rule_id": str(rule_id), "process_token": token or uuid4().hex})
    return submitted


def test_disabled_default_blocks_process_starts_and_keeps_intake(bundle):
    admin = login(*ADMIN)
    p = admin.get("/anliegen/prozesse")
    assert p.status_code == 200 and "Deaktiviert" in p.text
    with SessionLocal() as db:
        rule = _rule(db, bundle, bundle["author_id"])
        db.commit()
        rid = rule.id
    reporter = _client(bundle, "reporter")
    page = reporter.get("/anliegen/neu")
    assert page.status_code == 200
    assert 'id="anliegen-process-select"' not in page.text
    forbidden = _new_case(reporter, bundle, rule_id=rid)
    assert forbidden.status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(Anliegen.id).where(
            Anliegen.category_id == bundle["cat_id"])) is None
    ordinary = _new_case(reporter, bundle)
    assert ordinary.status_code == 303
    with SessionLocal() as db:
        assert db.scalar(select(AnliegenProcessRun.id).join(
            Anliegen, AnliegenProcessRun.anliegen_id == Anliegen.id).where(
            Anliegen.category_id == bundle["cat_id"])) is None


def test_rule_lifecycle_http_and_pinned_version(bundle):
    author = _client(bundle, "author")
    reviewer = _client(bundle, "approver")
    own_page = author.get("/anliegen/prozesse")
    assert own_page.status_code == 200 and "Neue Prozesszuordnung" in own_page.text
    csrf = csrf_of(own_page.text)
    created = author.post("/anliegen/prozesse/neu", data={
        "csrf": csrf, "category_id": bundle["cat_id"],
        "process_id": bundle["process_id"], "org_id": bundle["org_id"],
        "start_modes": ["submit", "handler"], "approval_required": "1",
        "completion": "manual"})
    assert created.status_code == 303
    with SessionLocal() as db:
        rule = db.scalar(select(AnliegenProcessRule).where(
            AnliegenProcessRule.category_id == bundle["cat_id"]))
        rid = rule.id
        assert rule.state == "draft" and rule.revision == 1
    assert author.post(f"/anliegen/prozesse/{rid}", data={
        "csrf": csrf, "action": "review", "state_version": "0"}).status_code == 303
    forbidden = author.post(f"/anliegen/prozesse/{rid}", data={
        "csrf": csrf, "action": "approve", "state_version": "1"})
    assert forbidden.status_code == 403
    other_csrf = _csrf(reviewer, "/anliegen/prozesse")
    activated = reviewer.post(f"/anliegen/prozesse/{rid}", data={
        "csrf": other_csrf, "action": "approve", "state_version": "1"})
    assert activated.status_code == 303
    with SessionLocal() as db:
        rule = db.get(AnliegenProcessRule, rid)
        assert rule.state == "active"
        assert rule.process_version_id == bundle["version_id"]
        assert rule.approved_by_id == bundle["approver_id"]
        assert len(list(db.scalars(select(AnliegenProcessRuleEvent).where(
            AnliegenProcessRuleEvent.rule_id == rid)))) == 3
    _flag_enabled()
    reporter = _client(bundle, "reporter")
    assert 'id="anliegen-process-select"' in reporter.get("/anliegen/neu").text
    posted = _new_case(reporter, bundle, rule_id=rid)
    assert posted.status_code == 303
    cid = int(posted.headers["location"].split("/")[-1])
    with SessionLocal() as db:
        run = db.scalar(select(AnliegenProcessRun).where(
            AnliegenProcessRun.anliegen_id == cid))
        assert run and run.state == "requested"
        assert run.process_version_id == bundle["version_id"]
        assert db.scalar(select(AnliegenProcessTask.id).where(
            AnliegenProcessTask.run_id == run.id)) is None
    approvals = reviewer.get("/anliegen/prozessfreigaben")
    assert approvals.status_code == 200
    assert f"ANL-{cid:06d}" in approvals.text
    assert "Zwei neue Monitore für den Bereich" not in approvals.text
    approved = reviewer.post(f"/anliegen/prozessfreigaben/{run.id}", data={
        "csrf": csrf_of(approvals.text)})
    assert approved.status_code == 303
    with SessionLocal() as db:
        run = db.get(AnliegenProcessRun, run.id)
        assert run.state == "running"
        first = db.scalar(select(AnliegenProcessTask).where(
            AnliegenProcessTask.run_id == run.id))
        assert first and first.assignee_id == bundle["handler_id"]
    handler = _client(bundle, "handler")
    page = handler.get(f"/anliegen/{cid}")
    assert page.status_code == 200 and "Beschaffung prüfen" in page.text
    submitted = handler.post(f"/anliegen/{cid}/prozesse/{run.id}/aufgabe/{first.id}", data={
        "csrf": csrf_of(page.text), "checks": ["Bedarf geprüft"],
        "field_cost": "90", "outcome": "done"})
    assert submitted.status_code == 303
    with SessionLocal() as db:
        run = db.get(AnliegenProcessRun, run.id)
        approval_step = db.scalar(select(AnliegenProcessTask).where(
            AnliegenProcessTask.run_id == run.id,
            AnliegenProcessTask.kind == "approval"))
        assert approval_step and approval_step.state == "open"
    second = handler.post(
        f"/anliegen/{cid}/prozesse/{run.id}/aufgabe/{approval_step.id}",
        data={"csrf": csrf_of(handler.get(f"/anliegen/{cid}").text),
              "outcome": "approved"})
    assert second.status_code == 303
    with SessionLocal() as db:
        assert db.get(AnliegenProcessRun, run.id).state == "done"


def test_four_eyes_review_versioning_stale_and_supersede(bundle):
    author = _client(bundle, "author")
    reviewer = _client(bundle, "approver")
    with SessionLocal() as db:
        rule = _rule(db, bundle, bundle["author_id"])
        db.commit()
        rid = rule.id
    csrf = _csrf(author, "/anliegen/prozesse")
    clone = author.post(f"/anliegen/prozesse/{rid}", data={
        "csrf": csrf, "action": "revise", "state_version": "2"})
    assert clone.status_code == 303
    with SessionLocal() as db:
        new = db.scalar(select(AnliegenProcessRule).where(
            AnliegenProcessRule.category_id == bundle["cat_id"],
            AnliegenProcessRule.revision == 2))
        assert new and new.state == "draft" and new.id != rid
        new_id = new.id
    assert author.post(f"/anliegen/prozesse/{new_id}", data={
        "csrf": csrf, "action": "update", "state_version": "1",
        "start_modes": ["handler"], "approval_required": "1",
        "completion": "manual"}).status_code == 409
    saved = author.post(f"/anliegen/prozesse/{new_id}", data={
        "csrf": csrf, "action": "update", "state_version": "0",
        "start_modes": ["handler"], "approval_required": "1",
        "completion": "manual"})
    assert saved.status_code == 303
    assert author.post(f"/anliegen/prozesse/{new_id}", data={
        "csrf": csrf, "action": "review", "state_version": "1"}).status_code == 303
    rcsrf = _csrf(reviewer, "/anliegen/prozesse")
    assert reviewer.post(f"/anliegen/prozesse/{new_id}", data={
        "csrf": rcsrf, "action": "approve", "state_version": "2"}).status_code == 303
    with SessionLocal() as db:
        old, current = db.get(AnliegenProcessRule, rid), db.get(AnliegenProcessRule, new_id)
        assert old.state == "retired" and current.state == "active"
        assert current.revision == 2
    retired = reviewer.post(f"/anliegen/prozesse/{new_id}", data={
        "csrf": rcsrf, "action": "retire", "state_version": "3"})
    assert retired.status_code == 303
    with SessionLocal() as db:
        assert db.get(AnliegenProcessRule, new_id).state == "retired"


def test_cross_organization_and_unrelated_users_cannot_configure_or_approve(bundle):
    stranger = _client(bundle, "stranger")
    author = _client(bundle, "author")
    with SessionLocal() as db:
        rule = _rule(db, bundle, bundle["author_id"], state="review")
        db.commit()
        rid = rule.id
    assert stranger.get("/anliegen/prozesse").status_code == 403
    assert stranger.post(f"/anliegen/prozesse/{rid}", data={
        "csrf": _csrf(stranger, "/anliegen/neu"), "action": "approve",
        "state_version": "1"}).status_code == 403
    assert author.post(f"/anliegen/prozesse/{rid}", data={
        "csrf": _csrf(author, "/anliegen/prozesse"),
        "action": "approve", "state_version": "1"}).status_code == 403
    with SessionLocal() as db:
        author_user = db.get(User, bundle["author_id"])
        other_org = Organization(name=f"Other org {uuid4().hex}", kind="fachbereich", active=True)
        db.add(other_org)
        db.flush()
        with pytest.raises(Exception) as exc:
            config.create_draft(db, author_user, bundle["cat_id"],
                                bundle["process_id"], other_org.id,
                                _policy("handler"))
        assert "403" in str(exc.value)
        db.rollback()  # The uncommitted foreign organization was rolled back too.


def test_auto_start_is_explicit_and_deduplicated_against_manual(bundle):
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == ADMIN[0]))
        cat = db.get(AnliegenCategory, bundle["cat_id"])
        proc = db.get(Process, bundle["process_id"])
        global_rule = config.create_draft(db, admin, cat.id, proc.id, None,
                                          _policy("auto", approval=False))
        config.submit_review(db, global_rule, admin, expected=0)
        # A different administrator is required to approve a global rule.
        other = User(email=_unique("global-approver"), name="Global approver",
                     password_hash=hash_password(PASSWORD), is_admin=True,
                     active=True, must_change_password=False, permissions="")
        db.add(other)
        db.flush()
        config.approve(db, global_rule, other, expected=1)
        db.commit()
        rid = global_rule.id
        other_id = other.id
    _flag_enabled()
    reporter = _client(bundle, "reporter")
    res = _new_case(reporter, bundle)
    assert res.status_code == 303
    cid = int(res.headers["location"].split("/")[-1])
    with SessionLocal() as db:
        runs = list(db.scalars(select(AnliegenProcessRun).where(
            AnliegenProcessRun.anliegen_id == cid)))
        assert len(runs) == 1 and runs[0].rule_id == rid
        assert runs[0].origin == "auto"
        assert runs[0].state == "running"
        db.delete(db.get(User, other_id))
        db.commit()


def test_confidential_categories_rejected_even_when_admin(bundle):
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == ADMIN[0]))
        confidential = AnliegenCategory(
            key=f"confidential_process_test_{uuid4().hex}",
            title="Geheim", confidential=True, routing="lead", enabled=True)
        db.add(confidential)
        db.flush()
        with pytest.raises(Exception) as ex:
            config.create_draft(db, admin, confidential.id,
                                bundle["process_id"], None, _policy("handler"))
        assert "422" in str(ex.value)
        db.rollback()  # The confidential category insert was never committed.


def test_csrf_and_switch_admin_only(bundle):
    admin = login(*ADMIN)
    outsider = _client(bundle, "stranger")
    assert outsider.post("/anliegen/prozesse/schalter", data={
        "csrf": _csrf(outsider, "/anliegen/neu"), "enabled": "1"}).status_code == 403
    assert admin.post("/anliegen/prozesse/schalter", data={
        "enabled": "1"}).status_code in (400, 403)
    assert admin.post("/anliegen/prozesse/schalter", data={
        "csrf": _csrf(admin, "/anliegen/prozesse"), "enabled": "1"}).status_code == 303
    with SessionLocal() as db:
        assert policies.integration_enabled(db) is True
