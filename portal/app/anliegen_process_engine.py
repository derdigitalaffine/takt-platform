"""Transaction-bound, side-effect-free executor for published internal workflows.

Intentionally distinct persistence from FormResponse/ApplicationTask. Published
ProcessVersion JSON is shared, but application-only effects are rejected before
the first step. Callers own commit/rollback. No background worker or routes yet.
"""
import json
import math
import re
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import anliegen as cases, anliegen_processes as rules, workflow
from .anliegen_models import Anliegen
from .anliegen_process_models import (
    AnliegenProcessAudit, AnliegenProcessRule, AnliegenProcessRun, AnliegenProcessTask,
)
from .db import Group, Process, ProcessVersion, User, utcnow
from .process_context import anliegen_context
from .security import decrypt, encrypt

SUPPORTED_STEPS = frozenset({"task", "approval", "auto"})
FINISHED = frozenset({"done", "rejected", "cancelled"})
VALID_OUTCOMES = frozenset({"done", "approved", "rejected"})
LAUNCH_KEY_RE = re.compile(r"^[A-Za-z0-9_:.-]{12,128}$")
FIELD_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
STEP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class ProcessEngineError(ValueError):
    """Safe, actionable business validation error. Never contains case content."""


class ProcessAccessDenied(ProcessEngineError):
    pass


class ProcessConflict(ProcessEngineError):
    pass


def _json_read(value, *, fallback=None):
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return fallback
    return data


