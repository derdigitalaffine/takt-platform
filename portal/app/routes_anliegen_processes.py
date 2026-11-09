"""CSRF-protected internal process rule administration and scoped start actions."""
import json
from uuid import uuid4

from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import anliegen as cases
from . import anliegen_process_config as config
from . import anliegen_processes as policies
from . import anliegen_process_engine as engine
from .anliegen_models import Anliegen, AnliegenCategory
from .anliegen_process_models import (
    AnliegenProcessRule, AnliegenProcessRun, AnliegenProcessTask,
)
from .db import Organization, Process, Setting, User, get_settings
from .main import (app, check_csrf, current_user, enabled_modules, flash,
                   get_db, rate_limit, redirect, render)


def _module():
    if "anliegen" not in enabled_modules():
        raise HTTPException(404, "Interne Anliegen sind nicht eingeschaltet.")


def _config_user(user: User):
    if not user.active or not (
            user.is_admin or user.can("anliegen_process_configure")
            or user.can("anliegen_process_approve")):
        raise HTTPException(403, "Keine Berechtigung für die Prozessverwaltung.")


def _get_rule(db: Session, rid: int) -> AnliegenProcessRule:
    rule = db.get(AnliegenProcessRule, rid)
    if rule is None:
        raise HTTPException(404, "Prozessregel nicht gefunden.")
    return rule


def _get_run(db: Session, run_id: int) -> AnliegenProcessRun:
    run = db.get(AnliegenProcessRun, run_id)
    if run is None:
        raise HTTPException(404, "Prozesslauf nicht gefunden.")
    return run


def _process_error(exc: engine.ProcessEngineError):
    code = 403 if isinstance(exc, engine.ProcessAccessDenied) else (
        409 if isinstance(exc, engine.ProcessConflict) else 422)
    raise HTTPException(code, str(exc)) from exc


def _clean_policy(form):
    modes = list(form.getlist("start_modes"))
    if len(modes) != len(set(modes)):
        raise HTTPException(422, "Startarten dürfen nicht doppelt vorkommen.")
    return {
        "start_modes": modes,
        "approval_required": form.get("approval_required") == "1",
        "completion": str(form.get("completion", "manual")),
        "agent_autonomy": "off",
        "field_mapping": [],
        "dependencies": [],
    }


