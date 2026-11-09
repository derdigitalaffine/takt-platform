"""Internal-process engine: no synthetic applications, no accidental side effects."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app import process_engine, workflow
from app.anliegen_models import Anliegen, AnliegenCategory
from app.anliegen_process_models import (
    AnliegenProcessRule, AnliegenProcessRun, AnliegenProcessTask, AnliegenProcessAudit,
)
from app.anliegen_process_engine import (
    ProcessAccessDenied, ProcessConflict, ProcessEngineError, approve_run,
    cancel_run, complete_task, pause_run, request_start, resume_run,
    validate_internal_version,
)
from app.db import FormResponse, Process, ProcessVersion, Setting, User
from app.process_context import anliegen_context, form_context
from app.security import decrypt


def make_step(name="Prüfung", key="check"):
    return {"id": key, "name": name, "type": "task", "status": "",
            "assign": {"mode": "case"}, "checklist": ["Punkt prüfen"],
            "fields": [{"key": "amount", "label": "Betrag", "type": "number",
                        "options": [], "required": True}]}


def approval_step(user_id, *, four_eyes=False):
    return {"id": "approval", "name": "Freigabe", "type": "approval",
            "status": "", "assign": {"mode": "user", "user_id": user_id},
            "four_eyes": four_eyes, "on_reject": "end"}


@pytest.fixture
def prepared(db):
    admin = db.scalar(select(User).where(User.email == "admin@example.org"))
    assert admin
    reviewer = User(
        email=f"process-reviewer-{uuid4().hex}@example.org",
        name="Prozessprüfer", password_hash="not-used",
        active=True, is_admin=False, permissions="anliegen_manage")
    outsider = User(
        email=f"process-outsider-{uuid4().hex}@example.org",
        name="Unbeteiligt", password_hash="not-used",
        active=True, is_admin=False, permissions="")
    db.add_all([reviewer, outsider])
    db.flush()
    cat = db.scalar(select(AnliegenCategory).where(
        AnliegenCategory.key == "it_procurement"))
    case = Anliegen(category_id=cat.id, reporter_id=admin.id, assignee_id=admin.id,
                   title="Monitore bestellen", description="Zwei Monitore benötigt",
                   status="open", confidential=False)
    proc = Process(name="Interne Beschaffung", draft_json="{}")
    db.add_all([case, proc])
    db.flush()
    version = ProcessVersion(process_id=proc.id, version=1,
                             definition_json=json.dumps({
                                 "steps": [make_step(), approval_step(reviewer.id)],
                                 "end_status": "done", "end_inform": False}))
    db.add(version)
    db.flush()
    policy = {"start_modes": ["handler"], "approval_required": False,
              "completion": "manual", "agent_autonomy": "off",
              "field_mapping": [{"source": "description", "target": "amount"}],
              "dependencies": []}
    rule = AnliegenProcessRule(
        category_id=cat.id, process_id=proc.id, revision=1, state="active",
        approved_by_id=admin.id, policy_json=json.dumps(policy))
    db.add(rule)
    db.flush()
    flag = db.get(Setting, "anliegen_process_integration_enabled")
    if flag is None:
        flag = Setting(key="anliegen_process_integration_enabled", value="1")
        db.add(flag)
    else:
        flag.value = "1"
    db.flush()
    return db, case, proc, version, rule, admin, reviewer, outsider


def start(p, *, key="workflow-start:123456", **kwargs):
    db, case, proc, version, rule, admin, reviewer, outsider = p
    return request_start(db, case, rule, admin, origin="handler",
                         launch_key=key, inputs={"amount": 2}, **kwargs)


def task_of(db, run, kind=None):
    stmt = select(AnliegenProcessTask).where(AnliegenProcessTask.run_id == run.id)
    if kind:
        stmt = stmt.where(AnliegenProcessTask.kind == kind)
    return db.scalars(stmt.order_by(AnliegenProcessTask.ordinal.desc())).first()


def test_starts_safe_workflow_without_creating_application(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    initial = db.scalar(select(FormResponse.id).order_by(FormResponse.id.desc()))
    run = start(prepared)
    assert run.state == "running"
    assert run.process_version_id == version.id
    assert run.cursor == 0
    assert task_of(db, run).assignee_id == admin.id
    assert db.scalar(select(FormResponse.id).order_by(FormResponse.id.desc())) == initial
    assert "amount" not in (run.inputs_enc or "")
    assert json.loads(decrypt(run.inputs_enc)) == {"amount": 2}
    assert len(list(db.scalars(select(AnliegenProcessAudit).where(
        AnliegenProcessAudit.run_id == run.id)))) >= 2


def test_tasks_approve_and_finish_with_four_eyes(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    version.definition_json = json.dumps({"steps": [
        make_step(), approval_step(reviewer.id, four_eyes=True)]})
    db.flush()
    run = start(prepared)
    first = task_of(db, run)
    with pytest.raises(ProcessAccessDenied):
        complete_task(db, first, outsider, checks=["Punkt prüfen"],
                      values={"amount": "75"})
    with pytest.raises(ProcessEngineError):
        complete_task(db, first, admin, checks=[],
                      values={"amount": 75})
    complete_task(db, first, admin, checks=["Punkt prüfen"],
                  values={"amount": "75"}, comment="Interne Kostenschätzung")
    assert "Interne Kostenschätzung" not in (first.comment_enc or "")
    assert decrypt(first.comment_enc) == "Interne Kostenschätzung"
    approval = task_of(db, run, "approval")
    assert approval.state == "open" and approval.assignee_id == reviewer.id
    with pytest.raises(ProcessAccessDenied):
        complete_task(db, approval, admin, outcome="approved")
    complete_task(db, approval, reviewer, outcome="approved")
    assert run.state == "done"
    assert task_of(db, run).state == "done"
    with pytest.raises(ProcessConflict):
        complete_task(db, approval, reviewer, outcome="approved")


def test_rejection_ends_run_without_closing_anliegen(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    run = start(prepared)
    complete_task(db, task_of(db, run), admin,
                  checks=["Punkt prüfen"], values={"amount": "12"})
    approval = task_of(db, run)
    with pytest.raises(ProcessEngineError):
        complete_task(db, approval, reviewer, outcome="rejected", comment="")
    complete_task(db, approval, reviewer, outcome="rejected", comment="Budget fehlt")
    assert run.state == "rejected"
    assert case.status == "open"


def test_idempotent_start_preserves_one_task_and_version(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    run = start(prepared)
    repeated = start(prepared)
    assert repeated.id == run.id
    assert db.scalar(select(AnliegenProcessTask.id).where(
        AnliegenProcessTask.run_id == run.id,
        AnliegenProcessTask.ordinal == 2)) is None
    other_case = Anliegen(category_id=case.category_id, reporter_id=admin.id,
                         assignee_id=admin.id, title="Andere Anfrage",
                         description="Fünf Monitore", status="open")
    db.add(other_case)
    db.flush()
    with pytest.raises(ProcessConflict):
        request_start(db, other_case, rule, admin, origin="handler",
                      launch_key="workflow-start:123456")
    newer = ProcessVersion(process_id=proc.id, version=2,
                           definition_json=json.dumps({"steps": [make_step()]}))
    db.add(newer)
    db.flush()
    assert run.process_version_id == version.id


def test_approval_gate_requires_second_authorized_person(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    rule.policy_json = json.dumps({"start_modes": ["handler"], "approval_required": True})
    db.flush()
    run = start(prepared)
    assert run.state == "requested" and task_of(db, run) is None
    with pytest.raises(ProcessAccessDenied):
        approve_run(db, run, outsider)
    with pytest.raises(ProcessAccessDenied):
        approve_run(db, run, admin)
    approve_run(db, run, reviewer)
    assert run.state == "running" and task_of(db, run) is not None
    with pytest.raises(ProcessConflict):
        approve_run(db, run, reviewer)


def test_unsupported_form_only_actions_fail_before_any_task(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    baseline = db.scalar(select(AnliegenProcessRun.id).order_by(
        AnliegenProcessRun.id.desc()))
    invalid = [
        {"id": "r", "type": "request", "name": "Nachforderung"},
        {"id": "c", "type": "confirm", "name": "Email bestätigen"},
        {"id": "p", "type": "payment", "name": "Gebühr"},
        {"id": "a", "type": "auto", "name": "Mail",
         "actions": [{"type": "mail", "to": "email", "email": "someone@example.com"}]},
        {"id": "s", "type": "task", "name": "Status ändern",
         "status": "in_progress"},
        {"id": "q", "type": "task", "name": "Frage",
         "condition": {"source": "q", "key": "secret", "op": "filled", "value": ""}},
    ]
    for step in invalid:
        version.definition_json = json.dumps({"steps": [step]})
        db.flush()
        with pytest.raises(ProcessEngineError):
            request_start(db, case, rule, admin, origin="handler",
                          launch_key=f"invalid-test:{step['id']}:123456")
    assert db.scalar(select(AnliegenProcessRun.id).order_by(
        AnliegenProcessRun.id.desc())) == baseline


def test_conditions_and_noop_auto_do_not_emit_external_actions(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    version.definition_json = json.dumps({"steps": [
        {"id": "safe", "type": "auto", "name": "Sicherer Marker", "actions": []},
        {"id": "conditional", "type": "task", "name": "Bedingte Aufgabe",
         "condition": {"source": "f", "key": "amount", "op": "gt", "value": "100"},
         "assign": {"mode": "case"}},
        make_step(key="final"),
    ]})
    db.flush()
    run = start(prepared)
    history = list(db.scalars(select(AnliegenProcessTask).where(
        AnliegenProcessTask.run_id == run.id).order_by(AnliegenProcessTask.ordinal)))
    assert [t.state for t in history] == ["done", "skipped", "open"]
    assert history[2].step_id == "final"
    complete_task(db, history[2], admin,
                  checks=["Punkt prüfen"], values={"amount": 3})
    assert run.state == "done"


def test_pause_resume_cancel_and_optimistic_lock(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    run = start(prepared)
    task = task_of(db, run)
    pause_run(db, run, admin)
    with pytest.raises(ProcessConflict):
        complete_task(db, task, admin, checks=["Punkt prüfen"], values={"amount": 1})
    resume_run(db, run, admin)
    assert db.scalar(select(AnliegenProcessTask.id).where(
        AnliegenProcessTask.run_id == run.id, AnliegenProcessTask.ordinal == 2)) is None
    db.execute(text("UPDATE anliegen_process_runs SET state_version = state_version + 1 WHERE id = :id"),
               {"id": run.id})
    with pytest.raises(ProcessConflict):
        complete_task(db, task, admin, checks=["Punkt prüfen"], values={"amount": 1})
    db.refresh(run)
    cancel_run(db, run, admin)
    assert run.state == "cancelled"
    assert task.state == "cancelled"
    with pytest.raises(ProcessConflict):
        cancel_run(db, run, admin)


def test_fail_closed_permissions_confidential_org_and_feature_flag(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    with pytest.raises(ProcessAccessDenied):
        request_start(db, case, rule, outsider, origin="handler",
                      launch_key="unauthorized:123456")
    rule.org_id = 123456
    db.flush()
    with pytest.raises(ProcessAccessDenied):
        start(prepared)
    rule.org_id = None
    case.confidential = True
    db.flush()
    with pytest.raises(ProcessAccessDenied):
        start(prepared)
    case.confidential = False
    db.get(Setting, "anliegen_process_integration_enabled").value = "0"
    db.flush()
    with pytest.raises(ProcessAccessDenied):
        start(prepared)


def test_failed_transaction_can_rollback_without_side_effects(prepared):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    with pytest.raises(RuntimeError):
        with db.begin_nested():
            run = start(prepared, key="rollback-case:123456")
            assert task_of(db, run)
            raise RuntimeError("Simulated transport failure")
    assert db.scalar(select(AnliegenProcessRun).where(
        AnliegenProcessRun.launch_key == "rollback-case:123456")) is None


def test_dispatch_type_guards(prepared, monkeypatch):
    db, case, proc, version, rule, admin, reviewer, outsider = prepared
    actual = anliegen_context(case)
    assert actual.kind == "anliegen"
    with pytest.raises(ValueError):
        process_engine.start(db, actual, case=case, actor=admin)
    with pytest.raises(ValueError):
        process_engine.start(db, actual, response=FormResponse(id=100))
    response = FormResponse(id=9876, user_id=admin.id)
    c = form_context(response)
    called = []
    monkeypatch.setattr(workflow, "start", lambda db, resp: called.append(resp.id) or True)
    assert process_engine.start(db, c, response=response) is True
    assert called == [9876]
    with pytest.raises(ValueError):
        process_engine.start(db, c, response=response, case=case)