def _stored(data: dict) -> str:
    return encrypt(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _inputs(run: AnliegenProcessRun) -> dict:
    data = _json_read(decrypt(run.inputs_enc), fallback={})
    if not isinstance(data, dict):
        raise ProcessEngineError("Gespeicherte Prozessdaten sind nicht lesbar.")
    return data


def _audit(db: Session, run: AnliegenProcessRun, actor: User | None, kind: str, note: str = ""):
    db.add(AnliegenProcessAudit(run_id=run.id, actor_id=actor.id if actor else None,
                               kind=kind, note=note[:500]))


def validate_internal_version(version: ProcessVersion) -> list[dict]:
    """Reject every unsupported step/condition/action before launch or approval.

    Form-only metadata (end_message, end_inform, end_status) is not used for
    external messages or altering the Anliegen: internal completion is its own
    state; its aggregate with the Anliegen is handled by the later Hub.
    """
    if not version or not version.id:
        raise ProcessEngineError("Keine veröffentlichte Prozessversion vorhanden.")
    definition = _json_read(version.definition_json)
    if not isinstance(definition, dict) or not isinstance(definition.get("steps"), list):
        raise ProcessEngineError("Die veröffentlichte Prozessdefinition ist ungültig.")
    steps = definition["steps"]
    if not 1 <= len(steps) <= 60:
        raise ProcessEngineError("Ein interner Prozess benötigt 1 bis 60 Schritte.")
    identifiers = set()
    for step in steps:
        if not isinstance(step, dict):
            raise ProcessEngineError("Ein Prozessschritt ist ungültig.")
        kind, key = step.get("type"), step.get("id")
        if kind not in SUPPORTED_STEPS:
            raise ProcessEngineError(f"Schritttyp {str(kind)[:30]} ist für interne Anliegen nicht freigegeben.")
        if not isinstance(key, str) or not STEP_ID_RE.fullmatch(key) or key in identifiers:
            raise ProcessEngineError("Schritt-IDs müssen gültig und eindeutig sein.")
        identifiers.add(key)
        if kind == "auto" and step.get("actions"):
            raise ProcessEngineError(
                "Automatische Mail-, Zahlungs-, PDF-, Status- und Zuweisungsaktionen "
                "sind für interne Anliegen noch nicht freigegeben.")
        if step.get("status"):
            raise ProcessEngineError("Antragsspezifische Schrittstatus können nicht übernommen werden.")
        if kind in ("task", "approval"):
            assign = step.get("assign") or {}
            if not isinstance(assign, dict) or assign.get("mode", "case") not in (
                    "case", "user", "group", "previous"):
                raise ProcessEngineError("Ungültige Schrittzuständigkeit.")
            if assign.get("mode") == "user" and not assign.get("user_id"):
                raise ProcessEngineError("Eine fest zugewiesene Person fehlt.")
            if assign.get("mode") == "group" and not assign.get("group_id"):
                raise ProcessEngineError("Eine fest zugewiesene Gruppe fehlt.")
        if kind == "task":
            fields = step.get("fields") or []
            if not isinstance(fields, list) or len(fields) > 30:
                raise ProcessEngineError("Ungültige Eingabefelder.")
            seen = set()
            for field in fields:
                if (not isinstance(field, dict) or not isinstance(field.get("key"), str)
                        or not FIELD_RE.fullmatch(field["key"])
                        or field["key"] in seen or field.get("type") not in workflow.FIELD_TYPES):
                    raise ProcessEngineError("Ungültiges oder doppeltes Prozessfeld.")
                seen.add(field["key"])
        cond = step.get("condition")
        if cond is not None:
            if (not isinstance(cond, dict) or cond.get("source") not in ("f", "step")
                    or cond.get("op") not in workflow.OPS
                    or not isinstance(cond.get("key"), str)
                    or not isinstance(cond.get("value", ""), str)):
                raise ProcessEngineError("Formularabhängige oder ungültige Schrittbedingung.")
    for step in steps:
        cond = step.get("condition")
        if cond and cond["source"] == "step" and cond["key"] not in identifiers:
            raise ProcessEngineError("Die Bedingung verweist auf einen fehlenden Schritt.")
        if step.get("goto") and step["goto"] not in identifiers:
            raise ProcessEngineError("Prozesssprung verweist auf einen fehlenden Schritt.")
        if step["type"] == "approval":
            target = step.get("on_reject") or "end"
            if target != "end" and target not in identifiers:
                raise ProcessEngineError("Ablehnungszweig verweist auf einen fehlenden Schritt.")
    return steps


def _definition(db: Session, run: AnliegenProcessRun):
    version = db.get(ProcessVersion, run.process_version_id)
    return validate_internal_version(version)


def _policy(rule: AnliegenProcessRule) -> dict:
    raw = _json_read(rule.policy_json, fallback=None)
    try:
        return rules.normalize_policy(raw)
    except (TypeError, ValueError) as exc:
        raise ProcessEngineError("Die Prozessregel ist ungültig.") from exc


def _check_available(db: Session):
    if not rules.integration_enabled(db):
        raise ProcessAccessDenied("Die Prozessintegration ist deaktiviert.")


def _case(db: Session, run: AnliegenProcessRun) -> Anliegen:
    case = db.get(Anliegen, run.anliegen_id)
    if case is None or case.confidential:
        raise ProcessAccessDenied("Kein Zugriff auf dieses Anliegen.")
    return case


def _require_handler(user: User, case: Anliegen):
    if not user or not user.active or not cases.can_handle(user, case):
        raise ProcessAccessDenied("Keine Berechtigung zur Prozessbearbeitung.")


def _lock_version(db: Session, run: AnliegenProcessRun):
    """Compare-and-swap per run before mutating tasks or branching.

    SQLite serializes writers; the CAS prevents a second stale completion from
    emitting another next step. Failed CAS is an error, never a silent retry.
    """
    expected = run.state_version
    changed = db.execute(
        update(AnliegenProcessRun)
        .where(AnliegenProcessRun.id == run.id,
               AnliegenProcessRun.state_version == expected)
        .values(state_version=expected + 1)
    )
    if changed.rowcount != 1:
        raise ProcessConflict("Der Vorgang wurde inzwischen verändert. Bitte neu laden.")
    run.state_version = expected + 1


def _safe_inputs(policy: dict, supplied: dict | None) -> dict:
    fields = supplied or {}
    if not isinstance(fields, dict) or len(fields) > 64:
        raise ProcessEngineError("Ungültige Prozessdaten.")
    targets = {item["target"] for item in policy["field_mapping"]}
    clean = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not FIELD_RE.fullmatch(key) or key not in targets:
            raise ProcessEngineError("Prozessdaten dürfen nur freigegebene Zielfelder enthalten.")
        if isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, (int, float)) and math.isfinite(value):
            clean[key] = value
        elif isinstance(value, str) and len(value) <= 500:
            clean[key] = value
        else:
            raise ProcessEngineError("Ungültiger Wert für ein Prozessfeld.")
    return clean