@app.get("/anliegen/prozesse")
def process_rules_page(request: Request, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    _module()
    _config_user(user)
    categories = list(db.scalars(select(AnliegenCategory).where(
        AnliegenCategory.confidential.is_(False)).order_by(AnliegenCategory.title)))
    processes = config.process_choices(db, user) if (
        user.is_admin or user.can("anliegen_process_configure")) else []
    orgs = list(db.scalars(select(Organization).where(
        Organization.active.is_(True)).order_by(Organization.name)))
    orgs = [org for org in orgs if config.can_configure(db, user, org.id)]
    rules = list(db.scalars(select(AnliegenProcessRule).order_by(
        AnliegenProcessRule.id.desc()).limit(500)))
    visible = []
    for rule in rules:
        edit = config.can_configure(db, user, rule.org_id)
        approve = config.can_approve_config(db, user, rule.org_id)
        if not (edit or approve):
            continue
        category = db.get(AnliegenCategory, rule.category_id)
        process = db.get(Process, rule.process_id)
        org = db.get(Organization, rule.org_id) if rule.org_id else None
        if not category or not process:
            continue
        try:
            policy = policies.normalize_policy(json.loads(rule.policy_json or "{}"))
        except (ValueError, TypeError):
            policy = dict(policies.DEFAULT_POLICY)
        visible.append(dict(rule=rule, category=category, process=process,
                            org=org, policy=policy, can_edit=edit,
                            can_approve=approve))
    return render(request, "anliegen_process_rules.html", user,
                  categories=categories, processes=processes, orgs=orgs,
                  rules=visible, enabled=policies.integration_enabled(db),
                  can_global=user.is_admin, has_scope=bool(orgs or user.is_admin))


@app.post("/anliegen/prozesse/schalter", dependencies=[Depends(check_csrf)])
def integration_switch(request: Request, enabled: str = Form(""),
                       user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    _module()
    if not user.active or not user.is_admin:
        raise HTTPException(403, "Nur die globale Administration darf die Integration aktivieren.")
    flag = db.get(Setting, "anliegen_process_integration_enabled")
    if flag is None:
        flag = Setting(key="anliegen_process_integration_enabled", value="0")
        db.add(flag)
    flag.value = "1" if enabled == "1" else "0"
    db.commit()
    flash(request, "Prozessintegration aktiviert." if flag.value == "1"
          else "Prozessintegration deaktiviert. Laufende Vorgänge bleiben gespeichert.")
    return redirect("/anliegen/prozesse")


@app.post("/anliegen/prozesse/neu", dependencies=[Depends(check_csrf)])
async def create_rule(request: Request, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    _module()
    _config_user(user)
    rate_limit(request, "anliegen-process-rule", limit=30, window=3600, key=str(user.id))
    form = await request.form()
    try:
        category_id = int(form.get("category_id", 0))
        process_id = int(form.get("process_id", 0))
        org_id = int(form.get("org_id", 0)) or None
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Bitte gültige Kategorie, Prozess und Organisation wählen.") from exc
    created = config.create_draft(db, user, category_id, process_id, org_id,
                                  _clean_policy(form))
    db.commit()
    flash(request, f"Prozesszuordnung als Entwurf V{created.revision} angelegt.")
    return redirect(f"/anliegen/prozesse#rule-{created.id}")


@app.post("/anliegen/prozesse/{rule_id:int}", dependencies=[Depends(check_csrf)])
async def rule_action(request: Request, rule_id: int,
                      user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    _module()
    _config_user(user)
    rate_limit(request, "anliegen-process-rule-action", limit=60,
               window=3600, key=str(user.id))
    rule = _get_rule(db, rule_id)
    form = await request.form()
    try:
        expected = int(form.get("state_version", "-1"))
    except ValueError as exc:
        raise HTTPException(409, "Bitte den aktuellen Regelstand laden.") from exc
    action = form.get("action")
    if action == "update":
        config.update_draft(db, rule, user, _clean_policy(form),
                            expected=expected)
        flash(request, "Prozessregel gespeichert.")
    elif action == "review":
        config.submit_review(db, rule, user, expected=expected)
        flash(request, "Regel zur Freigabe vorgelegt.")
    elif action == "approve":
        config.approve(db, rule, user, expected=expected)
        flash(request, "Regel freigegeben und für neue Vorgänge aktiviert.")
    elif action == "revise":
        revised = config.revise(db, rule, user, expected=expected)
        db.commit()
        flash(request, f"Neue, unabhängig bearbeitbare Revision V{revised.revision} angelegt.")
        return redirect(f"/anliegen/prozesse#rule-{revised.id}")
    elif action == "retire":
        config.retire(db, rule, user, expected=expected)
        flash(request, "Regel deaktiviert. Bestehende Prozesse bleiben erhalten.")
    else:
        raise HTTPException(422, "Unbekannte Regelaktion.")
    db.commit()
    return redirect(f"/anliegen/prozesse#rule-{rule_id}")


@app.post("/anliegen/{case_id:int}/prozess-start", dependencies=[Depends(check_csrf)])
def start_case_process(request: Request, case_id: int,
                       rule_id: int = Form(...), token: str = Form(...),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    _module()
    case = cases.get(db, user, case_id)
    rate_limit(request, "anliegen-process-start", limit=25,
               window=3600, key=str(user.id))
    run = config.launch(db, case, rule_id, user, origin="handler", token=token)
    db.commit()
    flash(request, "Prozess gestartet." if run.state != "requested"
          else "Prozessstart beantragt. Die Freigabe steht noch aus.")
    return redirect(f"/anliegen/{case_id}#anliegen-processes")


@app.get("/anliegen/prozessfreigaben")
def process_approvals(request: Request, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    _module()
    if not user.active or not user.can("anliegen_process_approve"):
        raise HTTPException(403)
    pending = []
    for run in db.scalars(select(AnliegenProcessRun).where(
            AnliegenProcessRun.state == "requested").order_by(
            AnliegenProcessRun.id.desc()).limit(500)):
        case = db.get(Anliegen, run.anliegen_id)
        rule = db.get(AnliegenProcessRule, run.rule_id)
        if (not case or not rule or not config.can_approve_run(db, user, case)
                or run.requested_by_id == user.id):
            continue
        category = db.get(AnliegenCategory, case.category_id)
        process = db.get(Process, rule.process_id)
        if category and process:
            pending.append(dict(run=run, case=case, category=category,
                                process=process))
    return render(request, "anliegen_process_approvals.html", user,
                  pending=pending, enabled=policies.integration_enabled(db))


@app.post("/anliegen/prozessfreigaben/{run_id:int}", dependencies=[Depends(check_csrf)])
def approve_case_run(request: Request, run_id: int,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    _module()
    if not user.active or not user.can("anliegen_process_approve"):
        raise HTTPException(403)
    rate_limit(request, "anliegen-process-approve", limit=45,
               window=3600, key=str(user.id))
    run = _get_run(db, run_id)
    case = db.get(Anliegen, run.anliegen_id)
    if not case or not config.can_approve_run(db, user, case):
        raise HTTPException(404, "Prozessfreigabe nicht verfügbar.")
    try:
        engine.approve_run(db, run, user)
    except engine.ProcessEngineError as exc:
        _process_error(exc)
    db.commit()
    flash(request, "Prozessfreigabe erteilt.")
    return redirect("/anliegen/prozessfreigaben")


@app.post("/anliegen/{case_id:int}/prozesse/{run_id:int}/aufgabe/{task_id:int}",
          dependencies=[Depends(check_csrf)])
async def case_process_task(request: Request, case_id: int, run_id: int,
                            task_id: int, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    _module()
    case = cases.get(db, user, case_id)
    if not cases.can_handle(user, case):
        raise HTTPException(403)
    run = _get_run(db, run_id)
    task = db.get(AnliegenProcessTask, task_id)
    if run.anliegen_id != case.id or task is None or task.run_id != run.id:
        raise HTTPException(404)
    rate_limit(request, "anliegen-process-task", limit=90,
               window=3600, key=str(user.id))
    form = await request.form()
    keys = engine._definition(db, run)
    if task.step_index < 0 or task.step_index >= len(keys):
        raise HTTPException(409, "Prozessschritt ist veraltet.")
    step = keys[task.step_index]
    values = {f["key"]: str(form.get("field_" + f["key"], ""))
              for f in (step.get("fields") or [])}
    try:
        engine.complete_task(db, task, user,
                             outcome=str(form.get("outcome", "done")),
                             checks=list(form.getlist("checks")),
                             values=values,
                             comment=str(form.get("comment", "")))
    except engine.ProcessEngineError as exc:
        _process_error(exc)
    db.commit()
    flash(request, "Prozessschritt abgeschlossen.")
    return redirect(f"/anliegen/{case.id}#anliegen-processes")


@app.post("/anliegen/{case_id:int}/prozesse/{run_id:int}/steuern",
          dependencies=[Depends(check_csrf)])
def case_process_control(request: Request, case_id: int, run_id: int,
                         action: str = Form(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    _module()
    case = cases.get(db, user, case_id)
    if not user.can("anliegen_process_start") or not cases.can_handle(user, case):
        raise HTTPException(403)
    run = _get_run(db, run_id)
    if run.anliegen_id != case.id:
        raise HTTPException(404)
    rate_limit(request, "anliegen-process-control", limit=45,
               window=3600, key=str(user.id))
    try:
        if action == "pause":
            engine.pause_run(db, run, user)
        elif action == "resume":
            engine.resume_run(db, run, user)
        elif action == "cancel":
            engine.cancel_run(db, run, user)
        else:
            raise HTTPException(422, "Unbekannte Prozessaktion.")
    except engine.ProcessEngineError as exc:
        _process_error(exc)
    db.commit()
    flash(request, "Prozesssteuerung aktualisiert.")
    return redirect(f"/anliegen/{case.id}#anliegen-processes")