def request_start(db: Session, case: Anliegen, rule: AnliegenProcessRule, actor: User,
                  *, origin: str, launch_key: str, inputs: dict | None = None) -> AnliegenProcessRun:
    """Create exactly one run for a stable caller-provided idempotency key.

    No own commit. Approval-required runs DO NOT execute a step until explicitly
    approved. Starts are deliberately unavailable through HTTP in this phase.
    """
    _check_available(db)
    if not actor or not actor.active:
        raise ProcessAccessDenied("Kein aktives Benutzerkonto.")
    context = anliegen_context(case)
    if context.confidential:
        raise ProcessAccessDenied("Vertrauliche Anliegen sind nicht freigegeben.")
    if not isinstance(launch_key, str) or not LAUNCH_KEY_RE.fullmatch(launch_key):
        raise ProcessEngineError("Ein gültiger, stabiler Startschlüssel ist erforderlich.")
    if not rule or rule.state != "active" or not rule.approved_by_id:
        raise ProcessAccessDenied("Keine aktiv freigegebene Prozessregel.")
    if case.category_id != rule.category_id or (rule.org_id is not None and rule.org_id != context.org_id):
        raise ProcessAccessDenied("Die Prozessregel gilt nicht für dieses Anliegen.")
    policy = _policy(rule)
    if origin not in policy["start_modes"]:
        raise ProcessAccessDenied("Diese Prozessstartart ist nicht freigegeben.")
    if origin == "submit":
        if case.reporter_id != actor.id or not actor.can("anliegen_submit"):
            raise ProcessAccessDenied("Keine Berechtigung zum Prozessstart beim Einreichen.")
    elif origin == "handler":
        _require_handler(actor, case)
    elif origin == "auto":
        # A rule's explicitly authorized approver is its scoped automation
        # principal. No global Anliegen management right is implied.
        from . import anliegen_process_config
        if (actor.id != rule.approved_by_id
                or not anliegen_process_config.can_approve_config(db, actor, rule.org_id)):
            raise ProcessAccessDenied("Keine freigegebene Identität für den automatischen Start.")
    else:
        raise ProcessAccessDenied("Startart nicht freigegeben.")
    existing = db.scalar(select(AnliegenProcessRun).where(
        AnliegenProcessRun.launch_key == launch_key))
    if existing:
        if (existing.anliegen_id, existing.rule_id, existing.origin) != (
                case.id, rule.id, origin):
            raise ProcessConflict("Der Startschlüssel ist bereits anderweitig belegt.")
        return existing
    process = db.get(Process, rule.process_id)
    version = (db.get(ProcessVersion, rule.process_version_id)
               if rule.process_version_id else (process.current if process else None))
    if process is None or version is None or version.process_id != process.id:
        raise ProcessEngineError("Die freigegebene Prozessversion ist nicht verfügbar.")
    validate_internal_version(version)
    data = _safe_inputs(policy, inputs)
    run = AnliegenProcessRun(
        anliegen_id=case.id, rule_id=rule.id, process_version_id=version.id,
        launch_key=launch_key, origin=origin, state="requested" if policy["approval_required"] else "running",
        requested_by_id=actor.id, inputs_enc=_stored(data))
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        # A concurrent caller may have used the same idempotency key.
        duplicate = db.scalar(select(AnliegenProcessRun).where(
            AnliegenProcessRun.launch_key == launch_key))
        if duplicate and (duplicate.anliegen_id, duplicate.rule_id, duplicate.origin) == (
                case.id, rule.id, origin):
            return duplicate
        raise ProcessConflict("Der Prozessstart kollidiert mit einem anderen Vorgang.") from None
    _audit(db, run, actor, "requested")
    if run.state == "running":
        _advance(db, run, case)
    return run


def approve_run(db: Session, run: AnliegenProcessRun, actor: User):
    _check_available(db)
    case = _case(db, run)
    from . import anliegen_process_config
    if not (cases.can_handle(actor, case)
            or anliegen_process_config.can_approve_run(db, actor, case)):
        raise ProcessAccessDenied("Keine Berechtigung zur Prozessfreigabe.")
    if run.state != "requested":
        raise ProcessConflict("Dieser Prozess wartet nicht auf eine Freigabe.")
    if run.requested_by_id == actor.id:
        raise ProcessAccessDenied("Start und Freigabe dürfen nicht durch dieselbe Person erfolgen.")
    _definition(db, run)
    _lock_version(db, run)
    run.state, run.approved_by_id = "running", actor.id
    _audit(db, run, actor, "approved")
    _advance(db, run, case)


def _completed(db: Session, run: AnliegenProcessRun) -> list[AnliegenProcessTask]:
    return list(db.scalars(select(AnliegenProcessTask).where(
        AnliegenProcessTask.run_id == run.id).order_by(
            AnliegenProcessTask.ordinal)))


def _condition_matches(db: Session, run: AnliegenProcessRun, cond: dict) -> bool:
    if not cond:
        return True
    if cond["source"] == "f":
        value = _inputs(run).get(cond["key"])
    else:
        tasks = [t for t in _completed(db, run)
                 if t.step_id == cond["key"] and t.state == "done"]
        value = {"approved": "genehmigt", "rejected": "abgelehnt", "done": "erledigt"}.get(
            tasks[-1].outcome) if tasks else None
    return workflow.evaluate_value(cond, value)


def _assign(db: Session, case: Anliegen, run: AnliegenProcessRun, step: dict):
    assign = step.get("assign") or {}
    mode = assign.get("mode", "case")
    if mode == "user":
        user = db.get(User, assign.get("user_id"))
        return (user.id, None) if user and user.active else (None, None)
    if mode == "group":
        group = db.get(Group, assign.get("group_id"))
        return (None, group.id) if group else (None, None)
    if mode == "previous":
        done = [t for t in _completed(db, run)
                if t.state == "done" and t.completed_by_id]
        if done:
            user = db.get(User, done[-1].completed_by_id)
            if user and user.active:
                return user.id, None
    assignee = db.get(User, case.assignee_id) if case.assignee_id else None
    return (assignee.id, None) if assignee and assignee.active else (None, None)


def _new_task(db: Session, run: AnliegenProcessRun, step: dict, index: int, *,
              state="open", outcome="", assignee_id=None, group_id=None):
    ordinal = db.scalar(select(func.count(AnliegenProcessTask.id)).where(
        AnliegenProcessTask.run_id == run.id)) or 0
    task = AnliegenProcessTask(
        run_id=run.id, ordinal=ordinal + 1, step_index=index,
        step_id=step["id"], name=step.get("name") or step["id"],
        kind=step["type"], state=state, outcome=outcome,
        assignee_id=assignee_id, group_id=group_id,
        due_at=(utcnow() + timedelta(days=int(step.get("due_days") or 0)))
        if step.get("due_days") and state == "open" else None,
        completed_at=utcnow() if state in ("done", "skipped") else None)
    db.add(task)
    db.flush()
    return task


def _advance(db: Session, run: AnliegenProcessRun, case: Anliegen):
    steps = _definition(db, run)
    # One entry into _advance may pass only one finite version of every step.
    # Repeated human-driven loops are additionally limited by persisted task count.
    for _ in range(len(steps) + 1):
        if run.cursor >= len(steps):
            run.state, run.error_code = "done", ""
            _audit(db, run, None, "finished")
            return
        if (db.scalar(select(func.count(AnliegenProcessTask.id)).where(
                AnliegenProcessTask.run_id == run.id)) or 0) >= 200:
            run.state, run.error_code = "blocked", "step_limit"
            _audit(db, run, None, "blocked", "step_limit")
            return
        index = run.cursor
        step = steps[index]
        if not _condition_matches(db, run, step.get("condition")):
            _new_task(db, run, step, index, state="skipped")
            run.cursor = index + 1
            continue
        if step["type"] == "auto":
            # No external actions: any such actions fail validation before start.
            _new_task(db, run, step, index, state="done", outcome="done")
            run.cursor = index + 1
            continue
        assignee, group = _assign(db, case, run, step)
        if assignee is None and group is None:
            run.state, run.error_code = "blocked", "assignee_missing"
            _audit(db, run, None, "blocked", "assignee_missing")
            return
        _new_task(db, run, step, index, assignee_id=assignee, group_id=group)
        run.state, run.error_code = "running", ""
        _audit(db, run, None, "task_opened", step["id"])
        return
    run.state, run.error_code = "blocked", "step_limit"
    _audit(db, run, None, "blocked", "step_limit")


def _authorize_task(db: Session, run: AnliegenProcessRun, task: AnliegenProcessTask,
                    actor: User, case: Anliegen):
    from . import anliegen_process_hub as hub
    if not hub.private_access(db, actor, case):
        raise ProcessAccessDenied("Keine organisatorische Berechtigung zur Prozessbearbeitung.")
    if task.run_id != run.id or task.state != "open" or run.state != "running":
        raise ProcessConflict("Dieser Prozessschritt kann nicht bearbeitet werden.")
    from . import absence
    users = absence.acting_ids(db, actor)
    groups = absence.acting_group_ids(db, actor)
    if task.assignee_id not in users and (not task.group_id or task.group_id not in groups):
        raise ProcessAccessDenied("Dieser Schritt ist Ihnen nicht zugewiesen.")


def _fields(step: dict, data: dict) -> dict:
    if not isinstance(data, dict):
        raise ProcessEngineError("Ungültige Feldeingaben.")
    configured = {f["key"]: f for f in (step.get("fields") or [])}
    if set(data) - set(configured):
        raise ProcessEngineError("Unbekanntes Prozessfeld.")
    clean = {}
    for name, field in configured.items():
        raw = data.get(name, "")
        if not isinstance(raw, (int, float, str, bool)) or len(str(raw)) > 5000:
            raise ProcessEngineError("Ungültiger Prozessfeldwert.")
        value = str(raw).strip()
        if field.get("required") and not value:
            raise ProcessEngineError("Pflichtangabe fehlt.")
        if not value:
            continue
        kind = field["type"]
        if kind in ("number", "money"):
            number = workflow._num(value)
            if number is None or not math.isfinite(number) or abs(number) > 100000000:
                raise ProcessEngineError("Ungültige Zahl.")
            clean[name] = round(number, 2) if kind == "money" else (
                int(number) if number.is_integer() else number)
        elif kind == "select":
            if value not in field.get("options", []):
                raise ProcessEngineError("Ungültige Auswahl.")
            clean[name] = value
        elif kind == "yesno":
            if value not in ("Ja", "Nein"):
                raise ProcessEngineError("Bitte Ja oder Nein wählen.")
            clean[name] = value
        else:
            clean[name] = value
    return clean


def complete_task(db: Session, task: AnliegenProcessTask, actor: User,
                  *, outcome="done", checks: list[str] | None = None,
                  values: dict | None = None, comment: str = "") -> AnliegenProcessRun:
    """Complete a step once; CAS serializes concurrent submissions."""
    _check_available(db)
    run = db.get(AnliegenProcessRun, task.run_id)
    if not run:
        raise ProcessConflict("Prozess nicht gefunden.")
    case = _case(db, run)
    _authorize_task(db, run, task, actor, case)
    steps = _definition(db, run)
    if task.step_index != run.cursor or steps[run.cursor]["id"] != task.step_id:
        raise ProcessConflict("Der Schritt ist nicht mehr aktuell.")
    step = steps[task.step_index]
    if not isinstance(comment, str) or len(comment) > 10000:
        raise ProcessEngineError("Ungültiger Kommentar.")
    if task.kind == "task":
        if outcome != "done":
            raise ProcessEngineError("Eine Aufgabe kann nur als erledigt abgeschlossen werden.")
        if not isinstance(checks or [], list):
            raise ProcessEngineError("Ungültige Prüfpunkte.")
        if any(not isinstance(c, str) for c in checks or []):
            raise ProcessEngineError("Ungültige Prüfpunkte.")
        checkset = set(checks or [])
        checklist = step.get("checklist") or []
        if not checkset.issubset(set(checklist)) or not set(checklist).issubset(checkset):
            raise ProcessEngineError("Bitte alle erforderlichen Prüfpunkte bestätigen.")
        entered = _fields(step, values or {})
    elif task.kind == "approval":
        if outcome not in ("approved", "rejected"):
            raise ProcessEngineError("Bitte genehmigen oder ablehnen.")
        if outcome == "rejected" and not comment.strip():
            raise ProcessEngineError("Eine Ablehnung muss begründet werden.")
        if values or checks:
            raise ProcessEngineError("Eine Freigabe enthält keine zusätzlichen Formulareingaben.")
        if step.get("four_eyes"):
            prior = [t for t in _completed(db, run) if t.id < task.id
                     and t.kind in ("task", "approval") and t.state == "done"]
            if prior and prior[-1].completed_by_id == actor.id:
                raise ProcessAccessDenied("Vier-Augen-Prinzip: Andere Person erforderlich.")
        entered = {}
    else:
        raise ProcessEngineError("Automatikschritte können nicht manuell erledigt werden.")
    _lock_version(db, run)
    task.state, task.outcome = "done", outcome
    task.completed_at, task.completed_by_id = utcnow(), actor.id
    task.checks_enc = _stored({"checks": checks or []})
    task.values_enc = _stored(entered)
    task.comment_enc = encrypt(comment)
    if entered:
        data = _inputs(run)
        data.update(entered)
        run.inputs_enc = _stored(data)
    _audit(db, run, actor, "task_completed", task.step_id)
    if outcome == "rejected":
        target = step.get("on_reject") or "end"
        if target == "end":
            run.state = "rejected"
            _audit(db, run, actor, "rejected", task.step_id)
            return run
        run.cursor = next(i for i, s in enumerate(steps) if s["id"] == target)
    elif step.get("goto"):
        run.cursor = next(i for i, s in enumerate(steps) if s["id"] == step["goto"])
    else:
        run.cursor = task.step_index + 1
    _advance(db, run, case)
    return run


def pause_run(db: Session, run: AnliegenProcessRun, actor: User):
    _check_available(db)
    _require_handler(actor, _case(db, run))
    if run.state not in ("running", "blocked"):
        raise ProcessConflict("Dieser Prozess kann nicht pausiert werden.")
    _lock_version(db, run)
    run.state = "paused"
    _audit(db, run, actor, "paused")


def resume_run(db: Session, run: AnliegenProcessRun, actor: User):
    _check_available(db)
    case = _case(db, run)
    _require_handler(actor, case)
    if run.state != "paused":
        raise ProcessConflict("Dieser Prozess ist nicht pausiert.")
    _lock_version(db, run)
    run.state = "running"
    open_tasks = db.scalar(select(AnliegenProcessTask.id).where(
        AnliegenProcessTask.run_id == run.id, AnliegenProcessTask.state == "open"))
    _audit(db, run, actor, "resumed")
    if not open_tasks:
        _advance(db, run, case)


def cancel_run(db: Session, run: AnliegenProcessRun, actor: User):
    _check_available(db)
    _require_handler(actor, _case(db, run))
    if run.state in FINISHED:
        raise ProcessConflict("Der Prozess ist bereits abgeschlossen.")
    _lock_version(db, run)
    run.state = "cancelled"
    for task in db.scalars(select(AnliegenProcessTask).where(
            AnliegenProcessTask.run_id == run.id, AnliegenProcessTask.state == "open")):
        task.state = "cancelled"
    _audit(db, run, actor, "cancelled")
